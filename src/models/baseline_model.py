"""Modèle de classification d'images entraîné from scratch (sans préentraînement).

Sert de ligne de base pour comparer les performances des backbones préentraînés.
Architecture volontairement simple : 3 blocs Conv → MaxPool → Dense.
"""
from __future__ import annotations

import tensorflow as tf


def build_baseline_model(
    image_size: int = 224,
    num_classes: int = 4,
    learning_rate: float = 1e-3,
) -> tf.keras.Model:
    """Construit un CNN léger entraîné from scratch.

    Args:
        image_size: Dimension spatiale de l'entrée (image_size × image_size × 3).
        num_classes: Nombre de classes de sortie.
        learning_rate: Taux d'apprentissage de l'optimiseur Adam.

    Returns:
        Modèle Keras compilé, prêt pour model.fit().
    """
    inputs = tf.keras.Input(shape=(image_size, image_size, 3))

    x = tf.keras.layers.Rescaling(1.0 / 255)(inputs)

    for filters in (32, 64, 128):
        x = tf.keras.layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.MaxPooling2D(2)(x)

    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dense(256, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.4)(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax")(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model
