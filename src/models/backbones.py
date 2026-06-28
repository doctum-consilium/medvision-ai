"""Registre des backbones Keras pour le transfer learning médical.

Chaque backbone est décrit par un BackboneConfig : classe Keras, nombre de
couches à dégeler en fine-tuning, et prétraitement attendu.

Usage typique :
    cfg = TF_BACKBONES["densenet121"]
    base = cfg.cls(include_top=False, weights="imagenet", input_shape=(224, 224, 3))
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import tensorflow as tf


@dataclass
class BackboneConfig:
    """Décrit un backbone Keras préentraîné.

    Attributes:
        cls: Classe Keras (ex. tf.keras.applications.DenseNet121).
        preprocess: Fonction de prétraitement correspondante.
        unfreeze_layers: Nombre de couches à dégeler lors du fine-tuning.
    """

    cls: Any
    preprocess: Any
    unfreeze_layers: int


TF_BACKBONES: dict[str, BackboneConfig] = {
    "densenet121": BackboneConfig(
        cls=tf.keras.applications.DenseNet121,
        preprocess=tf.keras.applications.densenet.preprocess_input,
        unfreeze_layers=30,
    ),
    "efficientnetv2b0": BackboneConfig(
        cls=tf.keras.applications.EfficientNetV2B0,
        preprocess=tf.keras.applications.efficientnet_v2.preprocess_input,
        unfreeze_layers=20,
    ),
    "convnexttiny": BackboneConfig(
        cls=tf.keras.applications.ConvNeXtTiny,
        preprocess=tf.keras.applications.convnext.preprocess_input,
        unfreeze_layers=10,
    ),
    "resnet50v2": BackboneConfig(
        cls=tf.keras.applications.ResNet50V2,
        preprocess=tf.keras.applications.resnet_v2.preprocess_input,
        unfreeze_layers=20,
    ),
}


def build_transfer_model(
    backbone_name: str,
    image_size: int,
    num_classes: int,
    learning_rate: float = 1e-3,
    trainable_backbone: bool = False,
    dropout: float | None = None,
) -> tuple[tf.keras.Model, tf.keras.Model]:
    """Construit un modèle de classification par transfer learning.

    Architecture : backbone préentraîné → GlobalAveragePooling → Dropout (optionnel)
    → Dense(num_classes, softmax).

    Args:
        backbone_name: Clé dans TF_BACKBONES (ex. "densenet121").
        image_size: Dimension spatiale de l'entrée (image_size × image_size × 3).
        num_classes: Nombre de classes de sortie.
        learning_rate: Taux d'apprentissage initial de l'optimiseur Adam.
        trainable_backbone: Si True, toutes les couches du backbone sont entraînables.
        dropout: Taux de dropout avant la couche de classification (None = pas de dropout).

    Returns:
        (model, base_model) — le modèle complet compilé et le backbone seul
        (utile pour set_backbone_trainable).

    Raises:
        KeyError: backbone_name absent de TF_BACKBONES.
    """
    cfg = TF_BACKBONES[backbone_name]

    inputs = tf.keras.Input(shape=(image_size, image_size, 3))
    x = cfg.preprocess(inputs)

    base_model = cfg.cls(include_top=False, weights="imagenet", input_tensor=x)
    base_model.trainable = trainable_backbone

    x = tf.keras.layers.GlobalAveragePooling2D()(base_model.output)
    if dropout:
        x = tf.keras.layers.Dropout(float(dropout))(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax")(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=False),
        metrics=["accuracy"],
    )
    return model, base_model


def set_backbone_trainable(base_model: tf.keras.Model, unfreeze_layers: int) -> None:
    """Dégèle les N dernières couches du backbone pour le fine-tuning.

    Les couches BatchNormalization restent toujours gelées (les dégeler
    déstabilise l'entraînement sur de petits datasets médicaux).

    Args:
        base_model: Le backbone extrait par build_transfer_model.
        unfreeze_layers: Nombre de couches à dégeler depuis la fin.
    """
    base_model.trainable = True
    for layer in base_model.layers[:-unfreeze_layers]:
        layer.trainable = False
    for layer in base_model.layers:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = False
