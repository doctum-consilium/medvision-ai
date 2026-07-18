"""État versionné du registre de modèles.

Le front Angular a besoin de savoir « est-ce que quelque chose a changé ? »
sans re-télécharger tout le registre : ce service calcule une VERSION
courte et stable dérivée des fichiers .onnx réellement présents (chemin,
taille, mtime). Quand le watcher DVC tire de nouveaux modèles, la version
change → l'UI sait qu'elle doit se resynchroniser (et le flux SSE la
prévient sans polling).
"""
from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.registry.model_registry import DEFAULT_ARTIFACTS_DIR, load_registry


def _models_fingerprint(artifacts_dir: Path) -> str:
    """Empreinte courte des .onnx présents (chemin, taille, mtime triés).

    Args:
        artifacts_dir: Racine des artefacts (contient models/).

    Returns:
        12 hexdigits stables tant qu'aucun modèle n'apparaît/change/disparaît.
    """
    models_dir = artifacts_dir / "models"
    entries: list[str] = []
    if models_dir.exists():
        for path in sorted(models_dir.glob("*.onnx")):
            stat = path.stat()
            entries.append(f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}")
    digest = hashlib.sha256("|".join(entries).encode("utf-8")).hexdigest()
    return digest[:12]


class RegistryState:
    """Registre des modèles + version, rechargeable à chaud.

    Le registre complet (`load_registry`) est recalculé à chaque
    `refresh()` — appelé au démarrage et par le watcher après un
    `dvc pull`. Les routes lisent l'état en mémoire (pas de re-scan
    disque à chaque requête).
    """

    def __init__(self, artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR) -> None:
        """Initialise l'état et charge le registre une première fois.

        Args:
            artifacts_dir: Racine des artefacts (surchargée par les tests).
        """
        self._artifacts_dir = Path(artifacts_dir)
        self._lock = threading.Lock()
        self._registry: dict[str, Any] = {"problems": {}}
        self._version = ""
        self._refreshed_at: str | None = None
        self.refresh()

    @property
    def version(self) -> str:
        """Version courte courante du registre (change quand les .onnx changent)."""
        with self._lock:
            return self._version

    @property
    def refreshed_at(self) -> str | None:
        """Horodatage ISO du dernier rechargement (None avant le premier)."""
        with self._lock:
            return self._refreshed_at

    def registry(self) -> dict[str, Any]:
        """Retourne le registre courant (dict partagé en lecture seule)."""
        with self._lock:
            return self._registry

    def refresh(self) -> tuple[str, list[str]]:
        """Recharge le registre depuis le disque et recalcule la version.

        Returns:
            (nouvelle_version, modèles_devenus_disponibles) — la liste
            « problem/model » des modèles qui n'étaient PAS disponibles
            avant ce refresh, pour alimenter l'événement SSE
            ``models_updated`` (badge « Nouveau » côté UI).
        """
        new_registry = load_registry(self._artifacts_dir)
        new_version = _models_fingerprint(self._artifacts_dir)

        with self._lock:
            previously_available = {
                f"{p}/{m}"
                for p, entry in self._registry.get("problems", {}).items()
                for m, meta in entry.get("models", {}).items()
                if meta.get("available")
            }
            now_available = {
                f"{p}/{m}"
                for p, entry in new_registry.get("problems", {}).items()
                for m, meta in entry.get("models", {}).items()
                if meta.get("available")
            }
            newly_available = sorted(now_available - previously_available)

            self._registry = new_registry
            self._version = new_version
            self._refreshed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        return new_version, newly_available

    def model_entry(self, problem: str, model_name: str) -> dict[str, Any]:
        """Entrée complète d'un modèle (avec class_names/task_type du problème).

        Args:
            problem: Identifiant du problème.
            model_name: Identifiant du modèle.

        Returns:
            Dict prêt pour l'inférence (model_path, task_type, class_names…).

        Raises:
            KeyError: Problème ou modèle inconnu.
        """
        with self._lock:
            problem_entry = self._registry["problems"].get(problem)
            if not problem_entry:
                raise KeyError(f"Unknown problem: {problem}")
            model_entry = problem_entry["models"].get(model_name)
            if not model_entry:
                raise KeyError(f"Unknown model '{model_name}' for problem '{problem}'")
            return {
                **model_entry,
                "class_names": problem_entry["class_names"],
                "task_type": problem_entry["task_type"],
            }
