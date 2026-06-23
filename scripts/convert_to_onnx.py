#!/usr/bin/env python3
"""Convertit tous les modèles .keras et .pt en .onnx pour le déploiement.

Ce script doit être exécuté sur la machine d'entraînement où Keras 3.13.2+
et PyTorch sont disponibles. Il lit les fichiers depuis artifacts/models/,
produit les .onnx correspondants, puis vous guide pour le push DVC.

Usage:
    conda activate GPUMachineLearning
    pip install tf2onnx>=1.16 onnx>=1.16
    python scripts/convert_to_onnx.py
    python scripts/convert_to_onnx.py --dry-run   # aperçu sans écrire

Après conversion:
    dvc add artifacts/models/
    dvc push
    git add artifacts/models/
    git commit -m "feat(models): convertit tous les modèles en ONNX (version-stable)"
    git push
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

OPSET = 17  # ONNX opset 17 = support ≥ onnxruntime 1.14 (2023+)

logger = logging.getLogger(__name__)


def convert_keras(src: Path, dst: Path) -> None:
    """Convertit un fichier .keras → .onnx via tf2onnx.

    Args:
        src: Chemin vers le fichier source .keras (Keras 3.x).
        dst: Chemin de sortie pour le fichier .onnx.

    Raises:
        ImportError: tf2onnx ou tensorflow non installé dans l'env actif.
        RuntimeError: La conversion a échoué (config de couche incompatible, etc.).
    """
    import tensorflow as tf  # noqa: PLC0415
    import tf2onnx  # noqa: PLC0415

    logger.info("Keras → ONNX : %s", src.name)
    logger.info("  Chargement du modèle (Keras %s)…", tf.keras.__version__)

    # safe_mode=False : requis pour les Functional imbriquées (EfficientNetB0, etc.)
    model = tf.keras.models.load_model(src, compile=False, safe_mode=False)

    input_sig = [
        tf.TensorSpec(inp.shape, tf.float32, name=inp.name)
        for inp in model.inputs
    ]
    logger.info("  Inputs  : %s", [(s.name, s.shape) for s in input_sig])
    logger.info("  Outputs : %s", [o.name for o in model.outputs])

    onnx_proto, _ = tf2onnx.convert.from_keras(
        model,
        input_signature=input_sig,
        opset=OPSET,
    )

    import onnx  # noqa: PLC0415

    onnx.save(onnx_proto, dst)
    size_mb = dst.stat().st_size / 1e6
    logger.info("  → %s (%.1f MB) ✓", dst.name, size_mb)


def convert_pytorch(src: Path, dst: Path) -> None:
    """Convertit un fichier .pt → .onnx via torch.onnx.export.

    Suppose que le fichier est un modèle complet (torch.save(model, ...))
    et non uniquement un state_dict. Si c'est un state_dict, voir README_ONNX_UPDATE.md.

    Args:
        src: Chemin vers le fichier source .pt.
        dst: Chemin de sortie pour le fichier .onnx.

    Raises:
        ImportError: PyTorch non installé.
        RuntimeError: Le fichier est un state_dict ou la forme d'entrée ne correspond pas.
    """
    import torch  # noqa: PLC0415

    logger.info("PyTorch → ONNX : %s", src.name)
    model = torch.load(src, map_location="cpu", weights_only=False)
    model.eval()

    # Forme standard d'entrée pour les modèles de classification d'images
    dummy = torch.randn(1, 3, 224, 224)

    torch.onnx.export(
        model,
        dummy,
        str(dst),
        opset_version=OPSET,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    )
    size_mb = dst.stat().st_size / 1e6
    logger.info("  → %s (%.1f MB) ✓", dst.name, size_mb)


def main() -> None:
    """Point d'entrée principal du script de conversion."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Convertit .keras/.pt → .onnx pour le déploiement medvision-ai."
    )
    parser.add_argument(
        "--models-dir",
        default="artifacts/models",
        help="Répertoire contenant les modèles à convertir (défaut: artifacts/models)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche ce qui serait converti sans créer les fichiers .onnx",
    )
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    if not models_dir.exists():
        logger.error("Répertoire introuvable : %s", models_dir)
        sys.exit(1)

    convertibles = [
        src for src in sorted(models_dir.iterdir())
        if src.suffix in (".keras", ".pt")
    ]
    if not convertibles:
        logger.warning("Aucun fichier .keras ou .pt dans %s", models_dir)
        sys.exit(0)

    ok: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for src in convertibles:
        dst = src.with_suffix(".onnx")

        if dst.exists():
            logger.info("SKIP (déjà converti) : %s", dst.name)
            skipped.append(dst.name)
            continue

        if args.dry_run:
            logger.info("DRY-RUN : %s → %s", src.name, dst.name)
            continue

        try:
            if src.suffix == ".keras":
                convert_keras(src, dst)
            else:
                convert_pytorch(src, dst)
            ok.append(dst.name)
        except Exception as exc:  # noqa: BLE001
            logger.error("ERREUR %s : %s", src.name, exc)
            failed.append(src.name)

    print()
    if args.dry_run:
        print(f"DRY-RUN — {len(convertibles)} fichier(s) à convertir.")
        return

    if ok:
        print(f"✓ {len(ok)} converti(s) : {ok}")
    if skipped:
        print(f"→ {len(skipped)} déjà présent(s) : {skipped}")
    if failed:
        print(f"✗ {len(failed)} échec(s) : {failed}")
        print()
        print("Consultez README_ONNX_UPDATE.md pour le diagnostic.")
        sys.exit(1)

    if ok:
        print()
        print("Prochaines étapes :")
        print("  dvc add artifacts/models/")
        print("  dvc push")
        print("  git add artifacts/models/")
        print('  git commit -m "feat(models): convertit tous les modèles en ONNX"')
        print("  git push")


if __name__ == "__main__":
    main()
