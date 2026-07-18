"""Route GET /api/reports — métriques et rapport de classification d'un modèle."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


@router.get("/reports")
def get_report(
    request: Request,
    problem: str = Query(...),
    model: str = Query(...),
) -> dict[str, Any]:
    """Métriques JSON + rapport texte (classification_report) d'un modèle.

    Args:
        request: Requête FastAPI.
        problem: Identifiant du problème.
        model: Identifiant du modèle.

    Returns:
        {"problem", "model", "metrics": {...},
         "classification_report": str | None} — le rapport est None si le
        fichier n'a pas été tiré sur le pod (limitation connue : seul le
        stage ONNX est dvc-pullé au démarrage).

    Raises:
        HTTPException 404: Problème ou modèle inconnu.
    """
    try:
        entry = request.app.state.registry_state.model_entry(problem, model)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    report_text: str | None = None
    report_path = entry.get("report_path")
    if report_path and Path(report_path).exists():
        try:
            report_text = Path(report_path).read_text(encoding="utf-8")
        except OSError:
            report_text = None

    return {
        "problem": problem,
        "model": model,
        "metrics": entry.get("metrics", {}),
        "classification_report": report_text,
    }
