from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.utils.config import load_config


class ModelNotFoundError(FileNotFoundError):
    """Le fichier .keras/.pt est absent du répertoire artifacts/models/."""


class ModelLoadError(RuntimeError):
    """Le modèle existe mais n'a pas pu être chargé (corruption, incompatibilité Keras)."""

DEFAULT_ARTIFACTS_DIR = Path("artifacts")

PROBLEMS: dict[str, dict[str, Any]] = {
    "chest_xray": {
        "label": "Chest X-ray Pneumonia Classification",
        "config_path": "configs/config.yaml",
        "model_candidates": {
            "baseline": "baseline_model.keras",
            "optimized": "optimized_model.keras",
            "densenet121": "densenet121_model.keras",
            "efficientnetv2b0": "efficientnetv2b0_model.keras",
            "convnexttiny": "convnexttiny_model.keras",
            "resnet50v2": "resnet50v2_model.keras",
        },
        "report_candidates": {
            "baseline": "baseline_classification_report.txt",
            "optimized": "optimized_classification_report.txt",
            "densenet121": "densenet121_classification_report.txt",
            "efficientnetv2b0": "efficientnetv2b0_classification_report.txt",
            "convnexttiny": "convnexttiny_classification_report.txt",
            "resnet50v2": "resnet50v2_classification_report.txt",
        },
        "metrics_candidates": {
            "baseline": ["baseline_metrics.json"],
            "optimized": ["optimized_metrics.json"],
            "densenet121": ["densenet121_metrics.json"],
            "efficientnetv2b0": ["efficientnetv2b0_metrics.json"],
            "convnexttiny": ["convnexttiny_metrics.json"],
            "resnet50v2": ["resnet50v2_metrics.json"],
        },
        "class_names": ["NORMAL", "PNEUMONIA"],
        "task_type": "binary",
    },
    "brain_mri": {
        "label": "Brain MRI Tumor Classification",
        "config_path": "configs/brain_tumor_mri.yaml",
        "model_candidates": {
            "optimized": "brain_mri_optimized.keras",
            "baseline": "brain_mri_baseline.keras",
            "densenet121": "brain_mri_densenet121.keras",
            "efficientnetv2b0": "brain_mri_efficientnetv2b0.keras",
            "convnexttiny": "brain_mri_convnexttiny.keras",
            "resnet50v2": "brain_mri_resnet50v2.keras",
            "densenet121_torch": "brain_mri_densenet121_torch.pt",
            "resnet50_torch": "brain_mri_resnet50_torch.pt",
            "swin_v2_s_torch": "brain_mri_swin_v2_s_torch.pt",
        },
        "report_candidates": {
            "optimized": "brain_mri_optimized_classification_report.txt",
            "baseline": "brain_mri_baseline_classification_report.txt",
            "densenet121": "brain_mri_densenet121_classification_report.txt",
            "efficientnetv2b0": "brain_mri_efficientnetv2b0_classification_report.txt",
            "convnexttiny": "brain_mri_convnexttiny_classification_report.txt",
            "resnet50v2": "brain_mri_resnet50v2_classification_report.txt",
        },
        "metrics_candidates": {
            "optimized": ["brain_mri_metrics.json"],
            "baseline": ["brain_mri_baseline_metrics.json"],
            "densenet121": ["brain_mri_densenet121_metrics.json"],
            "efficientnetv2b0": ["brain_mri_efficientnetv2b0_metrics.json"],
            "convnexttiny": ["brain_mri_convnexttiny_metrics.json"],
            "resnet50v2": ["brain_mri_resnet50v2_metrics.json"],
            "densenet121_torch": ["brain_mri_densenet121_torch_metrics.json"],
            "resnet50_torch": ["brain_mri_resnet50_torch_metrics.json"],
            "swin_v2_s_torch": ["brain_mri_swin_v2_s_torch_metrics.json"],
        },
        "class_names": ["glioma", "meningioma", "notumor", "pituitary"],
        "task_type": "multiclass",
    },
    "brain_tumor_segmentation": {
        "label": "Brain Tumor Segmentation + Classification",
        "config_path": "configs/brain_tumor_segmentation.yaml",
        "model_candidates": {
            "unet_multitask": "brain_tumor_segmentation_unet.keras",
        },
        "metrics_candidates": {
            "unet_multitask": ["brain_tumor_segmentation_unet_metrics.json"],
        },
        "class_names": ["glioma", "meningioma", "pituitary", "notumor"],
        "task_type": "segmentation_multitask",
    },
    "chest_xray_segmentation": {
        "label": "Chest X-ray Lung Segmentation + Abnormality Classification",
        "config_path": "configs/chest_xray_segmentation.yaml",
        "model_candidates": {
            "unet_multitask": "chest_xray_segmentation_unet.keras",
        },
        "metrics_candidates": {
            "unet_multitask": ["chest_xray_segmentation_unet_metrics.json"],
        },
        "class_names": ["NORMAL", "ABNORMAL"],
        "task_type": "segmentation_multitask",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find_first_existing(directory: Path, names: list[str] | tuple[str, ...]) -> Path | None:
    for name in names:
        if not name:
            continue
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def load_registry(artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR) -> dict[str, Any]:
    artifacts_dir = Path(artifacts_dir)
    models_dir = artifacts_dir / "models"
    reports_dir = artifacts_dir / "reports"
    registry: dict[str, Any] = {"problems": {}}

    for problem_key, spec in PROBLEMS.items():
        config = load_config(spec["config_path"]) if Path(spec["config_path"]).exists() else {}
        problem_entry: dict[str, Any] = {
            "label": spec["label"],
            "task_type": spec["task_type"],
            "class_names": config.get("class_names", spec["class_names"]),
            "models": {},
        }
        for model_key, model_filename in spec["model_candidates"].items():
            model_path = models_dir / model_filename
            metrics_path = _find_first_existing(reports_dir, spec.get("metrics_candidates", {}).get(model_key, []))
            report_path = _find_first_existing(reports_dir, [spec.get("report_candidates", {}).get(model_key, "")])

            problem_entry["models"][model_key] = {
                "model_path": str(model_path),
                "framework": "pytorch" if model_path.suffix == ".pt" else "tensorflow",
                "available": model_path.exists(),
                "metrics": _load_json(metrics_path) if metrics_path else {},
                "metrics_path": str(metrics_path) if metrics_path else None,
                "report_path": str(report_path) if report_path and report_path.exists() else None,
                "config_path": spec["config_path"],
            }
        registry["problems"][problem_key] = problem_entry

    return registry


@lru_cache(maxsize=16)
def load_tf_model(model_path: str):
    """Charge un modèle Keras depuis le chemin donné.

    L'import TensorFlow est différé au premier appel (lazy) pour que l'import
    du registry soit instantané même si TF n'est pas installé dans l'env courant.

    Args:
        model_path: Chemin absolu vers le fichier .keras.

    Returns:
        tf.keras.Model prêt pour l'inférence (non compilé).

    Raises:
        ModelNotFoundError: Le fichier n'existe pas.
        ModelLoadError: Le fichier existe mais la désérialisation a échoué.
    """
    import tensorflow as tf  # noqa: PLC0415 — import intentionnellement différé

    if not Path(model_path).exists():
        raise ModelNotFoundError(f"Modèle introuvable : {model_path}")

    # Patch de compatibilité Keras < 3.3 : `quantization_config` inconnu dans Dense.
    original_dense_from_config = tf.keras.layers.Dense.from_config

    def _compat_dense_from_config(cls, config):
        cfg = dict(config)
        cfg.pop("quantization_config", None)
        return original_dense_from_config.__func__(cls, cfg)

    try:
        return tf.keras.models.load_model(model_path, compile=False)
    except TypeError:
        tf.keras.layers.Dense.from_config = classmethod(_compat_dense_from_config)
        try:
            return tf.keras.models.load_model(model_path, compile=False)
        except Exception as exc:
            raise ModelLoadError(f"Impossible de charger {model_path} : {exc}") from exc
        finally:
            tf.keras.layers.Dense.from_config = original_dense_from_config
    except Exception as exc:
        raise ModelLoadError(f"Impossible de charger {model_path} : {exc}") from exc


def get_model_entry(problem: str, model_name: str, artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR) -> dict[str, Any]:
    registry = load_registry(artifacts_dir)
    problem_entry = registry["problems"].get(problem)
    if not problem_entry:
        raise KeyError(f"Unknown problem: {problem}")
    model_entry = problem_entry["models"].get(model_name)
    if not model_entry:
        raise KeyError(f"Unknown model '{model_name}' for problem '{problem}'")
    return {**model_entry, "class_names": problem_entry["class_names"], "task_type": problem_entry["task_type"]}


def compare_models(problem: str, artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR) -> list[dict[str, Any]]:
    registry = load_registry(artifacts_dir)
    problem_entry = registry["problems"].get(problem)
    if not problem_entry:
        raise KeyError(f"Unknown problem: {problem}")

    rows: list[dict[str, Any]] = []
    for model_name, model_entry in problem_entry["models"].items():
        row = {
            "model_name": model_name,
            "available": model_entry["available"],
        }
        row.update(model_entry.get("metrics", {}))
        rows.append(row)
    return rows
