"""Tests smoke : les deux problèmes de segmentation sont PURS.

Le U-Net multitâche possède une tête de classification, mais elle s'est
révélée très peu fiable en production (NORMAL annoncé à 1.000 sur des
pneumonies manifestes, le 2026-07-18). Décision produit : ces écrans
délimitent des zones et ne posent AUCUN diagnostic — la tête n'est ni
exécutée ni affichée. Ces tests verrouillent cette règle.

Y sont aussi vérifiés les modèles convnexttiny désactivés (leur export
ONNX est invalide, en attente d'un ré-export sur la machine ML).
"""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from src.api.main import create_app
from src.registry.model_registry import PROBLEMS, load_registry

SEGMENTATION_PROBLEMS = ("brain_tumor_segmentation", "chest_xray_segmentation")


# ── Registre : libellés, type de tâche, convnexttiny ───────────────────────


def test_libelles_sans_mention_de_classification() -> None:
    """Les libellés affichés ne promettent plus de classification."""
    for problem in SEGMENTATION_PROBLEMS:
        label = PROBLEMS[problem]["label"]
        assert "Classification" not in label, label
        assert "Segmentation" in label, label
    assert PROBLEMS["brain_tumor_segmentation"]["label"] == "Brain Tumor Segmentation"
    assert PROBLEMS["chest_xray_segmentation"]["label"] == "Chest X-ray Lung Segmentation"


def test_task_type_segmentation_pure(tmp_path: Path) -> None:
    """Le type de tâche est « segmentation » (et plus « segmentation_multitask »)."""
    registry = load_registry(tmp_path)
    for problem in SEGMENTATION_PROBLEMS:
        assert registry["problems"][problem]["task_type"] == "segmentation"
    # Les problèmes de classification gardent bien leur type d'origine.
    assert registry["problems"]["chest_xray"]["task_type"] == "binary"
    assert registry["problems"]["brain_mri"]["task_type"] == "multiclass"


def test_convnexttiny_absent_du_registre() -> None:
    """Les 2 variantes convnexttiny (export ONNX invalide) restent désactivées."""
    assert "convnexttiny" not in PROBLEMS["chest_xray"]["model_candidates"]
    assert "convnexttiny" not in PROBLEMS["brain_mri"]["model_candidates"]
    registry = load_registry("artifacts")
    assert "convnexttiny" not in registry["problems"]["chest_xray"]["models"]
    assert "convnexttiny" not in registry["problems"]["brain_mri"]["models"]


# ── API v2 : la prédiction ne rend QUE le masque ───────────────────────────


class _FakeSession:
    """Session ONNX factice exposant les deux têtes du U-Net."""

    def __init__(self, outputs: dict[str, np.ndarray]) -> None:
        self._outputs = outputs

    def get_inputs(self):
        return [SimpleNamespace(name="input", shape=[1, 256, 256, 3])]

    def get_outputs(self):
        return [SimpleNamespace(name=n) for n in self._outputs]

    def run(self, _names, _feed):
        return list(self._outputs.values())


def _png(size: int = 64) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), color=(80, 90, 100)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_api_predict_segmentation_sans_diagnostic(tmp_path: Path, monkeypatch) -> None:
    """Le résultat contient le masque, et AUCUN champ de classification.

    Le modèle factice renvoie pourtant une tête de classification très
    affirmative : elle doit être ignorée de bout en bout.
    """
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    (artifacts / "models" / "chest_xray_segmentation_unet.onnx").write_bytes(b"x")

    seg = np.zeros((1, 256, 256, 1), dtype=np.float32)
    seg[0, 60:180, 40:210, 0] = 0.95  # une « zone pulmonaire »
    monkeypatch.setattr(
        "src.api.services.session_cache.create_onnx_session",
        lambda _p: _FakeSession(
            {
                "segmentation_output": seg,
                # Tête de classification volontairement absurde (NORMAL à 1.0).
                "classification_output": np.array([[0.0]], dtype=np.float32),
            }
        ),
    )

    client = TestClient(create_app(artifacts_dir=artifacts, data_root=tmp_path))
    resp = client.post(
        "/api/predict",
        data={
            "problem": "chest_xray_segmentation",
            "model_names": ["unet_multitask"],
            "mask_threshold": "0.5",
        },
        files={"file": ("radio.png", _png(), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Plus de second avis dans la réponse : l'écran est purement segmentation.
    assert "second_opinion" not in body

    result = body["results"][0]
    assert "predicted_class" not in result
    assert "confidence" not in result
    assert "probabilities" not in result

    segmentation = result["segmentation"]
    assert 0.0 < segmentation["mask_foreground_ratio"] < 1.0
    assert segmentation["mask_prob_png"]  # la carte de probabilité reste servie
    assert segmentation["threshold"] == 0.5


def test_api_predict_classification_inchangee(tmp_path: Path, monkeypatch) -> None:
    """Les problèmes de classification gardent prédiction et probabilités."""
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    (artifacts / "models" / "optimized_model.onnx").write_bytes(b"x")
    monkeypatch.setattr(
        "src.api.services.session_cache.create_onnx_session",
        lambda _p: _FakeSession({"output": np.array([[0.83]], dtype=np.float32)}),
    )

    client = TestClient(create_app(artifacts_dir=artifacts, data_root=tmp_path))
    resp = client.post(
        "/api/predict",
        data={"problem": "chest_xray", "model_names": ["optimized"]},
        files={"file": ("radio.png", _png(), "image/png")},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["predicted_class"] == "PNEUMONIA"
    assert set(result["probabilities"]) == {"NORMAL", "PNEUMONIA"}
    assert "segmentation" not in result


def test_api_problems_libelles_et_types(tmp_path: Path) -> None:
    """La liste des problèmes servie à l'UI reflète la segmentation pure."""
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    client = TestClient(create_app(artifacts_dir=artifacts, data_root=tmp_path))
    problems = {p["id"]: p for p in client.get("/api/problems").json()}
    for problem in SEGMENTATION_PROBLEMS:
        assert problems[problem]["task_type"] == "segmentation"
        assert "Classification" not in problems[problem]["label"]
