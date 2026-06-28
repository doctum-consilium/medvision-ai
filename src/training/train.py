from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

import mlflow
import numpy as np
import tensorflow as tf
from sklearn.utils.class_weight import compute_class_weight

from src.evaluation.metrics import build_classification_report, evaluate_predictions, save_confusion_matrix
from src.evaluation.metrics_multiclass import save_metrics
from src.models.backbones import TF_BACKBONES
from src.models.baseline_model import build_baseline_model
from src.training.transfer_utils import FineTuneConfig, infer_unfreeze_layers, train_with_progressive_finetuning
from src.utils.config import load_config
from src.utils.dataset import build_datasets
from src.utils.paths import ensure_dir


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a medical image classification model")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config file")
    parser.add_argument("--model", type=str, default="densenet121", help="baseline or transfer backbone name")
    parser.add_argument("--epochs", type=int, default=None)
    return parser.parse_args()


def _log_history_metrics(history: dict[str, list[float]]) -> None:
    for metric_name, values in history.items():
        if not values:
            continue
        series = [float(v) for v in values]
        mlflow.log_metric(f"final_{metric_name}", series[-1])
        if "loss" in metric_name:
            mlflow.log_metric(f"best_{metric_name}", float(min(series)))
        else:
            mlflow.log_metric(f"best_{metric_name}", float(max(series)))


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    seed = int(config.get("seed", 42))
    set_seed(seed)

    image_size = int(config.get("image_size", 224))
    batch_size = int(config.get("batch_size", 16))
    epochs_total = args.epochs or int(config.get("epochs", 12))
    warmup_epochs = int(config.get("warmup_epochs", max(3, min(6, epochs_total // 3))))
    finetune_epochs = max(0, epochs_total - warmup_epochs)
    warmup_lr = float(config.get("warmup_learning_rate", config.get("learning_rate", 1e-3)))
    finetune_lr = float(config.get("finetune_learning_rate", min(warmup_lr, 3e-5)))
    dataset_dir = config["dataset_dir"]
    model_dir = ensure_dir(config.get("model_dir", "artifacts/models"))
    reports_dir = ensure_dir(config.get("reports_dir", "artifacts/reports"))
    label_smoothing = float(config.get("label_smoothing", 0.0))
    backbone_name = args.model.lower()

    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", config.get("mlflow_tracking_uri", "file:./mlruns"))
    mlflow_experiment = os.getenv("MLFLOW_EXPERIMENT_NAME", config.get("project_name", "medvision-ai"))
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(mlflow_experiment)

    train_ds, val_ds, test_ds = build_datasets(
        dataset_dir=dataset_dir,
        image_size=image_size,
        batch_size=batch_size,
        validation_split=float(config.get("validation_split", 0.2)),
        seed=seed,
    )

    y_train_all = []
    for _, labels in train_ds.unbatch():
        y = labels.numpy()
        y_train_all.append(int(y[0] if hasattr(y, "__len__") else y))
    class_weights_values = compute_class_weight(class_weight="balanced", classes=np.array([0, 1]), y=np.array(y_train_all))
    class_weights = {0: float(class_weights_values[0]), 1: float(class_weights_values[1])}

    if backbone_name == "baseline":
        model = build_baseline_model(image_size=image_size, num_classes=2, learning_rate=warmup_lr)
        history = model.fit(
            train_ds,
            validation_data=val_ds,
            epochs=epochs_total,
            class_weight=class_weights,
            callbacks=[
                tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=4, restore_best_weights=True),
                tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.2, patience=2),
            ],
            verbose=1,
        ).history
    else:
        if backbone_name not in TF_BACKBONES:
            raise ValueError(f"Unknown model `{backbone_name}`. Choices: baseline, {', '.join(TF_BACKBONES)}")
        model, history = train_with_progressive_finetuning(
            train_ds=train_ds,
            val_ds=val_ds,
            image_size=image_size,
            num_classes=2,
            cfg=FineTuneConfig(
                warmup_epochs=warmup_epochs,
                finetune_epochs=finetune_epochs,
                warmup_lr=warmup_lr,
                finetune_lr=finetune_lr,
                backbone_name=backbone_name,
                unfreeze_layers=infer_unfreeze_layers(backbone_name, config.get("unfreeze_layers")),
                dropout=config.get("dropout"),
                label_smoothing=label_smoothing,
            ),
            class_weight=class_weights,
        )

    y_true, y_prob = [], []
    for images, labels in test_ds:
        raw = np.asarray(model.predict(images, verbose=0))
        # Sorties à 2 classes softmax → proba de la classe positive (indice 1, PNEUMONIA).
        # Sorties sigmoïdes 1D → squeeze. Garantit un y_prob 1D pour les métriques binaires.
        preds = raw[:, 1] if raw.ndim == 2 and raw.shape[-1] == 2 else raw.squeeze()
        y_prob.extend(np.atleast_1d(preds).tolist())
        y_true.extend(np.atleast_1d(labels.numpy().astype(int).squeeze()).tolist())

    y_true_arr = np.array(y_true)
    y_prob_arr = np.array(y_prob)
    metrics = evaluate_predictions(y_true_arr, y_prob_arr)
    report = build_classification_report(y_true_arr, y_prob_arr)

    model_path = Path(model_dir) / ("baseline_model.keras" if backbone_name == "baseline" else f"{backbone_name}_model.keras")
    report_path = Path(reports_dir) / ("baseline_classification_report.txt" if backbone_name == "baseline" else f"{backbone_name}_classification_report.txt")
    metrics_path = Path(reports_dir) / ("baseline_metrics.json" if backbone_name == "baseline" else f"{backbone_name}_metrics.json")
    cm_path = Path(reports_dir) / ("baseline_confusion_matrix.png" if backbone_name == "baseline" else f"{backbone_name}_confusion_matrix.png")
    history_path = Path(reports_dir) / ("baseline_history.json" if backbone_name == "baseline" else f"{backbone_name}_history.json")

    with mlflow.start_run(run_name=f"{backbone_name}-transfer"):
        mlflow.log_params(
            {
                "problem": "chest_xray",
                "model": backbone_name,
                "image_size": image_size,
                "batch_size": batch_size,
                "epochs_total": epochs_total,
                "warmup_epochs": warmup_epochs,
                "finetune_epochs": finetune_epochs,
                "warmup_lr": warmup_lr,
                "finetune_lr": finetune_lr,
                "class_weight_0": class_weights[0],
                "class_weight_1": class_weights[1],
            }
        )
        _log_history_metrics(history)
        for key, value in metrics.items():
            mlflow.log_metric(key, float(value))

        model.save(model_path)
        report_path.write_text(report, encoding="utf-8")
        save_metrics(metrics, metrics_path)
        save_confusion_matrix(y_true_arr, y_prob_arr, cm_path)
        history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

        mlflow.log_artifact(str(model_path))
        mlflow.log_artifact(str(report_path))
        mlflow.log_artifact(str(metrics_path))
        mlflow.log_artifact(str(cm_path))
        mlflow.log_artifact(str(history_path))

    print(json.dumps({"metrics": metrics, "model_path": str(model_path)}, indent=2))


if __name__ == "__main__":
    main()
