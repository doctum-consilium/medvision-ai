#!/usr/bin/env bash
# Purpose : exécuter un module Python dans l'env PyTorch (.venv-torch), en isolant
#           LD_LIBRARY_PATH (le NCCL cu12 de TensorFlow casserait torch). Utilisé
#           par les stages torch de dvc.yaml.
# Usage   : bash scripts/_dvc_torch.sh <args python...>   (ex. -m src.training.train_brain_mri_torch ...)
# Exit    : code de retour de la commande.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
[ -x .venv-torch/bin/python ] || { echo "[_dvc_torch] .venv-torch absent — bash scripts/install_prereqs.sh" >&2; exit 1; }
# mlflow ≥ 3 lève une exception sur le backend fichier (./mlruns) sans cette opt-out.
export MLFLOW_ALLOW_FILE_STORE=true
exec env -u LD_LIBRARY_PATH .venv-torch/bin/python "$@"
