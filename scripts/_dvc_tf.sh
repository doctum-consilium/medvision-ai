#!/usr/bin/env bash
# Purpose : exécuter une commande dans l'env TensorFlow (.venv) avec GPU configuré.
#           Utilisé par les stages dvc.yaml pour que `dvc repro` marche depuis
#           n'importe quel shell (il active .venv + source gpu_env.sh lui-même).
# Usage   : bash scripts/_dvc_tf.sh <commande...>   (ex. python -m src.training.train ...)
# Exit    : code de retour de la commande.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
{ set +u; source .venv/bin/activate; set -u; }
# shellcheck disable=SC1091
source scripts/gpu_env.sh >/dev/null 2>&1 || true
exec "$@"
