"""Tests smoke du cache LRU de sessions ONNX et du registre versionné."""
from __future__ import annotations

from pathlib import Path

from src.api.services.registry_state import RegistryState
from src.api.services.session_cache import OnnxSessionCache


def _patch_creation(monkeypatch, created: list[str]) -> None:
    """Remplace la création de session par un enregistreur d'appels."""
    monkeypatch.setattr(
        "src.api.services.session_cache.create_onnx_session",
        lambda path: created.append(path) or f"session-{path}",
    )


def test_session_cache_reuses_and_evicts_lru(monkeypatch) -> None:
    """Une session est réutilisée tant qu'elle est chaude ; au-delà de la
    borne, la moins récemment utilisée est évincée (protection RAM du pod)."""
    created: list[str] = []
    _patch_creation(monkeypatch, created)
    cache = OnnxSessionCache(max_sessions=2)

    cache.get("a.onnx")
    cache.get("b.onnx")
    cache.get("a.onnx")  # hit : aucune création
    assert created == ["a.onnx", "b.onnx"]
    assert len(cache) == 2

    cache.get("c.onnx")  # évince b (a vient d'être touché)
    assert len(cache) == 2
    cache.get("a.onnx")  # toujours chaud
    assert created == ["a.onnx", "b.onnx", "c.onnx"]
    cache.get("b.onnx")  # b a été évincé → re-création
    assert created[-1] == "b.onnx"


def test_session_cache_clear(monkeypatch) -> None:
    """clear() (appelé après un dvc pull) force la re-création des sessions."""
    created: list[str] = []
    _patch_creation(monkeypatch, created)
    cache = OnnxSessionCache(max_sessions=2)
    cache.get("a.onnx")
    cache.clear()
    assert len(cache) == 0
    cache.get("a.onnx")
    assert created == ["a.onnx", "a.onnx"]


def test_registry_state_version_changes_with_models(tmp_path: Path) -> None:
    """La version du registre change quand un .onnx apparaît, et le refresh
    rapporte le modèle devenu disponible (alimente l'événement SSE)."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    state = RegistryState(artifacts_dir=tmp_path)
    version_empty = state.version

    (models_dir / "optimized_model.onnx").write_bytes(b"onnx")
    new_version, newly_available = state.refresh()

    assert new_version != version_empty
    assert newly_available == ["chest_xray/optimized"]
    assert state.version == new_version

    # Refresh sans changement : version stable, rien de nouveau.
    same_version, nothing_new = state.refresh()
    assert same_version == new_version
    assert nothing_new == []
