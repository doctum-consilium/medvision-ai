#!/bin/bash
# Purpose  : Point d'entrée du conteneur medvision-ai.
#            Récupère les artefacts ML (modèles, rapports) depuis S3 via DVC
#            avant de démarrer l'application, si les credentials AWS sont disponibles.
# Usage    : Automatique (ENTRYPOINT dans le Dockerfile).
# Arguments: Tout argument passé au conteneur est transmis à l'application ($@).
# Exit codes:
#   0  Application démarrée normalement.
#   >0 Erreur fatale dans l'application.
set -e

echo "[entrypoint] Démarrage medvision-ai..."

# ── Pull DVC depuis S3 ─────────────────────────────────────────────────────────
# Seul prérequis : les variables d'environnement AWS_ACCESS_KEY_ID et
# AWS_SECRET_ACCESS_KEY doivent être présentes (montées via Secret K8s).
if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    echo "[entrypoint] Credentials AWS détectés — tentative de dvc pull..."
    # DVC requiert un dépôt git. On initialise un repo vide si absent (conteneur sans .git).
    git rev-parse --git-dir > /dev/null 2>&1 || git init -q
    # On tire le stage convert_to_onnx, qui versionne les .onnx des 17 modèles du
    # registry (6 chest + 6 brain_mri Keras + 3 PyTorch + 2 segmentations). Les
    # stages d'entraînement (.keras/.pt) ne sont pas tirés en prod — l'entraînement
    # se fait sur machine ML (dvc repro), pas dans le pod.
    # --force : les modèles vivent sur un PVC partagé ; quand un hash change
    # côté S3, DVC refuse d'écraser les fichiers « unsaved » du volume sans
    # confirmation (incident 2026-07-18 : pods bloqués à 4 modèles). Le pod
    # est une copie jetable de la vérité S3 — l'écrasement est TOUJOURS voulu.
    if dvc pull convert_to_onnx --no-run-cache --force > /tmp/dvc-pull.log 2>&1; then
        cat /tmp/dvc-pull.log
        echo "[entrypoint] Artefacts récupérés depuis S3."
    else
        cat /tmp/dvc-pull.log
        echo "[entrypoint] dvc pull a échoué — l'app démarrera sans modèles (entraîner localement puis dvc push)."
    fi
else
    echo "[entrypoint] Pas de credentials AWS — artefacts locaux utilisés (si présents)."
fi

# ── Lancer l'application ──────────────────────────────────────────────────────
exec "$@"
