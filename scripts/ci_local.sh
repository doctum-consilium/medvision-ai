#!/usr/bin/env bash
# Purpose  : Rejouer EN LOCAL tous les checks de la CI GitHub Actions
#            (.github/workflows/ci.yml) AVANT de pousser, pour ne plus
#            découvrir un échec rouge sur la PR.
#
# Usage    : bash scripts/ci_local.sh
#            (appelé automatiquement par .githooks/pre-push)
#
# Checks   : 1) Ruff (src/ + tests/)
#            2) Pytest smoke (sans TF — rapide)
#            3) shellcheck -x (tous les .sh du projet)
#
# Notes    : Les tests TF (test_api.py) ne sont PAS joués ici car ils
#            nécessitent TF + 30 s de chargement. Ils tournent sur GitHub
#            Actions (job test-tf). Pour les jouer localement :
#            conda activate GPUMachineLearning && pytest tests/ -v
#
# Arguments : aucun.
# Exit codes: 0 = tout vert ; 1 = au moins un check a échoué.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT" || exit 1

# shellcheck source=.githooks/_lib.sh
. "$REPO_ROOT/.githooks/_lib.sh"

RUFF="$(hook_ruff)"
PY="$(hook_python)"
SHCHECK=""
hook_has shellcheck && SHCHECK="shellcheck"

# ── 1) Ruff ───────────────────────────────────────────────────────────────
hook_title "Ruff (src/ tests/)"
if [ -z "$RUFF" ]; then
  hook_fail "ruff absent — pip install ruff (la CI le lancera aussi)"
else
  if "$RUFF" check src/ tests/; then
    hook_ok "code propre"
  else
    hook_fail "problèmes ruff (ruff check --fix src/ tests/)"
  fi
fi

# ── 2) Tests smoke (sans TF) ──────────────────────────────────────────────
hook_title "Pytest smoke (sans TF)"
if [ -z "$PY" ]; then
  hook_fail "aucun python avec pytest — pip install pytest dans ton venv"
else
  if "$PY" -m pytest tests/smoke/ -q --tb=short; then
    hook_ok "smoke tests verts"
  else
    hook_fail "smoke tests échoués"
  fi
fi

# ── 3) shellcheck — scripts maintenus (pas la dette legacy Windows) ───────
hook_title "shellcheck (hooks + scripts maintenus)"
# On ne check QUE les scripts sous notre contrôle actuel, pas la dette legacy
# (scripts deploy/*.sh, scripts/*_segmentation_*.sh créés sous Windows avec CRLF).
MAINTAINED_SCRIPTS=(
  ".githooks/_lib.sh"
  ".githooks/pre-commit"
  ".githooks/pre-push"
  "scripts/ci_local.sh"
  "docker/entrypoint.sh"
)
if [ -z "$SHCHECK" ]; then
  hook_skip "shellcheck absent (sudo apt install shellcheck)"
else
  FAIL=0
  for f in "${MAINTAINED_SCRIPTS[@]}"; do
    if [ -f "$REPO_ROOT/$f" ]; then
      shellcheck -x "$REPO_ROOT/$f" || FAIL=1
    fi
  done
  if [ "$FAIL" -eq 0 ]; then
    hook_ok "${#MAINTAINED_SCRIPTS[@]} scripts maintenus propres"
  else
    hook_fail "shellcheck a trouvé des problèmes dans les scripts maintenus"
  fi
fi

hook_summary
