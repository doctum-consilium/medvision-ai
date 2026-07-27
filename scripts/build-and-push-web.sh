#!/usr/bin/env bash
# Purpose  : Construit et pousse l'image de l'interface web MedVision (nginx)
#            vers ECR.
#
#            Image SÉPARÉE de `medvision-ai` : celle-ci ne contient que des
#            fichiers statiques et nginx (~40 Mo), on la reconstruit en moins
#            d'une minute sans toucher à l'image d'inférence de plusieurs
#            gigaoctets.
#
# Usage    : ./scripts/build-and-push-web.sh [TAG]
# Arguments:
#   TAG   Tag ECR de l'image. Défaut : la date du jour (AAAA-MM-JJ).
#         Un rebuild le même jour après un échec de déploiement prend un
#         suffixe : 2026-07-27b, 2026-07-27c… On n'écrase JAMAIS un tag
#         existant : les nœuds ont `imagePullPolicy: IfNotPresent` et
#         garderaient l'ancienne image.
# Exit codes:
#   0  Image poussée
#   1  Erreur (voir message)
#
# Prérequis :
#   - Docker en marche
#   - aws CLI connecté (le jeton ECR expire toutes les 12 h : ce script le
#     rafraîchit lui-même)
#   - Le dépôt ECR doit exister. Création (une seule fois) :
#       aws ecr create-repository --repository-name platform/medvision-web \
#         --region eu-west-3
set -euo pipefail

REGISTRY="113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform"
REGION="eu-west-3"
IMAGE="${REGISTRY}/medvision-web"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"

TAG="${1:-$(date +%Y-%m-%d)}"

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "[ERREUR] $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker introuvable"
command -v aws    >/dev/null 2>&1 || die "aws CLI introuvable"
aws sts get-caller-identity >/dev/null 2>&1 \
  || die "aws non connecté — lance 'eval \$(aws configure export-credentials --format env)'"

# ─── Vérification préalable : le front doit compiler ─────────────────────
# Le faire ici plutôt que de laisser échouer le build Docker : l'erreur de
# compilation est bien plus lisible en local, et on économise le transfert
# du contexte Docker.
log "Compilation de contrôle du front…"
( cd "$REPO_ROOT/frontend" && npm ci --silent && npm run build ) \
  || die "le front ne compile pas — corrige avant de construire l'image"

# ─── Jeton ECR (expire toutes les 12 h) ─────────────────────────────────
log "Connexion à ECR…"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY" \
  || die "échec de la connexion ECR"

# ─── Construction ───────────────────────────────────────────────────────
log "Construction de ${IMAGE}:${TAG}…"
docker build \
  -f "$REPO_ROOT/docker/frontend.Dockerfile" \
  -t "${IMAGE}:${TAG}" \
  "$REPO_ROOT" \
  || die "échec du build Docker"

log "Envoi vers ECR…"
docker push "${IMAGE}:${TAG}" || die "échec du push"

log "Image poussée : ${IMAGE}:${TAG}"
echo
echo "── À FAIRE MAINTENANT ────────────────────────────────────────────────"
echo "  1. Mettre à jour le tag dans le dépôt k3s-fromOVHVps :"
echo "       deploy/platform/30-medvision.template.yaml"
echo "       rendered-k3s-manifests/30-medvision.yaml"
echo "     (chercher 'medvision-web:' — remplacer par ${TAG})"
echo "  2. Déployer :"
echo "       kubectl -n medvision set image deploy/medvision-web web=${IMAGE}:${TAG}"
echo "  3. Consigner le tag dans docs/SESSION-STATE.md."
echo "─────────────────────────────────────────────────────────────────────"
