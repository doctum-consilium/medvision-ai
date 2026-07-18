"""Inférence ONNX côté API : prédiction structurée + encodage PNG des masques.

Différence clé avec l'API historique : pour la segmentation, on renvoie la
CARTE DE PROBABILITÉ complète encodée en PNG niveaux de gris (base64).
POURQUOI : le front Angular re-seuille le masque côté canvas — le slider
de seuil est instantané et ne coûte AUCUNE ré-inférence au petit CPU du
VPS (Streamlit, lui, ré-exécute le modèle à chaque changement de seuil).
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from src.api.services.session_cache import OnnxSessionCache
from src.preprocessing.image_loader import load_and_preprocess_image
from src.registry.model_registry import format_model_input


def run_onnx(session: Any, image: np.ndarray) -> dict[str, np.ndarray]:
    """Exécute l'inférence ONNX et retourne un dict {nom_sortie: array}.

    Args:
        session: onnxruntime.InferenceSession chargée.
        image: Image prétraitée (H, W, C) float.

    Returns:
        Dict des sorties par nom — mono-tête (classification) comme
        multi-têtes (segmentation + classification).
    """
    input_name = session.get_inputs()[0].name
    # NHWC (Keras) ou NCHW (PyTorch) : le layout est lu sur la session.
    x = format_model_input(session, image)
    out_names = [o.name for o in session.get_outputs()]
    outputs = session.run(None, {input_name: x})
    return dict(zip(out_names, outputs, strict=True))


def _classification_probs(raw: np.ndarray, class_names: list[str], task_type: str) -> dict[str, float]:
    """Convertit la sortie brute du modèle en probabilités par classe.

    Args:
        raw: Vecteur de sortie (1D) ou scalaire sigmoïde pour le binaire.
        class_names: Noms de classes dans l'ordre du modèle.
        task_type: "binary" ou "multiclass".

    Returns:
        Dict {classe: probabilité}.
    """
    if task_type == "binary":
        p1 = float(raw[0]) if np.ndim(raw) > 0 else float(raw)
        return {class_names[0]: float(1.0 - p1), class_names[1]: p1}
    probs = np.asarray(raw, dtype=float)
    return {name: float(probs[i]) for i, name in enumerate(class_names)}


def _grayscale_png_b64(array01: np.ndarray) -> str:
    """Encode un array float [0,1] (H, W) en PNG niveaux de gris base64."""
    as_bytes = (np.clip(array01, 0.0, 1.0) * 255.0).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(as_bytes, mode="L").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _rgb_png_b64(array01: np.ndarray) -> str:
    """Encode un array float [0,1] (H, W, 3) en PNG RGB base64."""
    as_bytes = (np.clip(array01, 0.0, 1.0) * 255.0).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(as_bytes, mode="RGB").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def predict_with_entry(
    model_entry: dict[str, Any],
    image_path: Path,
    session_cache: OnnxSessionCache,
    mask_threshold: float = 0.5,
    image_size: int | None = None,
) -> dict[str, Any]:
    """Prédit sur une image et retourne le résultat structuré pour l'API v2.

    Args:
        model_entry: Entrée du registre (model_path, class_names, task_type…).
        image_path: Chemin de l'image à analyser.
        session_cache: Cache borné des sessions ONNX (jamais 17 modèles en RAM).
        mask_threshold: Seuil de binarisation du masque (segmentation).
        image_size: Taille d'entrée forcée ; par défaut 256 en segmentation, 224 sinon.

    Returns:
        Dict : predicted_class, confidence, probabilities, metrics, et pour la
        segmentation un bloc "segmentation" (PNG base64 + statistiques).

    Raises:
        ModelNotFoundError: .onnx absent (404 côté route).
        ModelLoadError: .onnx illisible (500 côté route).
    """
    task_type = model_entry["task_type"]
    class_names = model_entry["class_names"]
    is_segmentation = task_type == "segmentation_multitask"
    if image_size is None:
        image_size = 256 if is_segmentation else 224

    session = session_cache.get(str(Path(model_entry["model_path"]).resolve()))
    image = load_and_preprocess_image(image_path, image_size=image_size)
    raw = run_onnx(session, image)
    out_names = list(raw.keys())

    if is_segmentation:
        # tf2onnx préserve les noms de couches Keras ; fallback sur l'index si absent.
        seg_key = next((k for k in out_names if "seg" in k.lower()), out_names[0])
        cls_key = next(
            (k for k in out_names if "class" in k.lower() or "cls" in k.lower()),
            out_names[-1],
        )
        seg = raw[seg_key][0, ..., 0].astype(np.float32)
        cls_raw = raw[cls_key][0]
        effective_type = "binary" if len(class_names) == 2 else "multiclass"
        probs = _classification_probs(cls_raw, class_names, effective_type)
        predicted = max(probs.items(), key=lambda item: item[1])[0]
        mask = (seg >= mask_threshold).astype(np.float32)
        return {
            "predicted_class": predicted,
            "confidence": float(max(probs.values())),
            "probabilities": probs,
            "metrics": model_entry.get("metrics", {}),
            "segmentation": {
                "mask_prob_png": _grayscale_png_b64(seg),
                "preprocessed_png": _rgb_png_b64(np.asarray(image, dtype=np.float32)),
                "mask_foreground_ratio": float(mask.mean()),
                "prob_mean": float(np.mean(seg)),
                "prob_max": float(np.max(seg)),
                "prob_min": float(np.min(seg)),
                "threshold": float(mask_threshold),
            },
        }

    logits = raw[out_names[0]][0]
    probs = _classification_probs(logits, class_names, task_type)
    predicted = max(probs.items(), key=lambda item: item[1])[0]
    return {
        "predicted_class": predicted,
        "confidence": float(max(probs.values())),
        "probabilities": probs,
        "metrics": model_entry.get("metrics", {}),
    }
