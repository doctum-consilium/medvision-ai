from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from src.preprocessing.image_loader import load_and_preprocess_image
from src.registry.model_registry import compare_models, get_model_entry, load_registry, load_tf_model

app = FastAPI(title="MedVision AI API", version="3.0.0")


def _classification_payload(raw: np.ndarray, model_entry: dict[str, Any]) -> dict[str, Any]:
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
    model_path = Path(model_entry["model_path"])
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {model_path}")
    if model_entry.get("framework") != "tensorflow":
        raise HTTPException(status_code=400, detail="This prediction endpoint currently serves TensorFlow models only. Use the registry/compare views for PyTorch runs.")

    model = load_tf_model(str(model_path.resolve()))
    image = load_and_preprocess_image(image_path, image_size=image_size)
    batch = np.expand_dims(image, axis=0)
    raw = model.predict(batch, verbose=0)

    if model_entry["task_type"] == "segmentation_multitask":
        if not isinstance(raw, dict):
            raise HTTPException(status_code=500, detail="Expected a multitask segmentation model returning a dict.")
        mask = raw["segmentation_output"][0, ..., 0]
        pred_mask = (mask >= 0.5).astype(np.uint8)
        cls_raw = raw["classification_output"][0]
        class_payload = _classification_payload(cls_raw, {**model_entry, "task_type": "binary" if len(model_entry["class_names"]) == 2 else "multiclass"})
        return {
            **class_payload,
            "mask_foreground_ratio": float(pred_mask.mean()),
            "mask_shape": list(pred_mask.shape),
        }

    raw = raw[0]
    return _classification_payload(raw, model_entry)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/registry")
def registry() -> dict[str, Any]:
    return load_registry()


@app.get("/models")
def list_models(problem: str | None = Query(default=None)) -> dict[str, Any]:
    registry = load_registry()
    if problem:
        if problem not in registry["problems"]:
            raise HTTPException(status_code=404, detail=f"Unknown problem: {problem}")
        return registry["problems"][problem]
    return registry


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
        result = _predict_with_entry(model_entry, tmp_path, image_size=256 if 'segmentation' in problem else 224)
        return {"problem": problem, "model_name": model_name, **result, "model_metadata": {"metrics": model_entry.get("metrics", {}), "model_path": model_entry["model_path"]}}
    finally:
        tmp_path.unlink(missing_ok=True)
