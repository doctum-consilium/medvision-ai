"""Tests smoke du watcher DVC et du flux SSE (/api/events).

Sans S3 ni dvc réels : le client S3 est un faux injecté, le `dvc pull` est
monkeypatché. On vérifie la MACHINE À ÉTATS du watcher (veille, détection
d'ETag, invalidations, diffusion SSE) et le format du flux événements.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.api.main import create_app
from src.api.services.broadcaster import EventBroadcaster
from src.api.services.registry_state import RegistryState
from src.api.services.watcher import ModelWatcher, WatcherConfig, _split_s3_uri


@pytest.fixture
def anyio_backend():
    """Backend anyio des tests async (asyncio uniquement, pas trio)."""
    return "asyncio"


# ── Broadcaster ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_broadcaster_fans_out_to_all_subscribers() -> None:
    """Chaque abonné reçoit chaque événement, au format SSE."""
    broadcaster = EventBroadcaster()
    q1, q2 = await broadcaster.subscribe(), await broadcaster.subscribe()

    await broadcaster.publish("models_updated", {"version": "abc"})

    for queue in (q1, q2):
        payload = queue.get_nowait()
        assert payload.startswith("event: models_updated\n")
        assert json.loads(payload.split("data: ", 1)[1].strip()) == {"version": "abc"}

    await broadcaster.unsubscribe(q1)
    await broadcaster.publish("models_updated", {"version": "def"})
    assert q1.empty()  # désinscrit : ne reçoit plus rien
    assert await broadcaster.subscriber_count() == 1


@pytest.mark.anyio
async def test_broadcaster_full_queue_drops_for_that_client_only() -> None:
    """Un client gelé (queue pleine) perd SES événements, pas ceux des autres."""
    broadcaster = EventBroadcaster(max_queue_size=1)
    frozen, healthy = await broadcaster.subscribe(), await broadcaster.subscribe()

    await broadcaster.publish("e", {"n": 1})
    healthy.get_nowait()  # le client sain consomme au fil de l'eau
    await broadcaster.publish("e", {"n": 2})  # frozen est plein → jeté pour LUI

    assert frozen.qsize() == 1  # n'a reçu que le premier événement
    payload = healthy.get_nowait()  # le client sain reçoit bien le second
    assert json.loads(payload.split("data: ", 1)[1].strip()) == {"n": 2}


# ── Watcher ────────────────────────────────────────────────────────────────


def test_split_s3_uri_valid_and_invalid() -> None:
    """L'URI s3:// est découpée, les formes invalides lèvent ValueError."""
    assert _split_s3_uri("s3://bucket/a/b.lock") == ("bucket", "a/b.lock")
    with pytest.raises(ValueError):
        _split_s3_uri("http://bucket/key")
    with pytest.raises(ValueError):
        _split_s3_uri("s3://bucket-sans-cle")


class _FakeS3:
    """Faux client S3 : ETag contrôlé par le test, download traçable."""

    def __init__(self) -> None:
        self.etag: str | None = None
        self.downloads: list[tuple[str, str, str]] = []

    def head_object(self, Bucket: str, Key: str):  # noqa: N803 — API boto3
        if self.etag is None:
            raise RuntimeError("404 Not Found")
        return {"ETag": self.etag}

    def download_file(self, bucket: str, key: str, dest: str) -> None:
        self.downloads.append((bucket, key, dest))
        Path(dest).write_text("locked")


def _make_watcher(tmp_path: Path, s3: _FakeS3) -> tuple[ModelWatcher, SimpleNamespace, list]:
    """Assemble un watcher avec un état applicatif minimal traçable."""
    cleared: list[str] = []
    state = SimpleNamespace(
        registry_state=RegistryState(artifacts_dir=tmp_path),
        session_cache=SimpleNamespace(clear=lambda: cleared.append("sessions")),
        image_index=SimpleNamespace(invalidate=lambda: cleared.append("images")),
        broadcaster=EventBroadcaster(),
    )
    config = WatcherConfig(
        enabled=True,
        interval_s=0.01,
        manifest_s3_uri="s3://bucket/models/.meta/dvc.lock",
        dvc_lock_path=tmp_path / "dvc.lock",
    )
    watcher = ModelWatcher(state, config=config, s3_client=s3)
    return watcher, state, cleared


@pytest.mark.anyio
async def test_watcher_sleeps_while_manifest_absent(tmp_path: Path) -> None:
    """Manifeste jamais publié → veille silencieuse, aucun pull."""
    watcher, _, cleared = _make_watcher(tmp_path, _FakeS3())
    assert await watcher.check_once() is False
    assert cleared == []


@pytest.mark.anyio
async def test_watcher_pulls_on_new_etag_and_broadcasts(tmp_path: Path, monkeypatch) -> None:
    """Nouvel ETag → download + pull + invalidations + refresh + SSE."""
    s3 = _FakeS3()
    watcher, state, cleared = _make_watcher(tmp_path, s3)
    pulls: list[str] = []

    async def fake_pull() -> None:
        pulls.append("pull")
        # Le pull matérialise un nouveau modèle → newly_available non vide.
        (tmp_path / "models").mkdir(exist_ok=True)
        (tmp_path / "models" / "optimized_model.onnx").write_bytes(b"onnx")

    monkeypatch.setattr(watcher, "_dvc_pull", fake_pull)
    listener = await state.broadcaster.subscribe()

    s3.etag = '"etag-1"'
    assert await watcher.check_once() is True
    assert pulls == ["pull"]
    assert cleared == ["sessions", "images"]
    assert (tmp_path / "dvc.lock").read_text() == "locked"

    event = listener.get_nowait()
    assert event.startswith("event: models_updated\n")
    data = json.loads(event.split("data: ", 1)[1].strip())
    assert data["changed"] == ["chest_xray/optimized"]
    assert data["version"] == state.registry_state.version

    # Même ETag au tour suivant : aucun travail.
    assert await watcher.check_once() is False
    assert pulls == ["pull"]


@pytest.mark.anyio
async def test_watcher_disabled_never_starts(tmp_path: Path) -> None:
    """MEDVISION_WATCH_ENABLED=0 → start() est un no-op (statut disabled)."""
    watcher, _, _ = _make_watcher(tmp_path, _FakeS3())
    watcher._config.enabled = False
    watcher.status = "disabled"
    watcher.start()
    assert watcher._task is None
    await watcher.stop()  # idempotent


# ── Flux SSE de bout en bout ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_sse_stream_hello_then_models_updated(tmp_path: Path) -> None:
    """Le flux envoie `hello` (version courante) puis relaie les publications.

    On pilote directement le générateur `_event_stream` (pas de transport
    ASGI : les flux infinis + fermeture de client y sont fragiles en test)
    — c'est exactement ce que StreamingResponse consomme en prod.
    """
    from src.api.routes.events import _event_stream

    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    app = create_app(artifacts_dir=artifacts, data_root=tmp_path)
    fake_request = SimpleNamespace(app=app)

    stream = _event_stream(fake_request)
    try:
        hello = await asyncio.wait_for(stream.__anext__(), timeout=5)
        assert hello.startswith("event: hello\n")
        assert (
            json.loads(hello.split("data: ", 1)[1].strip())["version"]
            == app.state.registry_state.version
        )

        await app.state.broadcaster.publish("models_updated", {"version": "v2", "changed": []})
        event = await asyncio.wait_for(stream.__anext__(), timeout=5)
        assert event.startswith("event: models_updated\n")
        assert json.loads(event.split("data: ", 1)[1].strip())["version"] == "v2"
    finally:
        await stream.aclose()
    # La fermeture du flux a bien désinscrit le client (pas de fuite).
    assert await app.state.broadcaster.subscriber_count() == 0


@pytest.mark.anyio
async def test_sse_endpoint_headers(tmp_path: Path) -> None:
    """L'endpoint /api/events répond en text/event-stream non bufferisé.

    Appel direct de la route (pas de transport ASGI : fermer un corps
    infini via ASGITransport pend indéfiniment — vécu en CI).
    """
    from src.api.routes.events import events

    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    app = create_app(artifacts_dir=artifacts, data_root=tmp_path)

    response = await events(SimpleNamespace(app=app))
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    # Libère le générateur sous-jacent sans le consommer.
    await response.body_iterator.aclose()


def test_api_health_reports_watcher_status(tmp_path: Path) -> None:
    """La sonde v2 expose l'état du watcher (disabled par défaut en test)."""
    from fastapi.testclient import TestClient

    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    app = create_app(
        artifacts_dir=artifacts,
        data_root=tmp_path,
        watcher_config=WatcherConfig(enabled=False),
    )
    with TestClient(app) as client:
        body = client.get("/api/health").json()
        assert body["watcher"] == "disabled"
