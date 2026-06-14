from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from src.datasets.brats_2d_dataset import BrainMRISliceDataset
from src.models.classification_2d.simple_cnn import SimpleCNN2D
from src.training.trainer import run_epoch
from src.utils.config import load_config
from src.utils.logging import get_logger
from src.utils.paths import ensure_dir
from src.utils.seed import set_seed

LOGGER = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a demonstrative 2D MRI classifier")
    parser.add_argument("--config", required=True, help="Path to YAML config")
    return parser.parse_args()


def build_loader(csv_path: str | Path, config: dict, shuffle: bool) -> DataLoader:
    dataset = BrainMRISliceDataset(
        csv_path=csv_path,
        image_size=int(config.get("image_size", 128)),
        normalization=config.get("normalization", {}).get("method", "zscore_nonzero"),
        slice_strategy=config.get("slice_selection", {}).get("strategy", "central_k"),
        k=int(config.get("slice_selection", {}).get("k", 5)),
    )
    return DataLoader(
        dataset,
        batch_size=int(config.get("batch_size", 8)),
        shuffle=shuffle,
        num_workers=int(config.get("num_workers", 0)),
    )


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    seed = int(config.get("seed", 42))
    set_seed(seed)

    device = torch.device(config.get("training", {}).get("device", "cpu"))
    artifacts_dir = ensure_dir(config.get("artifacts_dir", "artifacts"))
    model_dir = ensure_dir(artifacts_dir / "models")
    reports_dir = ensure_dir(artifacts_dir / "reports")

    train_loader = build_loader(config["train_csv"], config, shuffle=True)
    val_loader = build_loader(config["val_csv"], config, shuffle=False)
    test_loader = build_loader(config["test_csv"], config, shuffle=False)

    model = SimpleCNN2D(
        in_channels=int(config.get("model", {}).get("in_channels", 1)),
        num_classes=int(config.get("num_classes", 2)),
    ).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=float(config.get("learning_rate", 1e-3)))

    epochs = int(config.get("epochs", 3))
    history: dict[str, list[float]] = {"train_loss": [], "train_acc": [], "val_loss": [], "val_acc": []}

    best_val_acc = -1.0
    best_model_path = model_dir / "brain_mri_2d_demo.pt"

    for epoch in range(1, epochs + 1):
        train_metrics = run_epoch(model, train_loader, criterion, device, optimizer=optimizer)
        val_metrics = run_epoch(model, val_loader, criterion, device, optimizer=None)

        history["train_loss"].append(train_metrics.loss)
        history["train_acc"].append(train_metrics.accuracy)
        history["val_loss"].append(val_metrics.loss)
        history["val_acc"].append(val_metrics.accuracy)

        LOGGER.info(
            "Epoch %s/%s | train_loss=%.4f train_acc=%.4f | val_loss=%.4f val_acc=%.4f",
            epoch,
            epochs,
            train_metrics.loss,
            train_metrics.accuracy,
            val_metrics.loss,
            val_metrics.accuracy,
        )

        if val_metrics.accuracy > best_val_acc:
            best_val_acc = val_metrics.accuracy
            torch.save(model.state_dict(), best_model_path)

    model.load_state_dict(torch.load(best_model_path, map_location=device))
    test_metrics = run_epoch(model, test_loader, criterion, device, optimizer=None)

    report = {
        "best_val_accuracy": best_val_acc,
        "test_loss": test_metrics.loss,
        "test_accuracy": test_metrics.accuracy,
        "history": history,
    }

    report_path = reports_dir / "brain_mri_2d_demo_metrics.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOGGER.info("Saved model to %s", best_model_path)
    LOGGER.info("Saved report to %s", report_path)
    LOGGER.info("Final test metrics: %s", json.dumps({k: v for k, v in report.items() if k != 'history'}, indent=2))


if __name__ == "__main__":
    main()
