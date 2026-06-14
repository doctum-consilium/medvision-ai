from __future__ import annotations

from pathlib import Path

import numpy as np
import tensorflow as tf

from src.preprocessing.image_loader import load_and_preprocess_image
from src.utils.config import load_config


def load_brain_mri_model(model_path: str | Path) -> tf.keras.Model:
    return tf.keras.models.load_model(model_path)


def predict_brain_mri(
    model: tf.keras.Model,
    image_path: str | Path,
    config_path: str | Path = "configs/brain_tumor_mri.yaml",
) -> dict[str, object]:
    cfg = load_config(config_path)
    class_names: list[str] = cfg["class_names"]
    image_size = int(cfg.get("image_size", 224))

    image = load_and_preprocess_image(image_path, image_size=image_size)
    batch = np.expand_dims(image, axis=0)
    probs = model.predict(batch, verbose=0)[0]
    pred_idx = int(np.argmax(probs))

    return {
        "predicted_class": class_names[pred_idx],
        "confidence": float(probs[pred_idx]),
        "probabilities": {name: float(probs[i]) for i, name in enumerate(class_names)},
    }
