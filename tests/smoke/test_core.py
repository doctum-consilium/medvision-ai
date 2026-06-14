"""Tests smoke sans dépendances lourdes (TF / onnxruntime / PyTorch).

Ces tests vérifient les invariants critiques du projet (registry, preprocessing,
gestion des erreurs) sans charger de modèles réels. Ils s'exécutent en quelques
secondes même sur un poste sans GPU et en CI légère (job test-fast).

Pour lancer : pytest tests/smoke/test_core.py -v
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.preprocessing.image_loader import load_and_preprocess_image
from src.registry.model_registry import (
    ModelLoadError,
    ModelNotFoundError,
    _find_first_existing,
    load_onnx_model,
    load_registry,
)

# ═══════════════════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════════════════


class TestLoadRegistry:
    def test_returns_problems_key(self, tmp_path: Path) -> None:
        result = load_registry(tmp_path)
        assert "problems" in result

    def test_expected_problems_present(self, tmp_path: Path) -> None:
        problems = load_registry(tmp_path)["problems"]
        assert "chest_xray" in problems
        assert "brain_mri" in problems
        assert "brain_tumor_segmentation" in problems

    def test_each_problem_has_models(self, tmp_path: Path) -> None:
        problems = load_registry(tmp_path)["problems"]
        for key, problem in problems.items():
            assert "models" in problem, f"Problème '{key}' sans clé 'models'"
            assert len(problem["models"]) > 0, f"Problème '{key}' sans aucun modèle"

    def test_model_available_false_when_file_missing(self, tmp_path: Path) -> None:
        """Quand artifacts/models/ est vide, tous les modèles sont available=False."""
        problems = load_registry(tmp_path)["problems"]
        for prob_key, problem in problems.items():
            for model_key, model in problem["models"].items():
                assert model["available"] is False, (
                    f"{prob_key}/{model_key} marqué available=True alors que le fichier est absent"
                )

    def test_model_available_true_when_onnx_file_present(self, tmp_path: Path) -> None:
        """Un fichier .onnx présent → available=True."""
        models_dir = tmp_path / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "optimized_model.onnx").write_bytes(b"fake-onnx")
        problems = load_registry(tmp_path)["problems"]
        assert problems["chest_xray"]["models"]["optimized"]["available"] is True

    def test_model_framework_is_onnxruntime(self, tmp_path: Path) -> None:
        """Tous les modèles doivent déclarer 'onnxruntime' comme framework."""
        problems = load_registry(tmp_path)["problems"]
        for prob_key, problem in problems.items():
            for model_key, model in problem["models"].items():
                assert model["framework"] == "onnxruntime", (
                    f"{prob_key}/{model_key} a framework={model['framework']!r} au lieu de 'onnxruntime'"
                )

    def test_metrics_empty_when_file_absent(self, tmp_path: Path) -> None:
        problems = load_registry(tmp_path)["problems"]
        for problem in problems.values():
            for model in problem["models"].values():
                assert model["metrics"] == {}

    def test_class_names_populated(self, tmp_path: Path) -> None:
        problems = load_registry(tmp_path)["problems"]
        assert problems["chest_xray"]["class_names"] == ["NORMAL", "PNEUMONIA"]
        assert len(problems["brain_mri"]["class_names"]) == 4


class TestFindFirstExisting:
    def test_returns_none_when_all_missing(self, tmp_path: Path) -> None:
        result = _find_first_existing(tmp_path, ["a.txt", "b.txt"])
        assert result is None

    def test_returns_first_existing(self, tmp_path: Path) -> None:
        (tmp_path / "b.txt").write_text("x")
        result = _find_first_existing(tmp_path, ["a.txt", "b.txt"])
        assert result == tmp_path / "b.txt"

    def test_ignores_empty_names(self, tmp_path: Path) -> None:
        result = _find_first_existing(tmp_path, ["", ""])
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# load_onnx_model — erreurs propres (pas de traceback illisible)
# ═══════════════════════════════════════════════════════════════════════════


class TestLoadOnnxModel:
    def test_raises_model_not_found_when_file_missing(self, tmp_path: Path) -> None:
        """Fichier .onnx absent → ModelNotFoundError avec message lisible."""
        missing = str(tmp_path / "ghost.onnx")
        with pytest.raises(ModelNotFoundError):
            load_onnx_model(missing)

    def test_model_not_found_message_is_human_readable(self, tmp_path: Path) -> None:
        """Le message d'erreur doit être lisible — pas de JSON de config Keras."""
        missing = str(tmp_path / "ghost.onnx")
        with pytest.raises(ModelNotFoundError) as exc_info:
            load_onnx_model(missing)
        msg = str(exc_info.value)
        assert "ghost.onnx" in msg, "Le nom du fichier doit apparaître dans le message"
        assert len(msg) < 500, "Le message ne doit pas contenir de JSON volumineux"

    def test_model_not_found_is_file_not_found(self) -> None:
        """ModelNotFoundError doit être une sous-classe de FileNotFoundError."""
        assert issubclass(ModelNotFoundError, FileNotFoundError)

    def test_model_load_error_is_runtime_error(self) -> None:
        """ModelLoadError doit être une sous-classe de RuntimeError."""
        assert issubclass(ModelLoadError, RuntimeError)

    def test_load_onnx_model_is_cached(self) -> None:
        """Le décorateur @lru_cache doit être présent sur load_onnx_model."""
        assert hasattr(load_onnx_model, "cache_info"), (
            "load_onnx_model doit utiliser @lru_cache pour éviter de recharger le modèle à chaque inférence"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Preprocessing
# ═══════════════════════════════════════════════════════════════════════════


class TestImagePreprocessing:
    def test_output_shape_classification(self, tmp_path: Path) -> None:
        """Taille 224×224 pour les problèmes de classification."""
        from PIL import Image

        img_path = tmp_path / "test.png"
        Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(img_path)
        arr = load_and_preprocess_image(img_path, image_size=224)
        assert arr.shape == (224, 224, 3)
        assert arr.dtype == np.float32

    def test_output_shape_segmentation(self, tmp_path: Path) -> None:
        """Taille 256×256 pour les modèles de segmentation."""
        from PIL import Image

        img_path = tmp_path / "test.png"
        Image.fromarray(np.zeros((32, 32, 3), dtype=np.uint8)).save(img_path)
        arr = load_and_preprocess_image(img_path, image_size=256)
        assert arr.shape == (256, 256, 3)

    def test_pixel_values_normalized(self, tmp_path: Path) -> None:
        """Les pixels doivent être normalisés dans [0, 1]."""
        from PIL import Image

        img_path = tmp_path / "white.png"
        Image.fromarray(np.full((32, 32, 3), 255, dtype=np.uint8)).save(img_path)
        arr = load_and_preprocess_image(img_path, image_size=32)
        assert arr.min() >= 0.0
        assert arr.max() <= 1.0

    def test_grayscale_converted_to_rgb(self, tmp_path: Path) -> None:
        """Une image en niveaux de gris doit être convertie en RGB."""
        from PIL import Image

        img_path = tmp_path / "gray.png"
        Image.fromarray(np.zeros((32, 32), dtype=np.uint8)).save(img_path)
        arr = load_and_preprocess_image(img_path, image_size=32)
        assert arr.shape[-1] == 3, "L'image doit avoir 3 canaux RGB en sortie"


# ═══════════════════════════════════════════════════════════════════════════
# .gitignore — invariants
# ═══════════════════════════════════════════════════════════════════════════


class TestGitignore:
    GITIGNORE = Path(__file__).parent.parent.parent / ".gitignore"

    def _content(self) -> str:
        return self.GITIGNORE.read_text(encoding="utf-8")

    def test_gitignore_exists(self) -> None:
        assert self.GITIGNORE.exists(), ".gitignore manquant"

    def test_data_raw_excluded(self) -> None:
        assert "data/raw/" in self._content(), "data/raw/ doit être dans .gitignore"

    def test_dvc_tmp_excluded(self) -> None:
        assert ".dvc/tmp/" in self._content(), ".dvc/tmp/ doit être dans .gitignore"

    def test_keras_files_excluded(self) -> None:
        """Les .keras restent trackés via DVC, pas git."""
        assert "*.keras" in self._content(), "*.keras doit être dans .gitignore"

    def test_artifacts_excluded_with_dvc_exception(self) -> None:
        content = self._content()
        assert "artifacts/*" in content
        assert "!artifacts/*.dvc" in content or "!artifacts/models.dvc" in content
