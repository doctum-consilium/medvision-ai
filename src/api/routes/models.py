"""Routes GET /api/models et /api/models/version — registre enrichi et versionné."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


def _enrich_model(meta: dict[str, Any]) -> dict[str, Any]:
    """Ajoute taille et date de modification du .onnx à une entrée de registre.

    POURQUOI : le front affiche un badge « Nouveau » basé sur modified_at,
    sans avoir accès au disque du pod.
    """
    enriched = {
        "available": meta["available"],
        "framework": meta["framework"],
        "metrics": meta.get("metrics", {}),
        "report_available": bool(meta.get("report_path")),
        "size_bytes": None,
        "modified_at": None,
    }
    model_path = Path(meta["model_path"])
    if meta["available"] and model_path.exists():
        stat = model_path.stat()
        enriched["size_bytes"] = stat.st_size
        enriched["modified_at"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
    return enriched


@router.get("/models")
def list_models(request: Request, problem: str | None = Query(default=None)) -> dict[str, Any]:
    """Registre des modèles, enrichi (taille, date) et versionné.

    Args:
        request: Requête FastAPI (accès à l'état applicatif).
        problem: Restreint la réponse à un seul problème (optionnel).

    Returns:
        {"version": str, "problems": {id: {label, task_type, class_names,
        models: {nom: {available, metrics, size_bytes, modified_at, …}}}}}.

    Raises:
        HTTPException 404: Problème inconnu.
    """
    state = request.app.state.registry_state
    registry = state.registry()

    problems = registry["problems"]
    if problem is not None:
        if problem not in problems:
            raise HTTPException(status_code=404, detail=f"Unknown problem: {problem}")
        problems = {problem: problems[problem]}

    return {
        "version": state.version,
        "problems": {
            pid: {
                "label": entry["label"],
                "task_type": entry["task_type"],
                "class_names": entry["class_names"],
                "models": {name: _enrich_model(meta) for name, meta in entry["models"].items()},
            }
            for pid, entry in problems.items()
        },
    }


@router.get("/models/version")
def models_version(request: Request) -> dict[str, str | None]:
    """Version courte du registre — resynchronisation légère après une
    coupure SSE (le front compare et ne recharge que si ça a changé)."""
    state = request.app.state.registry_state
    return {"version": state.version, "refreshed_at": state.refreshed_at}


@router.get("/compare")
def compare(request: Request, problem: str = Query(...)) -> dict[str, Any]:
    """Tableau comparatif des métriques des modèles d'un problème.

    Args:
        request: Requête FastAPI.
        problem: Identifiant du problème.

    Returns:
        {"problem", "version", "rows": [{model_name, available, métriques…}]}.

    Raises:
        HTTPException 404: Problème inconnu.
    """
    state = request.app.state.registry_state
    registry = state.registry()
    entry = registry["problems"].get(problem)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown problem: {problem}")

    rows = []
    for model_name, meta in entry["models"].items():
        row = {"model_name": model_name, "available": meta["available"]}
        row.update(meta.get("metrics", {}))
        rows.append(row)
    return {"problem": problem, "version": state.version, "rows": rows}
