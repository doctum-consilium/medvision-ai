#!/usr/bin/env bash
# Purpose  : Entraîne tous les modèles brain_mri (Keras + PyTorch) séquentiellement.
#            Un seul GPU utilisé à la fois — pas de parallélisme.
#
# Usage    : bash scripts/run_training_brain_mri_all.sh [--skip-existing]
# Arguments:
#   --skip-existing  Saute les backbones dont le fichier .keras/.pt existe déjà.
# Exit codes:
#   0  Tous les entraînements terminés (ou sautés)
#   1  Au moins un entraînement a échoué (les autres continuent)
set -euo pipefail

CONFIG="configs/brain_tumor_mri.yaml"
MODELS_DIR="artifacts/models"
SKIP_EXISTING=false

PYTHON=".venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python"

for arg in "$@"; do
  case "$arg" in
    --skip-existing) SKIP_EXISTING=true ;;
    *) echo "[ERREUR] Argument inconnu : $arg" >&2; exit 1 ;;
  esac
done

log()  { echo "[$(date +%H:%M:%S)] $*"; }
ok()   { echo "[$(date +%H:%M:%S)] ✓ $*"; }
fail() { echo "[$(date +%H:%M:%S)] ✗ $*" >&2; }

FAILED=()

run_keras() {
  local backbone="$1"
  local outfile="$2"
  if [ "$SKIP_EXISTING" = true ] && [ -f "${MODELS_DIR}/${outfile}" ]; then
    log "SKIP (existe déjà) : ${outfile}"
    return 0
  fi
  log "--- Keras / ${backbone} ---"
  if $PYTHON -m src.training.train_brain_mri --config "$CONFIG" --model "$backbone"; then
    ok "${outfile} produit"
  else
    fail "${backbone} a échoué"
    FAILED+=("keras/${backbone}")
  fi
}

run_torch() {
  local model_name="$1"
  local outfile="$2"
  if [ "$SKIP_EXISTING" = true ] && [ -f "${MODELS_DIR}/${outfile}" ]; then
    log "SKIP (existe déjà) : ${outfile}"
    return 0
  fi
  log "--- PyTorch / ${model_name} ---"
  if $PYTHON -m src.training.train_brain_mri_torch --config "$CONFIG" --model "$model_name"; then
    ok "${outfile} produit"
  else
    fail "${model_name} a échoué"
    FAILED+=("torch/${model_name}")
  fi
}

log "=== Entraînement brain_mri — 7 modèles (convnexttiny exclu : trop lourd pour 4GB VRAM) ==="
log "Config : ${CONFIG}"
log "Option --skip-existing : ${SKIP_EXISTING}"
echo ""

# ── Modèles Keras (5) ────────────────────────────────────────────────────────
run_keras "baseline"        "brain_mri_baseline.keras"
run_keras "densenet121"     "brain_mri_densenet121.keras"
run_keras "efficientnetv2b0" "brain_mri_efficientnetv2b0.keras"
run_keras "resnet50v2"      "brain_mri_resnet50v2.keras"

# ── Modèles PyTorch (3) ──────────────────────────────────────────────────────
run_torch "densenet121_torch" "brain_mri_densenet121_torch.pt"
run_torch "resnet50_torch"    "brain_mri_resnet50_torch.pt"
run_torch "swin_v2_s_torch"   "brain_mri_swin_v2_s_torch.pt"

echo ""
if [ ${#FAILED[@]} -eq 0 ]; then
  log "=== Tous les entraînements terminés ==="
  log "Prochaine étape : python scripts/convert_to_onnx.py"
  exit 0
else
  fail "=== ${#FAILED[@]} entraînement(s) en échec : ${FAILED[*]} ==="
  exit 1
fi
