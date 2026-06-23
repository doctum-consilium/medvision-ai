"""Smoke léger de l'API FastAPI (sans TF, sans vrai modèle, sans grosse image).

Le job smoke ne lançait que tests/smoke/ ; `tests/test_api.py` (qui couvre
src/api/main.py) vivait à la racine et n'était donc jamais mesuré → main.py à 0 %
dans la couverture du diff. On ajoute ici des tests TestClient + helpers, en
mockant tout ce qui est lourd (chargement ONNX, prétraitement image) et avec des
tableaux minuscules — pensés pour les runners GitHub modestes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

import src.api.main as M  # noqa: E402
from src.registry.model_registry import ModelNotFoundError  # noqa: E402


class _FakeSession:
    """Session ONNX factice : I/O nommés + sortie minuscule."""

    def get_inputs(self):
        return [type("I", (), {"name": "input"})()]

    def get_outputs(self):
        return [type("O", (), {"name": "output"})()]

    def run(self, _outputs, _feed):
        return [np.array([[0.2, 0.8]], dtype=np.float32)]


# ── Helpers purs ──────────────────────────────────────────────────────────────
def test_run_onnx_maps_outputs_by_name():
    out = M._run_onnx(_FakeSession(), np.zeros((4, 4, 3), dtype=np.float32))
    assert "output" in out
    assert out["output"].shape == (1, 2)


def test_classification_payload_binary_and_multiclass():
    binary = M._classification_payload(
        np.array([0.8]), {"class_names": ["neg", "pos"], "task_type": "binary"})
    assert binary["predicted_class"] == "pos"
    assert 0.0 <= binary["confidence"] <= 1.0

    multi = M._classification_payload(
        np.array([0.1, 0.7, 0.2]), {"class_names": ["a", "b", "c"], "task_type": "multiclass"})
    assert multi["predicted_class"] == "b"
    assert set(multi["probabilities"]) == {"a", "b", "c"}


def _patch_inference(monkeypatch, raw: dict[str, Any]):
    monkeypatch.setattr(M, "load_onnx_model", lambda _p: _FakeSession())
    monkeypatch.setattr(M, "load_and_preprocess_image", lambda _p, image_size=224: np.zeros((4, 4, 3), np.float32))
    monkeypatch.setattr(M, "_run_onnx", lambda _s, _i: raw)


def test_predict_with_entry_classification(monkeypatch):
    # Binaire = une seule probabilité (sigmoïde) ≥ 0.5 → classe positive.
    _patch_inference(monkeypatch, {"output": np.array([[0.8]], dtype=np.float32)})
    res = M._predict_with_entry(
        {"model_path": "x.onnx", "class_names": ["neg", "pos"], "task_type": "binary"},
        Path("img.png"))
    assert res["predicted_class"] == "pos"


def test_predict_with_entry_segmentation(monkeypatch):
    raw = {
        "segmentation_output": np.zeros((1, 4, 4, 1), dtype=np.float32),
        "class_output": np.array([[0.2, 0.8]], dtype=np.float32),
    }
    _patch_inference(monkeypatch, raw)
    res = M._predict_with_entry(
        {"model_path": "x.onnx", "class_names": ["neg", "pos"], "task_type": "segmentation_multitask"},
        Path("img.png"))
    assert "mask_foreground_ratio" in res
    assert res["mask_shape"] == [4, 4]


# ── Endpoints (TestClient, tout mocké) ────────────────────────────────────────
@pytest.fixture
def client():
    return TestClient(M.app, raise_server_exceptions=False)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_registry_and_models(client, monkeypatch):
    reg = {"problems": {"chest_xray": {"models": ["m1"]}}}
    monkeypatch.setattr(M, "load_registry", lambda: reg)
    assert client.get("/registry").json() == reg
    assert client.get("/models").json() == reg
    assert client.get("/models", params={"problem": "chest_xray"}).status_code == 200
    assert client.get("/models", params={"problem": "inconnu"}).status_code == 404


def test_compare(client, monkeypatch):
    monkeypatch.setattr(M, "compare_models", lambda p: [{"model": "m1"}])
    assert client.get("/compare", params={"problem": "chest_xray"}).status_code == 200

    def _raise(_p):
        raise KeyError("problème inconnu")
    monkeypatch.setattr(M, "compare_models", _raise)
    assert client.get("/compare", params={"problem": "x"}).status_code == 404


def test_predict_endpoint(client, monkeypatch):
    monkeypatch.setattr(M, "get_model_entry",
                        lambda p, m: {"model_path": "x.onnx", "class_names": ["neg", "pos"],
                                      "task_type": "binary", "metrics": {}})
    monkeypatch.setattr(M, "_predict_with_entry",
                        lambda *a, **k: {"predicted_class": "pos", "confidence": 0.8,
                                         "probabilities": {"neg": 0.2, "pos": 0.8}})
    r = client.post("/predict", params={"problem": "chest_xray", "model_name": "m1"},
                    files={"file": ("scan.png", b"\x89PNG\r\n", "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["predicted_class"] == "pos"
    assert body["model_name"] == "m1"


def test_predict_with_entry_maps_errors_to_http(monkeypatch):
    """Modèle absent → 404 ; toute autre erreur de chargement → 500."""
    from fastapi import HTTPException

    entry = {"model_path": "x.onnx", "class_names": ["neg", "pos"], "task_type": "binary"}

    def _not_found(_p):
        raise ModelNotFoundError("ghost.onnx introuvable")
    monkeypatch.setattr(M, "load_onnx_model", _not_found)
    with pytest.raises(HTTPException) as exc404:
        M._predict_with_entry(entry, Path("img.png"))
    assert exc404.value.status_code == 404

    def _boom(_p):
        raise RuntimeError("session corrompue")
    monkeypatch.setattr(M, "load_onnx_model", _boom)
    with pytest.raises(HTTPException) as exc500:
        M._predict_with_entry(entry, Path("img.png"))
    assert exc500.value.status_code == 500


def _fake_onnxruntime(monkeypatch, *, session_factory):
    """Injecte un faux module onnxruntime (le vrai n'est pas requis pour ces tests)."""
    import sys
    import types

    fake = types.ModuleType("onnxruntime")

    class _Opts:
        log_severity_level = 0

    fake.SessionOptions = _Opts
    fake.InferenceSession = session_factory
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)


def test_load_onnx_model_missing_file_needs_no_runtime(tmp_path):
    """Fichier absent → ModelNotFoundError, SANS dépendre d'onnxruntime."""
    from src.registry.model_registry import ModelNotFoundError, load_onnx_model

    with pytest.raises(ModelNotFoundError):
        load_onnx_model(str(tmp_path / "ghost.onnx"))


def test_load_onnx_model_success_with_mocked_runtime(tmp_path, monkeypatch):
    """Avec un runtime (mocké) : la session est retournée (import + opts + session)."""
    from src.registry.model_registry import load_onnx_model

    m = tmp_path / "m.onnx"
    m.write_bytes(b"x")
    _fake_onnxruntime(monkeypatch, session_factory=lambda *a, **k: "SESSION")
    assert load_onnx_model(str(m)) == "SESSION"


def test_load_onnx_model_wraps_session_failure(tmp_path, monkeypatch):
    """Échec de désérialisation de la session → ModelLoadError (couvre le except)."""
    from src.registry.model_registry import ModelLoadError, load_onnx_model

    m = tmp_path / "m.onnx"
    m.write_bytes(b"x")

    def _boom(*_a, **_k):
        raise RuntimeError("modèle corrompu")
    _fake_onnxruntime(monkeypatch, session_factory=_boom)
    with pytest.raises(ModelLoadError):
        load_onnx_model(str(m))
