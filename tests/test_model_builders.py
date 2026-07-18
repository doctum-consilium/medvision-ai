"""Tests des constructeurs d'architectures (classification + segmentation).

Ces modèles importent TensorFlow au niveau module : ils ne peuvent donc PAS
tourner dans la suite smoke (volontairement sans TF). Ce fichier vit à la racine
de tests/ — il n'est collecté que par le job CI « test-tf » (avec TensorFlow).

But : verrouiller la simple construction des modèles (forme des entrées/sorties,
gel des couches en fine-tuning) pour que la régression « code modèle absent du
dépôt » ne puisse pas se reproduire silencieusement.
"""
from __future__ import annotations

import numpy as np
import pytest
import tensorflow as tf

from src.models.backbones import (
    TF_BACKBONES,
    BackboneConfig,
    build_transfer_model,
    set_backbone_trainable,
)
from src.models.baseline_model import build_baseline_model
from src.segmentation.models.unet import build_multitask_unet, build_unet

# Petite taille d'image : garde les tests rapides tout en restant divisible
# par 16 (U-Net = 4 niveaux de max-pooling 2×2 → 32 / 16 = 2).
IMG = 32


def test_build_baseline_model_output_shape() -> None:
    """Le CNN baseline produit une distribution softmax sur num_classes."""
    model = build_baseline_model(image_size=IMG, num_classes=3)
    assert model.input_shape == (None, IMG, IMG, 3)
    assert model.output_shape == (None, 3)

    # Une prédiction réelle : les probas somment à 1 par échantillon.
    x = np.zeros((2, IMG, IMG, 3), dtype="float32")
    probs = model.predict(x, verbose=0)
    assert probs.shape == (2, 3)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)


def test_build_unet_binary_mask_shape() -> None:
    """U-Net binaire : sortie sigmoïde à 1 canal, même résolution que l'entrée."""
    model = build_unet(image_size=IMG, num_mask_classes=1)
    assert model.input_shape == (None, IMG, IMG, 3)
    assert model.output_shape == (None, IMG, IMG, 1)


def test_build_unet_multiclass_mask_shape() -> None:
    """U-Net multi-classe : sortie softmax à num_mask_classes canaux."""
    model = build_unet(image_size=IMG, num_mask_classes=4)
    assert model.output_shape == (None, IMG, IMG, 4)


def _shapes_by_name(model: tf.keras.Model) -> dict[str, tuple]:
    """Associe chaque nom de sortie à sa forme.

    Keras 3 renvoie `model.output_shape` sous forme de LISTE ordonnée (et non de
    dict, même quand le modèle a été défini avec des sorties nommées). On
    reconstruit donc le mapping nom→forme via `model.output_names`, dans le même
    ordre, pour des assertions robustes quelle que soit la version de Keras.
    """
    return dict(zip(model.output_names, model.output_shape, strict=True))


def test_build_multitask_unet_two_named_heads() -> None:
    """Le U-Net multitâche expose une tête segmentation ET une tête classification."""
    model = build_multitask_unet(image_size=IMG, num_classes=2)
    shapes = _shapes_by_name(model)
    assert set(shapes) == {"segmentation_output", "classification_output"}
    assert shapes["segmentation_output"] == (None, IMG, IMG, 1)
    # num_classes <= 2 → un seul logit sigmoïde.
    assert shapes["classification_output"] == (None, 1)


def test_build_multitask_unet_multiclass_head() -> None:
    """Avec num_classes > 2, la tête classification devient un softmax à N unités."""
    model = build_multitask_unet(image_size=IMG, num_classes=5)
    assert _shapes_by_name(model)["classification_output"] == (None, 5)


def test_set_backbone_trainable_freezes_batchnorm() -> None:
    """Le fine-tuning dégèle les dernières couches mais garde les BatchNorm gelées.

    On construit un mini-backbone (sans téléchargement de poids imagenet) pour
    couvrir la logique de gel sans dépendre du réseau.
    """
    base = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(IMG, IMG, 3)),
            tf.keras.layers.Conv2D(4, 3, padding="same"),
            tf.keras.layers.BatchNormalization(),
            tf.keras.layers.Conv2D(4, 3, padding="same"),
            tf.keras.layers.BatchNormalization(),
            tf.keras.layers.Conv2D(4, 3, padding="same"),
        ]
    )

    set_backbone_trainable(base, unfreeze_layers=1)

    # Toute couche BatchNormalization reste gelée, quoi qu'il arrive.
    for layer in base.layers:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            assert layer.trainable is False
    # La toute dernière couche (non-BN) est bien entraînable.
    assert base.layers[-1].trainable is True


class _FakeBase:
    """Backbone factice : évite le téléchargement des poids imagenet en test.

    `build_transfer_model` n'utilise que `.output` (KerasTensor à brancher sur
    la tête de classification) et `.trainable` (bool) — ce substitut suffit.
    """

    def __init__(self, input_tensor) -> None:
        self.output = tf.keras.layers.Conv2D(2, 1)(input_tensor)
        self.trainable = True


def test_build_transfer_model_warns_when_label_smoothing_requested(monkeypatch) -> None:
    """label_smoothing > 0 émet un warning : le loss sparse ne sait pas le lisser.

    Verrouille la décision documentée dans build_transfer_model : plutôt que de
    casser model.save() (Keras 3) avec un loss custom, on garde le loss sparse
    et on prévient l'utilisateur que le lissage n'est PAS appliqué.
    """
    fake_cfg = BackboneConfig(
        cls=lambda include_top, weights, input_tensor: _FakeBase(input_tensor),
        preprocess=lambda x: x,
        unfreeze_layers=1,
    )
    monkeypatch.setitem(TF_BACKBONES, "fake", fake_cfg)

    with pytest.warns(UserWarning, match="label_smoothing"):
        model, _ = build_transfer_model(
            "fake", image_size=IMG, num_classes=3, label_smoothing=0.1
        )
    assert model.output_shape == (None, 3)


def test_tf_backbones_registry_is_well_formed() -> None:
    """Le registre des backbones expose des BackboneConfig complets et cohérents."""
    assert set(TF_BACKBONES) == {
        "densenet121",
        "efficientnetv2b0",
        "convnexttiny",
        "resnet50v2",
        "optimized",
    }
    for name, cfg in TF_BACKBONES.items():
        assert isinstance(cfg, BackboneConfig), name
        assert callable(cfg.cls), name
        assert callable(cfg.preprocess), name
        assert cfg.unfreeze_layers > 0, name

    # « optimized » est l'alias canonique utilisé par dvc.yaml et les artefacts
    # S3 : il doit rester strictement identique à EfficientNetV2B0, sinon les
    # modèles rechargés depuis S3 ne correspondraient plus à leur architecture.
    assert TF_BACKBONES["optimized"].cls is tf.keras.applications.EfficientNetV2B0
    assert (
        TF_BACKBONES["optimized"].preprocess
        is tf.keras.applications.efficientnet_v2.preprocess_input
    )
