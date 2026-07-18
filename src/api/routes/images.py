"""Routes GET /api/images — le navigateur d'images dataset du front Angular.

Sécurité : le client ne manipule QUE des sample_id opaques. Le seul chemin
jamais ouvert vient de notre propre index (SampleIndex) — un id inconnu
répond 404, un chemin déguisé en id ne résout rien.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from src.datasets.sample_browser import filter_samples, recommended_samples

router = APIRouter()


def _public_sample(sample: dict[str, Any]) -> dict[str, str]:
    """Projette un échantillon vers sa forme publique (SANS le chemin disque)."""
    return {
        "sample_id": str(sample["sample_id"]),
        "label": str(sample["label"]),
        "display": str(sample["display"]),
    }


@router.get("/images")
def list_images(
    request: Request,
    problem: str = Query(...),
    labels: str = Query(default="", description="Labels retenus, séparés par des virgules"),
    q: str = Query(default="", description="Recherche libre (id ou label)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=48),
) -> dict[str, Any]:
    """Liste paginée des échantillons navigables d'un problème.

    Args:
        request: Requête FastAPI.
        problem: Identifiant du problème.
        labels: Filtre de classes (chaîne vide = toutes).
        q: Recherche texte dans id/label.
        page: Page 1-indexée.
        page_size: Taille de page (bornée pour protéger le VPS).

    Returns:
        {"total", "page", "page_size", "recommended": [4 max], "items": […]}.

    Raises:
        HTTPException 404: Problème inconnu du registre.
    """
    registry = request.app.state.registry_state.registry()
    entry = registry["problems"].get(problem)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown problem: {problem}")

    samples = request.app.state.image_index.samples(problem, entry.get("class_names"))
    chosen_labels = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
    filtered = filter_samples(samples, labels=chosen_labels, query=q)

    start = (page - 1) * page_size
    return {
        "total": len(filtered),
        "page": page,
        "page_size": page_size,
        "recommended": [_public_sample(s) for s in recommended_samples(filtered, max_items=4)],
        "items": [_public_sample(s) for s in filtered[start : start + page_size]],
    }


@router.get("/images/{sample_id}/file")
def get_image_file(
    request: Request,
    sample_id: str,
    problem: str = Query(...),
    thumb: bool = Query(default=True),
) -> Response:
    """Sert le fichier image d'un échantillon indexé.

    Args:
        request: Requête FastAPI.
        sample_id: Identifiant public opaque (jamais un chemin).
        problem: Identifiant du problème (les index sont par problème).
        thumb: True → vignette JPEG 256 px ; False → image pleine taille.

    Returns:
        La réponse binaire image, avec un cache navigateur d'une heure
        (les datasets sont immuables entre deux redéploiements).

    Raises:
        HTTPException 404: sample_id inconnu de l'index.
    """
    index = request.app.state.image_index
    sample = index.resolve(problem, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"Unknown sample: {sample_id}")

    payload, media_type = index.encode_image(sample["path"], thumbnail=thumb)
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
