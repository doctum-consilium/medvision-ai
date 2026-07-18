"""Tests du chargeur de données de segmentation (`src/segmentation/data.py`).

Ce module importe TensorFlow au niveau module : il ne peut donc PAS tourner
dans la suite smoke (volontairement sans TF). Ce fichier vit à la racine de
tests/ — il n'est collecté que par les jobs CI avec TensorFlow (test-tf,
current-test-suite).

But : verrouiller le comportement de `build_segmentation_datasets` —
formes des batches (multitâche et binaire), finitude de val/test (le bug
« .repeat() rendait val/test infinis » corrigé par la PR #10 ne doit pas
revenir), split de secours quand le manifeste n'a pas de lignes `test`,
et erreurs explicites sur manifeste absent/vide.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.segmentation.data import _read_image, _read_mask, build_segmentation_datasets

# Petite taille d'image : garde les tests rapides (le contenu des pixels
# n'a aucune importance ici, seules les formes et les valeurs comptent).
IMG = 16


def _write_sample_images(root: Path) -> tuple[Path, Path]:
    """Écrit une paire (image RGB, masque) minimaliste et retourne leurs chemins.

    Le masque contient un carré blanc sur fond noir : après lecture il doit
    être binarisé en {0.0, 1.0}, ce que les tests vérifient.
    """
    image_path = root / "image.png"
    mask_path = root / "mask.png"
    Image.new("RGB", (IMG, IMG), color=(120, 30, 200)).save(image_path)
    mask = Image.new("L", (IMG, IMG), color=0)
    mask.paste(255, (4, 4, 12, 12))
    mask.save(mask_path)
    return image_path, mask_path


def _write_manifest(root: Path, rows: list[dict[str, str]]) -> Path:
    """Écrit un manifest.csv au format produit par prepare_segmentation_dataset."""
    manifest_path = root / "manifest.csv"
    with manifest_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["image_path", "mask_path", "label", "split"])
        writer.writeheader()
        writer.writerows(rows)
    return manifest_path


def _make_manifest(root: Path, *, with_test_split: bool) -> Path:
    """Construit un manifeste équilibré à 2 classes (8+8 train, 2+2 test).

    Les lignes réutilisent la même paire image/masque : le chargeur lit les
    fichiers ligne par ligne, leur unicité n'apporte rien au test.
    """
    image_path, mask_path = _write_sample_images(root)
    rows = []
    for label in ("negative", "positive"):
        for _ in range(8):
            rows.append(
                {"image_path": str(image_path), "mask_path": str(mask_path),
                 "label": label, "split": "train"}
            )
        if with_test_split:
            for _ in range(2):
                rows.append(
                    {"image_path": str(image_path), "mask_path": str(mask_path),
                     "label": label, "split": "test"}
                )
    return _write_manifest(root, rows)


def test_read_image_normalizes_to_unit_range(tmp_path: Path) -> None:
    """`_read_image` redimensionne en RGB float32 normalisé [0, 1].

    Testé directement (et pas seulement via le tf.data.Dataset) car le corps du
    générateur s'exécute dans des threads gérés par TensorFlow que coverage ne
    trace pas — sans ce test direct, ces lignes paraîtraient mortes.
    """
    image_path, _ = _write_sample_images(tmp_path)
    arr = _read_image(str(image_path), IMG)
    assert arr.shape == (IMG, IMG, 3)
    assert arr.dtype == np.float32
    assert arr.min() >= 0.0 and arr.max() <= 1.0


def test_read_mask_is_strictly_binary(tmp_path: Path) -> None:
    """`_read_mask` binarise le masque en {0, 1} avec un canal explicite."""
    _, mask_path = _write_sample_images(tmp_path)
    arr = _read_mask(str(mask_path), IMG)
    assert arr.shape == (IMG, IMG, 1)
    assert set(np.unique(arr).tolist()) == {0.0, 1.0}


def test_multitask_batches_shapes_and_values(tmp_path: Path) -> None:
    """Le mode multitâche produit (image, {segmentation, classification}) bien formés."""
    manifest = _make_manifest(tmp_path, with_test_split=True)
    train_ds, val_ds, test_ds, labels, train_size = build_segmentation_datasets(
        manifest, image_size=IMG, batch_size=2, validation_split=0.25, task_type="multitask"
    )

    assert labels == ["negative", "positive"]
    # 16 lignes train − 25 % de validation = 12 conservées pour l'entraînement.
    assert train_size == 12

    # Le train est répété (infini) : on ne prélève qu'un batch.
    x, y = next(iter(train_ds))
    assert x.shape == (2, IMG, IMG, 3)
    assert set(y.keys()) == {"segmentation_output", "classification_output"}
    assert y["segmentation_output"].shape == (2, IMG, IMG, 1)
    assert y["classification_output"].shape == (2,)

    # Image normalisée [0, 1] et masque strictement binaire {0, 1}.
    assert float(x.numpy().min()) >= 0.0 and float(x.numpy().max()) <= 1.0
    mask_values = np.unique(y["segmentation_output"].numpy())
    assert set(mask_values.tolist()) <= {0.0, 1.0}
    assert len(mask_values) == 2  # le carré blanc garantit les deux valeurs


def test_val_and_test_datasets_are_finite(tmp_path: Path) -> None:
    """val/test ne sont PAS répétés : les itérer se termine (bug .repeat())."""
    manifest = _make_manifest(tmp_path, with_test_split=True)
    _, val_ds, test_ds, _, _ = build_segmentation_datasets(
        manifest, image_size=IMG, batch_size=2, validation_split=0.25, task_type="multitask"
    )
    # 4 lignes de validation et 4 de test, batch de 2 → 2 batches finis chacun.
    assert len(list(val_ds)) == 2
    assert len(list(test_ds)) == 2


def test_binary_task_yields_plain_masks(tmp_path: Path) -> None:
    """Hors multitâche, la cible est le masque seul (pas de dict de sorties)."""
    manifest = _make_manifest(tmp_path, with_test_split=True)
    train_ds, _, _, _, _ = build_segmentation_datasets(
        manifest, image_size=IMG, batch_size=2, validation_split=0.25, task_type="segmentation"
    )
    x, y = next(iter(train_ds))
    assert x.shape == (2, IMG, IMG, 3)
    assert y.shape == (2, IMG, IMG, 1)


def test_missing_test_split_triggers_fallback(tmp_path: Path) -> None:
    """Sans ligne `test`, un jeu de test est découpé automatiquement du train."""
    manifest = _make_manifest(tmp_path, with_test_split=False)
    _, _, test_ds, labels, train_size = build_segmentation_datasets(
        manifest, image_size=IMG, batch_size=2, validation_split=0.25, task_type="multitask"
    )
    assert labels == ["negative", "positive"]
    # 16 lignes → 25 % prélevées pour le test (4), puis 25 % du reste en
    # validation (3) → 9 restent à l'entraînement.
    assert train_size == 9
    assert len(list(test_ds)) == 2  # 4 lignes de test, batch de 2


def test_unknown_labels_are_excluded_from_classes(tmp_path: Path) -> None:
    """Le label `unknown` n'engendre pas de classe (il est mappé sur l'index 0)."""
    image_path, mask_path = _write_sample_images(tmp_path)
    rows = []
    for label in ("negative", "positive", "unknown"):
        for _ in range(4):
            rows.append(
                {"image_path": str(image_path), "mask_path": str(mask_path),
                 "label": label, "split": "train"}
            )
    for label in ("negative", "positive"):
        rows.append(
            {"image_path": str(image_path), "mask_path": str(mask_path),
             "label": label, "split": "test"}
        )
    manifest = _write_manifest(tmp_path, rows)
    _, _, _, labels, _ = build_segmentation_datasets(
        manifest, image_size=IMG, batch_size=2, validation_split=0.25, task_type="multitask"
    )
    assert labels == ["negative", "positive"]


def test_only_unknown_labels_fall_back_to_default_classes(tmp_path: Path) -> None:
    """Manifeste 100 % `unknown` → classes par défaut negative/positive."""
    image_path, mask_path = _write_sample_images(tmp_path)
    rows = [
        {"image_path": str(image_path), "mask_path": str(mask_path),
         "label": "unknown", "split": split}
        for split in ["train"] * 8 + ["test"] * 2
    ]
    manifest = _write_manifest(tmp_path, rows)
    _, _, _, labels, _ = build_segmentation_datasets(
        manifest, image_size=IMG, batch_size=2, validation_split=0.25, task_type="multitask"
    )
    assert labels == ["negative", "positive"]


def test_missing_manifest_raises_file_not_found(tmp_path: Path) -> None:
    """Manifeste inexistant → FileNotFoundError avec le chemin fautif."""
    with pytest.raises(FileNotFoundError, match="Manifest not found"):
        build_segmentation_datasets(tmp_path / "absent.csv", image_size=IMG, batch_size=2)


def test_empty_manifest_file_raises_value_error(tmp_path: Path) -> None:
    """Fichier vide (0 octet) → ValueError explicite, avant même pandas."""
    manifest = tmp_path / "manifest.csv"
    manifest.touch()
    with pytest.raises(ValueError, match="Manifest is empty"):
        build_segmentation_datasets(manifest, image_size=IMG, batch_size=2)


def test_header_only_manifest_raises_value_error(tmp_path: Path) -> None:
    """CSV avec en-têtes mais zéro ligne → ValueError « No rows found »."""
    manifest = _write_manifest(tmp_path, rows=[])
    with pytest.raises(ValueError, match="No rows found"):
        build_segmentation_datasets(manifest, image_size=IMG, batch_size=2)
