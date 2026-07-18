"""Diffuseur d'événements SSE : fan-out vers tous les abonnés connectés.

~40 lignes maison plutôt qu'une dépendance (sse-starlette) : le besoin est
minime — une queue asyncio par abonné, publication non bloquante, et
désinscription garantie quand le client ferme la connexion.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any


class EventBroadcaster:
    """Fan-out d'événements vers N abonnés SSE.

    Chaque abonné possède sa propre queue : un client lent ne bloque pas
    les autres. Si sa queue déborde (client gelé), l'événement est perdu
    pour LUI seul — il se resynchronisera via GET /api/models/version à la
    reconnexion (mécanisme prévu côté front).
    """

    def __init__(self, max_queue_size: int = 32) -> None:
        """Initialise le diffuseur.

        Args:
            max_queue_size: Taille de la queue par abonné avant de jeter.
        """
        self._max_queue_size = max_queue_size
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[str]:
        """Enregistre un nouvel abonné et retourne sa queue d'événements."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self._max_queue_size)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        """Désinscrit un abonné (appelé dans le finally du générateur SSE)."""
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        """Publie un événement à tous les abonnés, sans jamais bloquer.

        Args:
            event: Nom SSE de l'événement (ex. "models_updated").
            data: Charge utile, sérialisée en JSON.
        """
        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Client gelé : on jette POUR LUI ; il se resynchronisera
                # via /api/models/version à la reconnexion.
                pass

    async def subscriber_count(self) -> int:
        """Nombre d'abonnés actuellement connectés (diagnostic)."""
        async with self._lock:
            return len(self._subscribers)
