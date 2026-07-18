"""Route GET /api/events — flux SSE temps réel vers le front Angular.

Événements émis :
- ``models_updated`` : le watcher DVC a tiré de nouveaux modèles
  (data : version du registre, liste des modèles apparus, horodatage) ;
- ``heartbeat`` toutes les 25 s : maintient la connexion À TRAVERS
  l'ingress nginx (timeout de lecture 60 s par défaut) et permet au
  client de détecter une connexion morte.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

# Période du battement de cœur : STRICTEMENT sous les 60 s de
# proxy-read-timeout par défaut de nginx (ingress ET sidecar du front).
HEARTBEAT_SECONDS = 25.0


async def _event_stream(request: Request) -> AsyncIterator[str]:
    """Générateur SSE : relaie les événements du broadcaster + heartbeats.

    La désinscription est garantie par le bloc finally — y compris quand
    le client ferme brutalement l'onglet (CancelledError).
    """
    broadcaster = request.app.state.broadcaster
    queue = await broadcaster.subscribe()
    # Premier événement immédiat : la version courante — le client sait
    # tout de suite s'il est à jour (utile après une reconnexion).
    yield (
        "event: hello\n"
        f"data: {json.dumps({'version': request.app.state.registry_state.version})}\n\n"
    )
    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                yield payload
            # asyncio.TimeoutError : en Python 3.10 (image prod) ce N'est PAS
            # l'alias du builtin TimeoutError (fusion arrivée en 3.11).
            except asyncio.TimeoutError:  # noqa: UP041
                at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                yield f"event: heartbeat\ndata: {json.dumps({'at': at})}\n\n"
    finally:
        await broadcaster.unsubscribe(queue)


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    """Ouvre le flux SSE (text/event-stream).

    Returns:
        Réponse streaming jamais bufferisée (X-Accel-Buffering: no pour
        les nginx intermédiaires).
    """
    return StreamingResponse(
        _event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
