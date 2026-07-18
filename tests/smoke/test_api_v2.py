"""Tests smoke de l'API v2 (/api/*) consommée par le front Angular.

Sans onnxruntime réel : l'inférence est testée via une fausse session
(monkeypatch de `create_onnx_session`) qui rejoue les formes de sortie des
vrais modèles. Tout le reste — routes, registre versionné, index d'images,
cache de sessions, encodage PNG des masques — est exercé pour de vrai.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.api.main import create_app
from src.registry.model_registry import ModelNotFoundError

# ── Fixtures ───────────────────────────────────────────────────────────────


def _write_png(path: Path, size: int = 24) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), color=(40, 80, 120)).save(path)
    return path


@pytest.fixture()
def app_env(tmp_path: Path):
    """App de test : artifacts et datasets isolés dans tmp_path.

    Crée un faux .onnx (fichier non vide : seul `exists()` compte pour le
    registre, la session est monkeypatchée) et deux images chest_xray.
    """
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    (artifacts / "models" / "optimized_model.onnx").write_bytes(b"fake-onnx")

    _write_png(tmp_path / "data/raw/chest_xray/test/NORMAL/n1.png")
    _write_png(tmp_path / "data/raw/chest_xray/test/PNEUMONIA/p1.png")

    app = create_app(artifacts_dir=artifacts, data_root=tmp_path)
    return app, TestClient(app), tmp_path


class _FakeSession:
    """Session ONNX factice : rejoue les formes de sortie des vrais modèles.

    Args:
        outputs: Sorties simulées {nom: array}.
        input_shape: Forme d'entrée déclarée (NHWC par défaut, NCHW pour
            simuler un export PyTorch).
    """

    def __init__(
        self, outputs: dict[str, np.ndarray], input_shape: list | None = None
    ) -> None:
        self._outputs = outputs
        self._input_shape = input_shape or [1, 224, 224, 3]
        self.received_feeds: list[dict] = []

    def get_inputs(self):
        return [SimpleNamespace(name="input", shape=self._input_shape)]

    def get_outputs(self):
        return [SimpleNamespace(name=name) for name in self._outputs]

    def run(self, _names, feed):
        self.received_feeds.append(feed)
        return list(self._outputs.values())


def _patch_session(monkeypatch, outputs: dict[str, np.ndarray]) -> None:
    """Substitue la création de session ONNX par la fausse session donnée.

    Respecte le contrat de `create_onnx_session` : un .onnx absent lève
    ModelNotFoundError (c'est ce qui alimente l'erreur par modèle).
    """

    def _fake(path: str):
        if not Path(path).exists():
            raise ModelNotFoundError(f"{Path(path).name} introuvable.")
        return _FakeSession(outputs)

    monkeypatch.setattr("src.api.services.session_cache.create_onnx_session", _fake)


# ── Santé / problèmes / modèles ────────────────────────────────────────────


def test_api_health_exposes_registry_version(app_env) -> None:
    """La sonde v2 expose l'état ET la version du registre."""
    _, client, _ = app_env
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["registry_version"]


def test_api_problems_lists_the_four_problems_with_counters(app_env) -> None:
    """4 problèmes, compteurs disponibles/total cohérents avec les fichiers."""
    _, client, _ = app_env
    problems = {p["id"]: p for p in client.get("/api/problems").json()}
    assert set(problems) == {
        "chest_xray",
        "brain_mri",
        "brain_tumor_segmentation",
        "chest_xray_segmentation",
    }
    chest = problems["chest_xray"]
    assert chest["models_total"] == 6
    assert chest["models_available"] == 1  # seul optimized_model.onnx existe
    assert problems["brain_mri"]["models_available"] == 0


def test_api_models_enriched_and_versioned(app_env) -> None:
    """Le registre v2 ajoute version, taille et date aux modèles disponibles."""
    _, client, _ = app_env
    body = client.get("/api/models", params={"problem": "chest_xray"}).json()
    assert body["version"] == client.get("/api/models/version").json()["version"]
    optimized = body["problems"]["chest_xray"]["models"]["optimized"]
    assert optimized["available"] is True
    assert optimized["size_bytes"] == len(b"fake-onnx")
    assert optimized["modified_at"] is not None
    baseline = body["problems"]["chest_xray"]["models"]["baseline"]
    assert baseline["available"] is False
    assert baseline["size_bytes"] is None
    assert client.get("/api/models", params={"problem": "nope"}).status_code == 404


def test_api_compare_rows(app_env) -> None:
    """Le comparatif renvoie une ligne par modèle du problème."""
    _, client, _ = app_env
    body = client.get("/api/compare", params={"problem": "chest_xray"}).json()
    assert len(body["rows"]) == 6
    assert client.get("/api/compare", params={"problem": "nope"}).status_code == 404


# ── Navigateur d'images ────────────────────────────────────────────────────


def test_api_images_pagination_and_security(app_env) -> None:
    """Liste paginée sans chemins disque ; fichier servi par sample_id seul."""
    _, client, _ = app_env
    body = client.get("/api/images", params={"problem": "chest_xray"}).json()
    assert body["total"] == 2
    assert {item["label"] for item in body["items"]} == {"NORMAL", "PNEUMONIA"}
    # Jamais de chemin dans la réponse publique.
    assert all("path" not in item for item in body["items"])
    assert len(body["recommended"]) == 2

    sample_id = body["items"][0]["sample_id"]
    file_resp = client.get(f"/api/images/{sample_id}/file", params={"problem": "chest_xray"})
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"] == "image/jpeg"
    # Un id inconnu (ou un chemin déguisé) → 404, jamais d'accès disque.
    assert (
        client.get("/api/images/sample-ffffffffff/file", params={"problem": "chest_xray"}).status_code
        == 404
    )
    assert client.get("/api/images", params={"problem": "nope"}).status_code == 404


def test_api_images_label_filter(app_env) -> None:
    """Le filtre de classes réduit la liste."""
    _, client, _ = app_env
    body = client.get(
        "/api/images", params={"problem": "chest_xray", "labels": "NORMAL"}
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["label"] == "NORMAL"


# ── Prédiction ─────────────────────────────────────────────────────────────


def _png_bytes(size: int = 32) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), color=(200, 100, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_api_predict_requires_exactly_one_image_source(app_env) -> None:
    """Ni fichier ni sample_id (ou les deux) → 400 explicite."""
    _, client, _ = app_env
    resp = client.post("/api/predict", data={"problem": "chest_xray", "model_names": ["optimized"]})
    assert resp.status_code == 400


def test_api_predict_unknown_problem_and_sample(app_env) -> None:
    """Problème inconnu → 404 ; sample_id inconnu → 404."""
    _, client, _ = app_env
    assert (
        client.post(
            "/api/predict",
            data={"problem": "nope", "model_names": ["optimized"], "sample_id": "sample-00"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/predict",
            data={"problem": "chest_xray", "model_names": ["optimized"], "sample_id": "sample-00"},
        ).status_code
        == 404
    )


def test_api_predict_classification_multi_models(app_env, monkeypatch) -> None:
    """Upload + 2 modèles : un OK (probas binaires), un absent (erreur inline)."""
    _, client, _ = app_env
    _patch_session(monkeypatch, {"output": np.array([[0.9]], dtype=np.float32)})

    resp = client.post(
        "/api/predict",
        data={"problem": "chest_xray", "model_names": ["optimized", "baseline"]},
        files={"file": ("scan.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["image"]["source"] == "upload"
    by_name = {r["model_name"]: r for r in body["results"]}

    ok = by_name["optimized"]
    assert ok["predicted_class"] == "PNEUMONIA"
    assert ok["probabilities"]["PNEUMONIA"] == pytest.approx(0.9)
    # baseline n'a pas de .onnx : erreur par modèle, pas de 500 global.
    assert "error" in by_name["baseline"]


def test_api_predict_segmentation_returns_probability_png(app_env, monkeypatch) -> None:
    """Segmentation : la carte de probabilité revient en PNG base64 décodable."""
    _, client, tmp_path = app_env
    # Le fichier .onnx du modèle unet doit exister pour la session (factice).
    (tmp_path / "artifacts/models/brain_tumor_segmentation_unet.onnx").write_bytes(b"x")
    seg = np.zeros((1, 256, 256, 1), dtype=np.float32)
    seg[0, 100:150, 100:150, 0] = 0.8  # un carré « tumeur »
    _patch_session(
        monkeypatch,
        {
            "segmentation_output": seg,
            "classification_output": np.array([[0.7, 0.1, 0.1, 0.1]], dtype=np.float32),
        },
    )

    resp = client.post(
        "/api/predict",
        data={
            "problem": "brain_tumor_segmentation",
            "model_names": ["unet_multitask"],
            "mask_threshold": "0.5",
        },
        files={"file": ("mri.png", _png_bytes(64), "image/png")},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["predicted_class"] == "glioma"
    segmentation = result["segmentation"]
    assert segmentation["threshold"] == pytest.approx(0.5)
    assert 0.0 < segmentation["mask_foreground_ratio"] < 1.0

    # Le PNG est décodable et garde la résolution du modèle (256×256).
    mask_img = Image.open(io.BytesIO(base64.b64decode(segmentation["mask_prob_png"])))
    assert mask_img.size == (256, 256)
    preview = Image.open(io.BytesIO(base64.b64decode(segmentation["preprocessed_png"])))
    assert preview.mode == "RGB"


def test_api_predict_from_dataset_sample(app_env, monkeypatch) -> None:
    """La prédiction accepte un sample_id du navigateur à la place d'un upload."""
    _, client, _ = app_env
    _patch_session(monkeypatch, {"output": np.array([[0.2]], dtype=np.float32)})
    sample_id = client.get("/api/images", params={"problem": "chest_xray"}).json()["items"][0][
        "sample_id"
    ]

    resp = client.post(
        "/api/predict",
        data={"problem": "chest_xray", "model_names": ["optimized"], "sample_id": sample_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["image"] == {"source": "dataset", "sample_id": sample_id}
    assert body["results"][0]["predicted_class"] == "NORMAL"


def test_format_model_input_layouts() -> None:
    """NHWC pour Keras, NCHW pour les exports PyTorch (lu sur la session).

    Verrouille l'incident 2026-07-18 : les 3 modèles torch échouaient en
    INVALID_ARGUMENT car l'app envoyait du NHWC à des modèles NCHW.
    """
    from src.registry.model_registry import format_model_input

    image = np.zeros((224, 224, 3), dtype=np.float32)

    keras_session = _FakeSession({}, input_shape=[1, 224, 224, 3])
    assert format_model_input(keras_session, image).shape == (1, 224, 224, 3)

    torch_session = _FakeSession({}, input_shape=[1, 3, 224, 224])
    assert format_model_input(torch_session, image).shape == (1, 3, 224, 224)

    # Dimension batch symbolique (chaîne) : le layout reste détecté.
    torch_dyn = _FakeSession({}, input_shape=["batch", 3, 224, 224])
    assert format_model_input(torch_dyn, image).shape == (1, 3, 224, 224)


def test_api_predict_transposes_for_torch_models(app_env, monkeypatch) -> None:
    """Bout en bout : un modèle NCHW reçoit bien un batch transposé."""
    _, client, _ = app_env
    session = _FakeSession(
        {"output": np.array([[0.1, 0.2, 0.6, 0.1]], dtype=np.float32)},
        input_shape=[1, 3, 224, 224],
    )

    def _fake(path: str):
        if not Path(path).exists():
            raise ModelNotFoundError(f"{Path(path).name} introuvable.")
        return session

    monkeypatch.setattr("src.api.services.session_cache.create_onnx_session", _fake)

    resp = client.post(
        "/api/predict",
        data={"problem": "chest_xray", "model_names": ["optimized"]},
        files={"file": ("scan.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 200
    assert session.received_feeds[0]["input"].shape == (1, 3, 224, 224)


# ── Rapports ───────────────────────────────────────────────────────────────


def test_api_reports_metrics_and_missing_report(app_env) -> None:
    """Métriques présentes, rapport texte None si non tiré sur le pod."""
    app, client, tmp_path = app_env
    reports_dir = tmp_path / "artifacts" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "optimized_metrics.json").write_text('{"accuracy": 0.91}')
    resp = client.get("/api/reports", params={"problem": "chest_xray", "model": "optimized"})
    assert resp.status_code == 200
    # Le registre est un instantané en mémoire : forcer un refresh pour
    # qu'il voie le fichier de métriques écrit après la création de l'app.
    app.state.registry_state.refresh()
    body = client.get("/api/reports", params={"problem": "chest_xray", "model": "optimized"}).json()
    assert body["metrics"] == {"accuracy": 0.91}
    assert body["classification_report"] is None
    assert (
        client.get("/api/reports", params={"problem": "chest_xray", "model": "nope"}).status_code
        == 404
    )


# ── Endpoints historiques toujours vivants ─────────────────────────────────


def test_legacy_endpoints_still_work(app_env) -> None:
    """/health et /registry (sans préfixe) restent servis pendant la coexistence."""
    _, client, _ = app_env
    assert client.get("/health").json() == {"status": "ok"}
    assert "problems" in client.get("/registry").json()
