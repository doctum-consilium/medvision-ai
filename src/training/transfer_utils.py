from __future__ import annotations

from dataclasses import dataclass

import tensorflow as tf

from src.models.backbones import TF_BACKBONES, build_transfer_model, set_backbone_trainable


@dataclass
class FineTuneConfig:
    warmup_epochs: int
    finetune_epochs: int
    warmup_lr: float
    finetune_lr: float
    backbone_name: str
    unfreeze_layers: int
    dropout: float | None = None
    label_smoothing: float = 0.0


def default_callbacks() -> list[tf.keras.callbacks.Callback]:
    return [
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=4, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.2, patience=2, verbose=1),
    ]


def train_with_progressive_finetuning(
    train_ds: tf.data.Dataset,
    val_ds: tf.data.Dataset,
    image_size: int,
    num_classes: int,
    cfg: FineTuneConfig,
    class_weight: dict[int, float] | None = None,
) -> tuple[tf.keras.Model, dict[str, list[float]]]:
    model, base_model = build_transfer_model(
        backbone_name=cfg.backbone_name,
        image_size=image_size,
        num_classes=num_classes,
        learning_rate=cfg.warmup_lr,
        trainable_backbone=False,
        dropout=cfg.dropout,
        label_smoothing=cfg.label_smoothing,
    )

    history: dict[str, list[float]] = {}
    callbacks = default_callbacks()

    if cfg.warmup_epochs > 0:
        warmup_history = model.fit(
            train_ds,
            validation_data=val_ds,
            epochs=cfg.warmup_epochs,
            class_weight=class_weight,
            callbacks=callbacks,
            verbose=1,
        ).history
        for k, v in warmup_history.items():
            history.setdefault(k, []).extend(v)

    set_backbone_trainable(base_model, cfg.unfreeze_layers)
    # metrics=["accuracy"] (et non model.metrics) : réutiliser les objets Metric déjà
    # construits rend le conteneur de métriques non-sérialisable → model.save() plante
    # (Keras 3 : compile_utils get_config NotImplementedError).
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=cfg.finetune_lr),
        loss=model.loss,
        metrics=["accuracy"],
    )

    if cfg.finetune_epochs > 0:
        fine_history = model.fit(
            train_ds,
            validation_data=val_ds,
            epochs=cfg.warmup_epochs + cfg.finetune_epochs,
            initial_epoch=cfg.warmup_epochs,
            class_weight=class_weight,
            callbacks=callbacks,
            verbose=1,
        ).history
        for k, v in fine_history.items():
            history.setdefault(k, []).extend(v)

    return model, history


def infer_unfreeze_layers(backbone_name: str, override: int | None = None) -> int:
    if override is not None:
        return override
    return TF_BACKBONES[backbone_name].unfreeze_layers
