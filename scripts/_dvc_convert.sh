#!/usr/bin/env bash
# Purpose : convertir TOUS les modèles en ONNX malgré la séparation des envs.
#           Passe 1 (env TF) : .keras → .onnx (les .pt y échouent, toléré).
#           Passe 2 (env torch) : .pt → .onnx (les .keras déjà convertis sont skippés).
#           L'union produit tous les .onnx. Utilisé par la stage convert_to_onnx.
# Usage   : bash scripts/_dvc_convert.sh
# Exit    : 0 si la passe torch réussit (= tous les .keras convertis en passe 1).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

{ set +u; source .venv/bin/activate; set -u; }
# shellcheck disable=SC1091
source scripts/gpu_env.sh >/dev/null 2>&1 || true
python scripts/convert_to_onnx.py || true       # keras OK ; .pt échouent ici (normal)
{ set +u; deactivate 2>/dev/null || true; set -u; }

[ -x .venv-torch/bin/python ] || { echo "[_dvc_convert] .venv-torch absent — bash scripts/install_prereqs.sh" >&2; exit 1; }
exec env -u LD_LIBRARY_PATH .venv-torch/bin/python scripts/convert_to_onnx.py   # .pt ; keras skippés → exit 0
