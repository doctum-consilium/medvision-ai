"""Index d'images dataset côté API : construction paresseuse + vignettes.

S'appuie sur le module partagé src/datasets/sample_browser.py (même logique
que Streamlit). L'index par problème est construit au premier accès puis
mémorisé — le balayage disque (rglob sur des milliers de fichiers) ne doit
pas se rejouer à chaque requête de pagination.
"""
from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

from PIL import Image

from src.datasets.sample_browser import SampleIndex, build_problem_image_database

# Taille maximale du grand côté des vignettes servies par l'API.
THUMBNAIL_MAX_SIDE = 256


class ImageIndexService:
    """Index paresseux des échantillons navigables, par problème médical."""

    def __init__(self, root: Path | None = None, limit: int = 200) -> None:
        """Initialise le service.

        Args:
            root: Racine du projet (surchargée par les tests).
            limit: Nombre maximal d'échantillons indexés par problème —
                200 couvre largement la pagination UI sans balayer tout
                le dataset (des dizaines de milliers d'images en prod).
        """
        self._root = root
        self._limit = limit
        self._lock = threading.Lock()
        self._index = SampleIndex()
        self._samples: dict[str, list[dict[str, Any]]] = {}

    def samples(self, problem: str, expected_labels: list[str] | None) -> list[dict[str, Any]]:
        """Retourne (et construit au besoin) les échantillons d'un problème.

        Args:
            problem: Identifiant du problème.
            expected_labels: class_names du registre (équilibrage par classe).

        Returns:
            Liste d'échantillons {path, label, sample_id, display}.
        """
        with self._lock:
            if problem in self._samples:
                return self._samples[problem]

        built = build_problem_image_database(
            problem, expected_labels=expected_labels, limit=self._limit, root=self._root
        )
        with self._lock:
            self._samples[problem] = built
            self._index.put(problem, built)
        return built

    def resolve(self, problem: str, sample_id: str) -> dict[str, Any] | None:
        """Résout un sample_id opaque vers son échantillon (None si inconnu)."""
        with self._lock:
            return self._index.resolve(problem, sample_id)

    def invalidate(self) -> None:
        """Vide l'index (nouvelles données tirées ou volume remonté)."""
        with self._lock:
            self._samples.clear()
            self._index = SampleIndex()

    @staticmethod
    def encode_image(path: Path, thumbnail: bool = True) -> tuple[bytes, str]:
        """Encode une image du dataset pour la réponse HTTP.

        Args:
            path: Chemin réel (déjà validé par `resolve` — jamais fourni
                par le client).
            thumbnail: True → vignette JPEG ≤ 256 px (léger pour la grille) ;
                False → fichier original re-encodé en PNG (aperçu).

        Returns:
            (octets, media_type).
        """
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            buffer = io.BytesIO()
            if thumbnail:
                rgb.thumbnail((THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
                rgb.save(buffer, format="JPEG", quality=70)
                return buffer.getvalue(), "image/jpeg"
            rgb.save(buffer, format="PNG")
            return buffer.getvalue(), "image/png"
