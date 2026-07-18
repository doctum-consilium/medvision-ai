"""Route GET /api/problems — la liste des problèmes médicaux et leur état."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/problems")
def list_problems(request: Request) -> list[dict[str, Any]]:
    """Liste les problèmes médicaux avec compteurs de modèles.

    C'est l'écran d'accueil du front : une carte par problème, avec
    « x modèles disponibles sur y » — d'où les compteurs pré-calculés.

    Returns:
        Liste de dicts {id, label, task_type, class_names, models_total,
        models_available}.
    """
    registry = request.app.state.registry_state.registry()
    problems = []
    for problem_id, entry in registry["problems"].items():
        models = entry["models"]
        problems.append(
            {
                "id": problem_id,
                "label": entry["label"],
                "task_type": entry["task_type"],
                "class_names": entry["class_names"],
                "models_total": len(models),
                "models_available": sum(1 for m in models.values() if m["available"]),
            }
        )
    return problems
