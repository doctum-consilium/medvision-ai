from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from src.preprocessing.image_loader import load_and_preprocess_image
from src.registry.model_registry import (
    ModelNotFoundError,
    compare_models,
    get_model_entry,
    load_onnx_model,
    load_registry,
)

app = FastAPI(title="MedVision AI API", version="3.1.0")


def _run_onnx(session: Any, image: np.ndarray) -> dict[str, np.ndarray]:
    """Lance l'inférence ONNX et retourne un dict {nom_sortie: array}.

    Args:
        session: onnxruntime.InferenceSession chargée.
        image: Image prétraitée, shape (H, W, C), float32.

    Returns:
        Dict des sorties par nom (ex. "segmentation_output", "output").
    """
    input_name = session.get_inputs()[0].name
    x = image.astype(np.float32)[np.newaxis, ...]
    out_names = [o.name for o in session.get_outputs()]
    outputs = session.run(None, {input_name: x})
    return dict(zip(out_names, outputs, strict=True))


def _classification_payload(raw: np.ndarray, model_entry: dict[str, Any]) -> dict[str, Any]:
    """Construit le payload de classification à partir d'un vecteur de sortie.

    Args:
        raw: Vecteur de probabilités (1D) ou scalaire pour binaire.
        model_entry: Entrée du registre avec class_names et task_type.

    Returns:
        Dict avec predicted_class, confidence, probabilities.
    """
    class_names = model_entry["class_names"]
    task_type = model_entry["task_type"]
    if task_type == "binary":
        probability = float(raw[0]) if np.ndim(raw) > 0 else float(raw)
        predicted_class = class_names[1] if probability >= 0.5 else class_names[0]
        probabilities = {class_names[0]: float(1.0 - probability), class_names[1]: float(probability)}
        confidence = max(probabilities.values())
    else:
        probs = np.asarray(raw, dtype=float)
        pred_idx = int(np.argmax(probs))
        predicted_class = class_names[pred_idx]
        probabilities = {name: float(probs[i]) for i, name in enumerate(class_names)}
        confidence = float(probs[pred_idx])
    return {"predicted_class": predicted_class, "confidence": confidence, "probabilities": probabilities}


def _predict_with_entry(model_entry: dict[str, Any], image_path: Path, image_size: int = 224) -> dict[str, Any]:
    """Exécute l'inférence ONNX pour une image et retourne le résultat structuré.

    Args:
        model_entry: Entrée du registre (model_path, class_names, task_type...).
        image_path: Chemin vers l'image à analyser.
        image_size: Taille de redimensionnement (224 pour classification, 256 pour segmentation).

    Returns:
        Dict avec predicted_class, confidence, probabilities, et optionnellement mask_*.

    Raises:
        HTTPException 404: Fichier .onnx introuvable (pas encore converti).
        HTTPException 500: Erreur lors du chargement ou de l'inférence.
    """
    model_path = model_entry["model_path"]
    try:
        session = load_onnx_model(str(Path(model_path).resolve()))
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur chargement modèle : {exc}") from exc

    image = load_and_preprocess_image(image_path, image_size=image_size)
    raw = _run_onnx(session, image)
    out_names = list(raw.keys())

    if model_entry["task_type"] == "segmentation_multitask":
        seg_key = next((k for k in out_names if "seg" in k.lower()), out_names[0])
        cls_key = next((k for k in out_names if "class" in k.lower() or "cls" in k.lower()), out_names[-1])
        mask = raw[seg_key][0, ..., 0]
        pred_mask = (mask >= 0.5).astype(np.uint8)
        cls_raw = raw[cls_key][0]
        effective_type = "binary" if len(model_entry["class_names"]) == 2 else "multiclass"
        class_payload = _classification_payload(cls_raw, {**model_entry, "task_type": effective_type})
        return {
            **class_payload,
            "mask_foreground_ratio": float(pred_mask.mean()),
            "mask_shape": list(pred_mask.shape),
        }

    cls_output = raw[out_names[0]][0]
    return _classification_payload(cls_output, model_entry)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/registry")
def registry() -> dict[str, Any]:
    return load_registry()


@app.get("/models")
def list_models(problem: str | None = Query(default=None)) -> dict[str, Any]:
    reg = load_registry()
    if problem:
        if problem not in reg["problems"]:
            raise HTTPException(status_code=404, detail=f"Unknown problem: {problem}")
        return reg["problems"][problem]
    return reg


@app.get("/compare")
def compare(problem: str = Query(..., description="Problem id")) -> dict[str, Any]:
    try:
        return {"problem": problem, "rows": compare_models(problem)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/predict")
async def predict(
    file: UploadFile = File(...),
    problem: str = Query(..., description="Problem id"),
    model_name: str = Query(..., description="Model id"),
) -> dict[str, Any]:
    """Prédit la classe et la confiance à partir d'une image médicale.

    Args:
        file: Image à analyser (PNG, JPG, TIFF…).
        problem: Identifiant du problème (chest_xray, brain_mri…).
        model_name: Identifiant du modèle dans le registre.

    Returns:
        Dict avec problem, model_name, predicted_class, confidence, probabilities, model_metadata.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    try:
        model_entry = get_model_entry(problem, model_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    suffix = Path(file.filename).suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = _predict_with_entry(
            model_entry,
            tmp_path,
            image_size=256 if "segmentation" in problem else 224,
        )
        return {
            "problem": problem,
            "model_name": model_name,
            **result,
            "model_metadata": {
                "metrics": model_entry.get("metrics", {}),
                "model_path": model_entry["model_path"],
            },
        }
    finally:
        tmp_path.unlink(missing_ok=True)
