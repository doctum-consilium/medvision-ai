from __future__ import annotations

from pathlib import Path

import numpy as np
import tensorflow as tf

from src.preprocessing.image_loader import load_and_preprocess_image


def load_model(model_path: str | Path) -> tf.keras.Model:
    return tf.keras.models.load_model(model_path)


def predict_from_path(model: tf.keras.Model, image_path: str | Path, image_size: int = 224) -> dict[str, float | str]:
    image = load_and_preprocess_image(image_path, image_size=image_size)
    batch = np.expand_dims(image, axis=0)
    probability = float(model.predict(batch, verbose=0)[0][0])
    predicted_class = "PNEUMONIA" if probability >= 0.5 else "NORMAL"
    return {"predicted_class": predicted_class, "probability_pneumonia": probability}
