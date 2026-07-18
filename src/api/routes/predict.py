"""Route POST /api/predict — prédiction multi-modèles en une seule requête.

POURQUOI multi-modèles : le studio Angular compare N modèles sur la même
image. Une requête unique = un seul upload + un seul prétraitement, puis
des inférences séquentielles (CPU-only : le parallélisme n'apporterait
rien sur le VPS et ferait exploser la RAM).
Les erreurs sont rapportées PAR MODÈLE (champ "error") — un .onnx absent
ne doit pas faire échouer la comparaison entière.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from src.api.services.inference import predict_with_entry
from src.registry.model_registry import ModelNotFoundError

router = APIRouter()


@router.post("/predict")
async def predict(
    request: Request,
    problem: str = Form(...),
    model_names: list[str] = Form(...),
    mask_threshold: float = Form(default=0.5, ge=0.0, le=1.0),
    file: UploadFile | None = File(default=None),
    sample_id: str | None = Form(default=None),
) -> dict[str, Any]:
    """Prédit la classe (et le masque) d'une image pour N modèles.

    L'image vient SOIT d'un upload (`file`), SOIT du dataset indexé
    (`sample_id`) — exactement un des deux.

    Args:
        request: Requête FastAPI.
        problem: Identifiant du problème.
        model_names: Modèles à exécuter (champ répétable du formulaire).
        mask_threshold: Seuil de binarisation du masque (segmentation).
        file: Image envoyée par l'utilisateur.
        sample_id: Identifiant opaque d'une image du dataset.

    Returns:
        {"problem", "image": {"source", "sample_id"?},
         "results": [{model_name, predicted_class?, …, error?}]}.

    Raises:
        HTTPException 400: Ni fichier ni sample_id (ou les deux).
        HTTPException 404: Problème ou échantillon inconnu.
    """
    if (file is None) == (sample_id is None):
        raise HTTPException(
            status_code=400,
            detail="Fournir SOIT un fichier image, SOIT un sample_id (exactement un des deux).",
        )

    state = request.app.state.registry_state
    if problem not in state.registry()["problems"]:
        raise HTTPException(status_code=404, detail=f"Unknown problem: {problem}")

    tmp_path: Path | None = None
    if file is not None:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        suffix = Path(file.filename).suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)
        predict_path = tmp_path
        image_info: dict[str, Any] = {"source": "upload"}
    else:
        sample = request.app.state.image_index.resolve(problem, str(sample_id))
        if sample is None:
            raise HTTPException(status_code=404, detail=f"Unknown sample: {sample_id}")
        predict_path = Path(sample["path"])
        image_info = {"source": "dataset", "sample_id": str(sample_id)}

    results: list[dict[str, Any]] = []
    try:
        for model_name in model_names:
            try:
                entry = state.model_entry(problem, model_name)
            except KeyError as exc:
                results.append({"model_name": model_name, "error": str(exc)})
                continue
            try:
                payload = predict_with_entry(
                    entry,
                    predict_path,
                    session_cache=request.app.state.session_cache,
                    mask_threshold=mask_threshold,
                )
            except ModelNotFoundError:
                results.append(
                    {
                        "model_name": model_name,
                        "error": "Modèle indisponible : entraîner puis `dvc push`, "
                        "le serveur le récupérera automatiquement.",
                    }
                )
                continue
            except Exception as exc:  # un modèle cassé ne bloque pas les autres
                message = str(exc)
                if len(message) > 300:
                    message = message[:300] + "…"
                results.append(
                    {"model_name": model_name, "error": f"{type(exc).__name__}: {message}"}
                )
                continue
            results.append({"model_name": model_name, **payload})
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    return {"problem": problem, "image": image_info, "results": results}
