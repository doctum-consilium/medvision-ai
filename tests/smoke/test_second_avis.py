"""Tests smoke : modèles désactivés (convnexttiny) et « second avis ».

Le second avis = sur un problème de segmentation, le verdict du MEILLEUR
classifieur dédié du problème frère accompagne celui du U-Net multitâche
(dont la tête de classification s'est révélée très faible en prod).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.api.main import create_app
from src.registry.model_registry import PROBLEMS, best_available_model, load_registry

# ── convnexttiny désactivé ─────────────────────────────────────────────────


def test_convnexttiny_absent_du_registre() -> None:
    """Les 2 variantes convnexttiny (export ONNX invalide) sont désactivées."""
    assert "convnexttiny" not in PROBLEMS["chest_xray"]["model_candidates"]
    assert "convnexttiny" not in PROBLEMS["brain_mri"]["model_candidates"]
    registry = load_registry("artifacts")
    assert "convnexttiny" not in registry["problems"]["chest_xray"]["models"]
    assert "convnexttiny" not in registry["problems"]["brain_mri"]["models"]


def test_companion_problem_expose_dans_le_registre(tmp_path: Path) -> None:
    """Les problèmes de segmentation déclarent leur problème frère."""
    registry = load_registry(tmp_path)
    problems = registry["problems"]
    assert problems["chest_xray_segmentation"]["companion_problem"] == "chest_xray"
    assert problems["brain_tumor_segmentation"]["companion_problem"] == "brain_mri"
    assert problems["chest_xray"]["companion_problem"] is None


# ── best_available_model ───────────────────────────────────────────────────


def _make_artifacts(tmp_path: Path, models: dict[str, float | None]) -> Path:
    """Crée artifacts/ avec des .onnx factices et leurs métriques d'accuracy.

    Args:
        tmp_path: Répertoire de test.
        models: {nom_de_modèle_chest: accuracy ou None (pas de métriques)}.
    """
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True, exist_ok=True)
    (artifacts / "reports").mkdir(parents=True, exist_ok=True)
    filenames = PROBLEMS["chest_xray"]["model_candidates"]
    metrics_names = PROBLEMS["chest_xray"]["metrics_candidates"]
    for name, accuracy in models.items():
        (artifacts / "models" / filenames[name]).write_bytes(b"onnx")
        if accuracy is not None:
            (artifacts / "reports" / metrics_names[name][0]).write_text(
                json.dumps({"accuracy": accuracy})
            )
    return artifacts


def test_best_available_model_choisit_par_accuracy(tmp_path: Path) -> None:
    """Le modèle disponible avec la meilleure accuracy gagne."""
    artifacts = _make_artifacts(
        tmp_path, {"baseline": 0.71, "densenet121": 0.93, "optimized": 0.88}
    )
    best = best_available_model("chest_xray", artifacts_dir=artifacts)
    assert best is not None
    name, entry = best
    assert name == "densenet121"
    assert entry["task_type"] == "binary"
    assert entry["class_names"] == ["NORMAL", "PNEUMONIA"]


def test_best_available_model_sans_metriques_ni_modeles(tmp_path: Path) -> None:
    """Sans métriques : un disponible est quand même choisi ; sans modèle : None."""
    artifacts = _make_artifacts(tmp_path, {"optimized": None})
    best = best_available_model("chest_xray", artifacts_dir=artifacts)
    assert best is not None and best[0] == "optimized"

    empty = tmp_path / "vide"
    (empty / "models").mkdir(parents=True)
    assert best_available_model("chest_xray", artifacts_dir=empty) is None
    assert best_available_model("probleme_inconnu", artifacts_dir=empty) is None


# ── Second avis de bout en bout (API v2) ───────────────────────────────────


class _FakeSession:
    """Session factice dont les sorties dépendent du modèle chargé."""

    def __init__(self, outputs: dict[str, np.ndarray]) -> None:
        self._outputs = outputs

    def get_inputs(self):
        return [SimpleNamespace(name="input", shape=[1, 224, 224, 3])]

    def get_outputs(self):
        return [SimpleNamespace(name=n) for n in self._outputs]

    def run(self, _n, _f):
        return list(self._outputs.values())


def test_api_predict_segmentation_ajoute_le_second_avis(tmp_path: Path, monkeypatch) -> None:
    """La réponse de segmentation contient le verdict du meilleur classifieur frère."""
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    (artifacts / "reports").mkdir(parents=True)
    (artifacts / "models" / "brain_tumor_segmentation_unet.onnx").write_bytes(b"x")
    # Deux classifieurs brain_mri disponibles — le mieux noté doit être choisi.
    (artifacts / "models" / "brain_mri_baseline.onnx").write_bytes(b"x")
    (artifacts / "models" / "brain_mri_densenet121.onnx").write_bytes(b"x")
    (artifacts / "reports" / "brain_mri_baseline_metrics.json").write_text('{"accuracy": 0.61}')
    (artifacts / "reports" / "brain_mri_densenet121_metrics.json").write_text('{"accuracy": 0.94}')

    app = create_app(artifacts_dir=artifacts, data_root=tmp_path)
    client = TestClient(app)

    seg = np.zeros((1, 256, 256, 1), dtype=np.float32)
    seg[0, 50:80, 50:80, 0] = 0.9

    def fake_session(path: str):
        # Le U-Net répond « pituitary tumor » ; le classifieur dédié « glioma ».
        # NB : le U-Net de segmentation n'a que 3 classes (elles viennent du
        # YAML configs/brain_tumor_segmentation.yaml), là où le classifieur
        # brain_mri en a 4 — d'où deux vecteurs de tailles différentes.
        if "unet" in path:
            return _FakeSession(
                {
                    "segmentation_output": seg,
                    "classification_output": np.array([[0.1, 0.2, 0.7]], dtype=np.float32),
                }
            )
        return _FakeSession({"output": np.array([[0.8, 0.1, 0.05, 0.05]], dtype=np.float32)})

    monkeypatch.setattr("src.api.services.session_cache.create_onnx_session", fake_session)

    import io

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(90, 90, 90)).save(buffer, format="PNG")
    resp = client.post(
        "/api/predict",
        data={"problem": "brain_tumor_segmentation", "model_names": ["unet_multitask"]},
        files={"file": ("mri.png", buffer.getvalue(), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Le U-Net a répondu, ET le second avis vient du MEILLEUR classifieur frère.
    assert body["results"][0]["predicted_class"] == "pituitary tumor"
    opinion = body["second_opinion"]
    assert opinion is not None
    assert opinion["problem"] == "brain_mri"
    assert opinion["model_name"] == "densenet121"
    assert opinion["predicted_class"] == "glioma"
    assert opinion["confidence"] == pytest.approx(0.8)


def test_api_predict_classification_sans_second_avis(tmp_path: Path, monkeypatch) -> None:
    """Un problème de classification pure n'a pas de second avis."""
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    (artifacts / "models" / "optimized_model.onnx").write_bytes(b"x")
    app = create_app(artifacts_dir=artifacts, data_root=tmp_path)
    client = TestClient(app)

    monkeypatch.setattr(
        "src.api.services.session_cache.create_onnx_session",
        lambda _p: _FakeSession({"output": np.array([[0.7]], dtype=np.float32)}),
    )
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(10, 10, 10)).save(buffer, format="PNG")
    resp = client.post(
        "/api/predict",
        data={"problem": "chest_xray", "model_names": ["optimized"]},
        files={"file": ("scan.png", buffer.getvalue(), "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["second_opinion"] is None
