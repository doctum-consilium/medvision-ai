#!/usr/bin/env bash
# Helpers communs aux hooks git de ce repo.
# Source : `. "$(dirname "$0")/_lib.sh"`.

set -uo pipefail

# ── Couleurs (désactivées si stdout n'est pas un TTY) ─────────────────────
if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'; C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
else
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_DIM=""; C_RESET=""
fi

HOOK_ERRORS=0
HOOK_SKIPS=0

hook_title()  { printf "%s──[ %s ]%s\n" "$C_BLUE" "$1" "$C_RESET"; }
hook_ok()     { printf "%s✓%s %s\n" "$C_GREEN" "$C_RESET" "$1"; }
hook_warn()   { printf "%s⚠%s %s\n" "$C_YELLOW" "$C_RESET" "$1"; }
hook_skip()   { printf "%s↷%s %s\n" "$C_DIM" "$C_RESET" "$1"; HOOK_SKIPS=$((HOOK_SKIPS+1)); }
hook_fail()   { printf "%s✗%s %s\n" "$C_RED" "$C_RESET" "$1"; HOOK_ERRORS=$((HOOK_ERRORS+1)); }
hook_has()    { command -v "$1" >/dev/null 2>&1; }

filter_ext() {
  local ext="$1"; shift
  for f in "$@"; do case "$f" in *.${ext}) printf "%s\n" "$f" ;; esac; done
}

staged_files() { git diff --cached --name-only --diff-filter=ACMR; }

# Recherche le binaire python qui a pytest.
hook_python() {
  for cand in \
    "${VIRTUAL_ENV:-NONE}/bin/python" \
    "$(conda info --base 2>/dev/null)/envs/GPUMachineLearning/bin/python" \
    python3 python; do
    [ "$cand" = "NONE/bin/python" ] && continue
    [ -x "$cand" ] || continue
    # Exige pytest ET Python ≥ 3.10 : le projet utilise la syntaxe d'union `X | None`
    # (PEP 604), que 3.9 ne sait pas évaluer — la CI tourne en 3.10. Sans ce garde,
    # le hook pouvait choisir un env 3.9 (ex. GPUMachineLearning) et échouer à tort.
    if "$cand" -c "import pytest, sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
      echo "$cand"; return
    fi
  done
  echo ""
}

# Recherche ruff dans le venv courant ou le PATH.
hook_ruff() {
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/ruff" ]; then
    echo "$VIRTUAL_ENV/bin/ruff"
  elif hook_has ruff; then
    echo ruff
  else
    echo ""
  fi
}

hook_summary() {
  echo
  if [ "$HOOK_ERRORS" -gt 0 ]; then
    printf "%s%d erreur(s)%s · %d outil(s) sauté(s)\n" "$C_RED" "$HOOK_ERRORS" "$C_RESET" "$HOOK_SKIPS"
    return 1
  fi
  if [ "$HOOK_SKIPS" -gt 0 ]; then
    printf "%sok%s (%d outil(s) sauté(s) — installer pour couvrir +)\n" "$C_GREEN" "$C_RESET" "$HOOK_SKIPS"
  else
    printf "%sok%s\n" "$C_GREEN" "$C_RESET"
  fi
  return 0
}
