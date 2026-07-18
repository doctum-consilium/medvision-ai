#!/usr/bin/env bash
# Purpose : rendre le GPU visible à TensorFlow 2.16 quand les libs CUDA viennent
#           des wheels pip (tensorflow[and-cuda]). TF 2.16.1 ne déclare pas seul
#           ses libs → on ajoute les dossiers nvidia/*/lib à LD_LIBRARY_PATH.
# Usage   : source scripts/gpu_env.sh   (puis : dvc repro  /  python -m src.training.train ...)
# Args    : aucun. Lire la variable d'env LD_LIBRARY_PATH en sortie.
# Exit    : 0 si les libs nvidia sont trouvées, sinon laisse l'env inchangé (CPU).
# Portable : aucun chemin en dur — les dossiers sont dérivés du package `nvidia`
#            installé dans l'environnement Python courant (venv ou conda).

_nv_base="$(python -c 'import nvidia, os; print(os.path.dirname(nvidia.__file__))' 2>/dev/null)"
if [ -n "${_nv_base}" ] && [ -d "${_nv_base}" ]; then
  for _d in "${_nv_base}"/*/lib; do
    [ -d "${_d}" ] && LD_LIBRARY_PATH="${_d}:${LD_LIBRARY_PATH}"
  done
  export LD_LIBRARY_PATH
  echo "[gpu_env] LD_LIBRARY_PATH enrichi depuis ${_nv_base}"
else
  echo "[gpu_env] package 'nvidia' introuvable — TensorFlow tournera sur CPU." >&2
fi
unset _nv_base _d
