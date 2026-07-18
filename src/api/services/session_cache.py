"""Cache LRU borné des sessions d'inférence ONNX.

POURQUOI un cache borné : le registre expose 17 modèles ONNX (jusqu'à
~350 Mo de RAM par session pour les plus gros backbones) alors que le pod
API est limité à 2 Gi. Le `lru_cache(maxsize=16)` historique de
`load_onnx_model` pouvait donc conduire à un OOM kill si un utilisateur
comparait beaucoup de modèles. Ici : au plus `max_sessions` sessions
vivantes, éviction LRU, et invalidation totale quand le watcher DVC
remplace les fichiers modèles (une session ouverte sur un .onnx remplacé
servirait l'ANCIEN modèle en silence).
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

from src.registry.model_registry import create_onnx_session


class OnnxSessionCache:
    """Cache LRU thread-safe de `onnxruntime.InferenceSession`.

    Attributes:
        max_sessions: Nombre maximal de sessions simultanément en mémoire.
    """

    def __init__(self, max_sessions: int = 3) -> None:
        """Initialise le cache.

        Args:
            max_sessions: Borne dure du nombre de sessions en RAM (≥ 1).
        """
        self.max_sessions = max(1, int(max_sessions))
        self._sessions: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, model_path: str) -> Any:
        """Retourne la session du modèle, en la créant au besoin.

        Args:
            model_path: Chemin absolu du fichier .onnx.

        Returns:
            La session d'inférence prête à l'emploi.

        Raises:
            ModelNotFoundError: Le fichier .onnx est absent.
            ModelLoadError: Le fichier existe mais ne se charge pas.
        """
        with self._lock:
            session = self._sessions.get(model_path)
            if session is not None:
                # Touche l'entrée : elle redevient « la plus récente ».
                self._sessions.move_to_end(model_path)
                return session

        # Création HORS verrou : charger un .onnx prend des secondes et ne
        # doit pas bloquer les requêtes servies par les sessions déjà chaudes.
        session = create_onnx_session(model_path)

        with self._lock:
            self._sessions[model_path] = session
            self._sessions.move_to_end(model_path)
            while len(self._sessions) > self.max_sessions:
                # popitem(last=False) évince la moins récemment utilisée.
                self._sessions.popitem(last=False)
        return session

    def clear(self) -> None:
        """Vide le cache — à appeler après chaque `dvc pull` du watcher."""
        with self._lock:
            self._sessions.clear()

    def __len__(self) -> int:
        """Nombre de sessions actuellement en mémoire."""
        with self._lock:
            return len(self._sessions)
