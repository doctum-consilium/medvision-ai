#!/usr/bin/env bash
# =============================================================================
# install_prereqs.sh — Installe TOUS les pré-requis de MedVision AI
# -----------------------------------------------------------------------------
# Purpose  : Amener une machine Ubuntu (native OU WSL2) de zéro à un poste de
#            développement/entraînement fonctionnel : paquets système, Python
#            3.10–3.12, les DEUX environnements virtuels (TensorFlow GPU +
#            PyTorch/vision), stack CUDA via wheels pip, et contrôle des accès.
# Usage    : bash scripts/install_prereqs.sh [options]
#            Options :
#              --no-torch    N'installe pas l'env PyTorch (.venv-torch)
#              --no-system   Saute l'étape apt (paquets système déjà présents)
#              --cpu         Force CPU (ignore la vérification GPU)
#              -h | --help   Affiche cette aide
# Arguments: aucun argument positionnel.
# Exit     : 0 succès ; 1 erreur fatale ; 2 mauvaise option.
# Plateforme : Ubuntu 22.04 / 24.04, natif ou WSL2. Idempotent (ré-exécutable).
# NB       : sur WSL2, le driver NVIDIA vient de Windows (ne PAS l'installer ici).
#            La stack CUDA (cuDNN/NCCL/cuBLAS) est fournie par les wheels pip
#            (tensorflow[and-cuda], torch+cu124) — aucun CUDA toolkit système requis.
# =============================================================================
set -euo pipefail

# --- options ----------------------------------------------------------------
INSTALL_TORCH=1; INSTALL_SYSTEM=1; FORCE_CPU=0
for arg in "$@"; do
  case "$arg" in
    --no-torch)  INSTALL_TORCH=0 ;;
    --no-system) INSTALL_SYSTEM=0 ;;
    --cpu)       FORCE_CPU=1 ;;
    -h|--help)   sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $arg" >&2; exit 2 ;;
  esac
done

# --- helpers ----------------------------------------------------------------
c_blue=$'\033[1;34m'; c_grn=$'\033[1;32m'; c_yel=$'\033[1;33m'; c_red=$'\033[1;31m'; c_off=$'\033[0m'
log()  { echo "${c_blue}[install]${c_off} $*"; }
ok()   { echo "${c_grn}[ ok ]${c_off} $*"; }
warn() { echo "${c_yel}[warn]${c_off} $*" >&2; }
die()  { echo "${c_red}[fail]${c_off} $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
log "Répertoire projet : $REPO_DIR"

SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

# --- 0. détection environnement --------------------------------------------
IS_WSL=0
if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then IS_WSL=1; fi
log "Plateforme : $([ "$IS_WSL" -eq 1 ] && echo 'Ubuntu WSL2' || echo 'Ubuntu natif')"
if have lsb_release; then log "Distrib : $(lsb_release -ds 2>/dev/null)"; fi

# --- 1. paquets système (apt) -----------------------------------------------
if [ "$INSTALL_SYSTEM" -eq 1 ]; then
  have apt-get || die "apt-get introuvable — ce script cible Ubuntu/Debian."
  log "Installation des paquets système (sudo requis)…"
  $SUDO apt-get update -y
  $SUDO apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev python3-pip \
    build-essential pkg-config \
    git git-lfs curl wget unzip ca-certificates \
    ffmpeg libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    tmux jq
  git lfs install --skip-repo 2>/dev/null || true
  ok "Paquets système installés."
else
  warn "Étape système sautée (--no-system)."
fi

# --- 2. choix de l'interpréteur Python (3.10–3.12) --------------------------
pick_python() {
  local p
  for p in python3.12 python3.11 python3.10; do
    have "$p" && { echo "$p"; return 0; }
  done
  if have python3; then
    local v; v="$(python3 -c 'import sys;print("%d%d"%sys.version_info[:2])')"
    if [ "$v" -ge 310 ] && [ "$v" -lt 313 ]; then echo "python3"; return 0; fi
  fi
  return 1
}
if ! PYBIN="$(pick_python)"; then
  warn "Aucun Python 3.10–3.12 trouvé (TensorFlow 2.16 refuse 3.13+). Tentative d'installation de python3.12…"
  if [ "$INSTALL_SYSTEM" -eq 1 ]; then
    $SUDO apt-get install -y python3.12 python3.12-venv python3.12-dev 2>/dev/null \
      || { $SUDO add-apt-repository -y ppa:deadsnakes/ppa && $SUDO apt-get update -y \
           && $SUDO apt-get install -y python3.12 python3.12-venv python3.12-dev; }
  fi
  PYBIN="$(pick_python)" || die "Impossible d'obtenir un Python 3.10–3.12."
fi
log "Interpréteur Python : $PYBIN ($("$PYBIN" --version 2>&1))"

# --- 3. environnement TensorFlow (.venv) ------------------------------------
create_venv() {  # $1=dir $2=python
  if [ -d "$1" ] && [ -x "$1/bin/python" ]; then ok "venv déjà présent : $1"; else
    log "Création venv $1…"; "$2" -m venv "$1"; fi
}
log "=== Environnement TensorFlow (.venv) ==="
create_venv ".venv" "$PYBIN"
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
log "Installation requirements-train.txt (TensorFlow + CUDA, peut être long)…"
pip install -r requirements-train.txt
deactivate
ok "Environnement TensorFlow prêt."

# --- 4. environnement PyTorch (.venv-torch) ---------------------------------
if [ "$INSTALL_TORCH" -eq 1 ]; then
  log "=== Environnement PyTorch / vision (.venv-torch) ==="
  create_venv ".venv-torch" "$PYBIN"
  # shellcheck disable=SC1091
  source .venv-torch/bin/activate
  python -m pip install --upgrade pip wheel setuptools
  log "Installation requirements-torch.txt (torch+cu124, peut être long)…"
  pip install -r requirements-torch.txt
  deactivate
  ok "Environnement PyTorch prêt."
else
  warn "Env PyTorch sauté (--no-torch)."
fi

# --- 5. vérification GPU ------------------------------------------------------
if [ "$FORCE_CPU" -eq 0 ]; then
  log "=== Vérification GPU ==="
  if have nvidia-smi && nvidia-smi -L >/dev/null 2>&1; then
    ok "Driver NVIDIA détecté : $(nvidia-smi -L | head -1)"
    # TensorFlow (nécessite gpu_env.sh)
    # shellcheck disable=SC1091
    source .venv/bin/activate; source scripts/gpu_env.sh >/dev/null 2>&1 || true
    if python -c "import tensorflow as tf; import sys; sys.exit(0 if tf.config.list_physical_devices('GPU') else 1)" 2>/dev/null; then
      ok "TensorFlow voit le GPU."
    else
      warn "TensorFlow ne voit pas le GPU — vérifier 'source scripts/gpu_env.sh' avant l'entraînement."
    fi
    deactivate
    if [ "$INSTALL_TORCH" -eq 1 ]; then
      # shellcheck disable=SC1091
      source .venv-torch/bin/activate
      if python -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
        ok "PyTorch voit le GPU."
      else
        warn "PyTorch ne voit pas le GPU."
      fi
      deactivate
    fi
  else
    warn "nvidia-smi absent."
    if [ "$IS_WSL" -eq 1 ]; then
      warn "WSL2 : installe le driver NVIDIA *Windows* (support WSL) côté hôte, puis relance."
    else
      warn "Ubuntu natif : installe le driver NVIDIA, ex. 'sudo ubuntu-drivers autoinstall' puis redémarre."
    fi
  fi
fi

# --- 6. contrôle des accès (AWS / Kaggle) -----------------------------------
# Les "~/.aws/..." ci-dessous sont des messages destinés à l'utilisateur (littéral voulu).
# shellcheck disable=SC2088
log "=== Accès (DVC/S3 + Kaggle) ==="
[ -f "$HOME/.aws/credentials" ] && ok "~/.aws/credentials présent." \
  || warn "~/.aws/credentials manquant → 'aws configure' (region eu-west-3) pour 'dvc pull/push'."
[ -f "$HOME/.aws/config" ] && grep -q 'region' "$HOME/.aws/config" 2>/dev/null && ok "~/.aws/config OK." \
  || warn "~/.aws/config sans region → printf '[default]\\nregion = eu-west-3\\noutput = json\\n' > ~/.aws/config"
[ -f "$HOME/.kaggle/kaggle.json" ] && ok "~/.kaggle/kaggle.json présent." \
  || warn "~/.kaggle/kaggle.json manquant → requis par scripts/download_*.sh (kaggle.com/settings)."

# --- 7. récap ----------------------------------------------------------------
echo
ok "Installation terminée."
cat <<EOF

Prochaines étapes :
  # Pipeline TensorFlow (entraîne tous les modèles + ONNX) :
  source .venv/bin/activate && source scripts/gpu_env.sh
  dvc pull          # récupère les modèles/datasets depuis S3 (accès AWS requis)
  dvc repro         # ré-entraîne tout ce qui est périmé

  # Modèles PyTorch / vision (env séparé) :
  source .venv-torch/bin/activate
  python -m src.training.train_brain_mri_torch --help

Détails : ONBOARDING.md
EOF
