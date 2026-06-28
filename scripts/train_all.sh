#!/usr/bin/env bash
# =============================================================================
# train_all.sh — Entraîne TOUS les modèles MedVision AI (17) en une commande.
# -----------------------------------------------------------------------------
# Purpose  : Orchestrer l'entraînement complet du catalogue, en respectant les
#            deux environnements séparés (.venv TensorFlow / .venv-torch PyTorch),
#            puis convertir tous les modèles en ONNX.
#              - Chest X-ray classif (6) : baseline, optimized, densenet121,
#                efficientnetv2b0, convnexttiny, resnet50v2          [TF]
#              - Brain MRI classif Keras (6) : mêmes backbones        [TF]
#              - Brain MRI classif PyTorch (3) : densenet121_torch,
#                resnet50_torch, swin_v2_s_torch                      [torch]
#              - Segmentation U-Net (2) : brain_tumor, chest_xray     [TF]
# Usage    : bash scripts/train_all.sh [options]
#            Options :
#              --skip-existing  Saute un modèle si son fichier de sortie existe
#              --no-download    Ne (re)télécharge pas les datasets
#              --no-torch       Saute les 3 modèles PyTorch
#              --no-onnx        Ne convertit pas en ONNX à la fin
#              -h | --help      Affiche cette aide
# Arguments: aucun argument positionnel.
# Exit     : 0 si tous les modèles demandés sont OK ; 1 si au moins un échec.
# Pré-requis : bash scripts/install_prereqs.sh (les 2 envs + GPU + accès Kaggle).
# NB       : entraînement GPU long (heures). Lancer de préférence dans tmux.
# =============================================================================
set -uo pipefail

# --- options ----------------------------------------------------------------
SKIP_EXISTING=0; DO_DOWNLOAD=1; DO_TORCH=1; DO_ONNX=1
for arg in "$@"; do
  case "$arg" in
    --skip-existing) SKIP_EXISTING=1 ;;
    --no-download)   DO_DOWNLOAD=0 ;;
    --no-torch)      DO_TORCH=0 ;;
    --no-onnx)       DO_ONNX=0 ;;
    -h|--help)       sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $arg" >&2; exit 2 ;;
  esac
done

# --- helpers ----------------------------------------------------------------
c_blue=$'\033[1;34m'; c_grn=$'\033[1;32m'; c_yel=$'\033[1;33m'; c_red=$'\033[1;31m'; c_off=$'\033[0m'
log()  { echo "${c_blue}[$(date +%H:%M:%S)]${c_off} $*"; }
ok()   { echo "${c_grn}[ ok ]${c_off} $*"; }
warn() { echo "${c_yel}[warn]${c_off} $*" >&2; }
die()  { echo "${c_red}[fail]${c_off} $*" >&2; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$REPO_DIR" || exit 1
MODELS_DIR="artifacts/models"
ORIG_LD="${LD_LIBRARY_PATH:-}"
FAILED=()

[ -x ".venv/bin/python" ] || die "Env TensorFlow absent (.venv) — lancer : bash scripts/install_prereqs.sh"

# Bascule d'environnement (le LD_LIBRARY_PATH cu12 de TF casserait torch, et inversement).
activate_tf() {
  # shellcheck disable=SC1091
  { set +u; deactivate 2>/dev/null || true; source .venv/bin/activate; set -u; }
  LD_LIBRARY_PATH="$ORIG_LD"; export LD_LIBRARY_PATH
  # shellcheck disable=SC1091
  source scripts/gpu_env.sh >/dev/null 2>&1 || warn "gpu_env.sh indisponible — TF sur CPU."
}
activate_torch() {
  # shellcheck disable=SC1091
  { set +u; deactivate 2>/dev/null || true; source .venv-torch/bin/activate; set -u; }
  LD_LIBRARY_PATH="$ORIG_LD"; export LD_LIBRARY_PATH   # torch trouve ses libs cu13 seul
}

# train <label> <fichier_sortie_attendu> <cmd...>
train() {
  local label="$1" out="$2"; shift 2
  if [ "$SKIP_EXISTING" -eq 1 ] && [ -f "${MODELS_DIR}/${out}" ]; then
    log "SKIP (existe) : ${label} → ${out}"; return 0
  fi
  log "▶ ${label}"
  if "$@"; then ok "${label} → ${out}"; else warn "${label} a ÉCHOUÉ"; FAILED+=("$label"); fi
}

# === Phase 1 — TensorFlow (.venv) ==========================================
log "=== Phase 1/3 — Modèles TensorFlow (.venv) ==="
activate_tf
python -c "import tensorflow as tf; print('  TF GPU:', bool(tf.config.list_physical_devices('GPU')))" 2>/dev/null || true

if [ "$DO_DOWNLOAD" -eq 1 ]; then
  log "Téléchargement des datasets (Kaggle)…"
  python -m src.data.download_dataset                                              || warn "download chest classif"
  python -m src.data.download_brain_mri_dataset --config configs/brain_tumor_mri.yaml || warn "download brain_mri"
  python -m src.data.download_segmentation_dataset --problem brain_tumor_seg        || warn "download brain seg"
  python -m src.data.download_segmentation_dataset --problem chest_xray_seg         || warn "download chest seg"
fi

# Chest X-ray classification — tous les backbones
for m in baseline optimized densenet121 efficientnetv2b0 convnexttiny resnet50v2; do
  out=$([ "$m" = baseline ] && echo "baseline_model.keras" || echo "${m}_model.keras")
  train "chest/${m}" "$out" python -m src.training.train --config configs/config.yaml --model "$m"
done

# Brain MRI classification Keras — script dédié (tous les backbones)
log "▶ brain_mri Keras (tous les backbones)"
if [ "$SKIP_EXISTING" -eq 1 ]; then
  bash scripts/run_training_brain_mri_all.sh --skip-existing || FAILED+=("brain_mri/keras")
else
  bash scripts/run_training_brain_mri_all.sh || FAILED+=("brain_mri/keras")
fi

# Segmentation U-Net (préparation + entraînement)
python -m src.data.prepare_segmentation_dataset --config configs/brain_tumor_segmentation.yaml || warn "prepare brain seg"
train "seg/brain_tumor" "brain_tumor_segmentation_unet.keras" \
  python -m src.segmentation.train_segmentation --config configs/brain_tumor_segmentation.yaml
python -m src.data.prepare_segmentation_dataset --config configs/chest_xray_segmentation.yaml || warn "prepare chest seg"
train "seg/chest_xray" "chest_xray_segmentation_unet.keras" \
  python -m src.segmentation.train_segmentation --config configs/chest_xray_segmentation.yaml

# === Phase 2 — PyTorch (.venv-torch) =======================================
if [ "$DO_TORCH" -eq 1 ]; then
  if [ -x ".venv-torch/bin/python" ]; then
    log "=== Phase 2/3 — Modèles PyTorch (.venv-torch) ==="
    activate_torch
    python -c "import torch; print('  torch CUDA:', torch.cuda.is_available())" 2>/dev/null || true
    for m in densenet121_torch resnet50_torch swin_v2_s_torch; do
      train "brain_mri/${m}" "brain_mri_${m}.pt" \
        python -m src.training.train_brain_mri_torch --config configs/brain_tumor_mri.yaml --model "$m"
    done
  else
    warn "Env PyTorch absent (.venv-torch) — 3 modèles torch sautés. (install_prereqs.sh)"
  fi
else
  log "Phase PyTorch sautée (--no-torch)."
fi

# === Phase 3 — Conversion ONNX =============================================
if [ "$DO_ONNX" -eq 1 ]; then
  log "=== Phase 3/3 — Conversion ONNX ==="
  # Keras → ONNX dans l'env TF (les .pt y échouent → toléré ; ils seront faits ensuite).
  activate_tf
  python scripts/convert_to_onnx.py || warn "conversion keras : des .pt ont échoué ici (normal)."
  # .pt → ONNX dans l'env torch (les .keras déjà convertis sont skippés → doit réussir).
  if [ "$DO_TORCH" -eq 1 ] && [ -x ".venv-torch/bin/python" ]; then
    activate_torch
    python scripts/convert_to_onnx.py || FAILED+=("convert_to_onnx(.pt)")
  fi
fi

# === Récap ==================================================================
{ set +u; deactivate 2>/dev/null || true; set -u; }
echo
log "=== Récapitulatif ==="
log "Artefacts dans ${MODELS_DIR} : $(ls "${MODELS_DIR}"/*.keras 2>/dev/null | wc -l) keras, \
$(ls "${MODELS_DIR}"/*.pt 2>/dev/null | wc -l) pt, $(ls "${MODELS_DIR}"/*.onnx 2>/dev/null | wc -l) onnx"
if [ "${#FAILED[@]}" -eq 0 ]; then
  ok "Tous les modèles demandés sont passés."
else
  warn "Échecs (${#FAILED[@]}) : ${FAILED[*]}"
fi
cat <<'EOF'

Pousser vers S3 + déployer k3s :
  # ATTENTION : dvc.yaml ne suit que 4 ONNX (optimized + segmentation + baseline).
  # Les autres backbones ne seront PAS poussés tant que le câblage dvc.yaml n'est pas étendu.
  source .venv/bin/activate && source scripts/gpu_env.sh
  dvc repro && dvc push                         # modèles câblés → S3
  bash scripts/redeploy-k3s.sh "$(date +%Y-%m-%d)a"   # rollout k3s (pods refont dvc pull)
EOF
[ "${#FAILED[@]}" -eq 0 ] || exit 1
