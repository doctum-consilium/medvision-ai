from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.utils.config import load_config


class ModelNotFoundError(FileNotFoundError):
    """Le fichier .onnx est absent du répertoire artifacts/models/.

    Cause la plus fréquente : les modèles n'ont pas encore été convertis en ONNX.
    Exécuter scripts/convert_to_onnx.py sur la machine d'entraînement,
    puis dvc push, puis rebuilder l'image.
    """


class ModelLoadError(RuntimeError):
    """Le modèle existe mais n'a pas pu être chargé (fichier corrompu, etc.)."""


DEFAULT_ARTIFACTS_DIR = Path("artifacts")

# Registre des problèmes médicaux et de leurs modèles associés.
# Tous les modèles référencent des fichiers .onnx — format stable entre versions.
# Les fichiers .keras/.pt sources sont conservés en DVC pour l'entraînement.
PROBLEMS: dict[str, dict[str, Any]] = {
    "chest_xray": {
        "label": "Chest X-ray Pneumonia Classification",
        "config_path": "configs/config.yaml",
        "model_candidates": {
            "baseline": "baseline_model.onnx",
            "optimized": "optimized_model.onnx",
            "densenet121": "densenet121_model.onnx",
            "efficientnetv2b0": "efficientnetv2b0_model.onnx",
            "convnexttiny": "convnexttiny_model.onnx",
            "resnet50v2": "resnet50v2_model.onnx",
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
            "optimized": "brain_mri_optimized.onnx",
            "baseline": "brain_mri_baseline.onnx",
            "densenet121": "brain_mri_densenet121.onnx",
            "efficientnetv2b0": "brain_mri_efficientnetv2b0.onnx",
            "convnexttiny": "brain_mri_convnexttiny.onnx",
            "resnet50v2": "brain_mri_resnet50v2.onnx",
            "densenet121_torch": "brain_mri_densenet121_torch.onnx",
            "resnet50_torch": "brain_mri_resnet50_torch.onnx",
            "swin_v2_s_torch": "brain_mri_swin_v2_s_torch.onnx",
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
            "unet_multitask": "brain_tumor_segmentation_unet.onnx",
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
            "unet_multitask": "chest_xray_segmentation_unet.onnx",
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
    """Construit le registre complet des modèles disponibles.

    Args:
        artifacts_dir: Répertoire racine des artefacts (contient models/, reports/).

    Returns:
        Dict avec une clé "problems" → dict de problèmes → modèles disponibles.
    """
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
            metrics_path = _find_first_existing(
                reports_dir, spec.get("metrics_candidates", {}).get(model_key, [])
            )
            report_path = _find_first_existing(
                reports_dir, [spec.get("report_candidates", {}).get(model_key, "")]
            )

            problem_entry["models"][model_key] = {
                "model_path": str(model_path),
                "framework": "onnxruntime",
                "available": model_path.exists(),
                "metrics": _load_json(metrics_path) if metrics_path else {},
                "metrics_path": str(metrics_path) if metrics_path else None,
                "report_path": str(report_path) if report_path and report_path.exists() else None,
                "config_path": spec["config_path"],
            }
        registry["problems"][problem_key] = problem_entry

    return registry


@lru_cache(maxsize=16)
def load_onnx_model(model_path: str) -> Any:
    """Charge un modèle ONNX et retourne une InferenceSession prête pour l'inférence.

    L'import onnxruntime est différé au premier appel (lazy) pour que l'import
    du registry reste instantané même si onnxruntime n'est pas installé.

    Args:
        model_path: Chemin absolu vers le fichier .onnx.

    Returns:
        onnxruntime.InferenceSession prêt pour l'inférence CPU.

    Raises:
        ModelNotFoundError: Le fichier .onnx est absent — modèle non encore converti.
            Exécuter scripts/convert_to_onnx.py sur la machine ML, puis dvc push.
        ModelLoadError: Le fichier existe mais la désérialisation a échoué.

    Example:
        >>> sess = load_onnx_model("artifacts/models/optimized_model.onnx")
        >>> out = sess.run(None, {sess.get_inputs()[0].name: image_batch})
    """
    # On vérifie l'existence du fichier AVANT d'importer onnxruntime : un modèle
    # absent doit lever ModelNotFoundError SANS dépendre d'onnxruntime (sinon un
    # environnement sans la lib — ex. job CI léger — voit un ModuleNotFoundError
    # illisible au lieu de l'erreur métier). L'import reste paresseux, juste après.
    path = Path(model_path)
    if not path.exists():
        raise ModelNotFoundError(
            f"{path.name} introuvable.\n"
            "Le modèle n'a pas encore été converti en ONNX.\n"
            "Exécuter : python scripts/convert_to_onnx.py (sur machine ML), puis dvc push."
        )

    try:
        import onnxruntime as ort  # noqa: PLC0415 — lazy import intentionnel
        opts = ort.SessionOptions()
        opts.log_severity_level = 3  # supprime les avertissements verbeux
        return ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
    except Exception as exc:
        raise ModelLoadError(f"{path.name} : {exc}") from exc


def get_model_entry(
    problem: str,
    model_name: str,
    artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
) -> dict[str, Any]:
    """Retourne l'entrée de registre pour un modèle donné.

    Args:
        problem: Clé du problème médical (ex. "chest_xray", "brain_mri").
        model_name: Nom du modèle dans le registre (ex. "baseline", "optimized").
        artifacts_dir: Répertoire racine des artefacts.

    Returns:
        Dict avec model_path, framework, available, metrics, class_names, task_type.

    Raises:
        KeyError: Le problème ou le modèle n'existe pas dans le registre.
    """
    registry = load_registry(artifacts_dir)
    problem_entry = registry["problems"].get(problem)
    if not problem_entry:
        raise KeyError(f"Unknown problem: {problem}")
    model_entry = problem_entry["models"].get(model_name)
    if not model_entry:
        raise KeyError(f"Unknown model '{model_name}' for problem '{problem}'")
    return {**model_entry, "class_names": problem_entry["class_names"], "task_type": problem_entry["task_type"]}


def compare_models(
    problem: str,
    artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
) -> list[dict[str, Any]]:
    """Retourne un tableau comparatif des métriques pour tous les modèles d'un problème.

    Args:
        problem: Clé du problème médical.
        artifacts_dir: Répertoire racine des artefacts.

    Returns:
        Liste de dicts (un par modèle) avec model_name, available, et toutes les métriques.

    Raises:
        KeyError: Le problème n'existe pas dans le registre.
    """
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
