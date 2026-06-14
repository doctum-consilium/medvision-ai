#!/usr/bin/env bash
# Purpose  : Redéploie medvision-ai sur le cluster k3s OVH.
#
#            Les manifests Kubernetes sont dans k3s-fromOVHVps — ce script
#            ne contient PAS de YAML inline. Source de vérité unique :
#            k3s-fromOVHVps/rendered-k3s-manifests/30-medvision.yaml
#
#            Deux modes :
#              normal         — met à jour l'image des 3 deployments (pod crash, rollout).
#              --full-recovery — rebuild depuis zéro après perte du cluster k3s
#                               (labels nœuds, cert-manager, apply manifest complet).
#
# Usage    : ./scripts/redeploy-k3s.sh [TAG] [--full-recovery]
# Arguments:
#   TAG              Tag ECR de l'image (défaut : 2026-06-15f)
#   --full-recovery  À utiliser si k3s vient d'être réinstallé.
# Exit codes:
#   0  Déploiement réussi
#   1  Erreur (voir message)
#
# Prérequis :
#   - kubectl configuré (contexte pointant sur le cluster k3s)
#   - aws CLI connecté (aws sts get-caller-identity doit fonctionner)
#   - SSH sur worker-ovh-094 pour refresh containerd credentials (ECR)
#   - k3s-fromOVHVps cloné en parallèle (chemin : $K3S_REPO)
set -euo pipefail

REGISTRY="113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform"
REGION="eu-west-3"
IMAGE="${REGISTRY}/medvision-ai"
NAMESPACE="medvision"
WORKER_SSH_B="yannsmatti@51.38.235.94"   # worker-ovh-094 (apps-b)
WORKER_SSH_A="yannsmatti@141.94.121.233" # worker-ovh-233 (apps-a)

# Repo k3s — chemin relatif au répertoire parent de medvision-ai
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
K3S_REPO="${K3S_REPO:-$(cd "$REPO_ROOT/.." && pwd)/k3s-fromOVHVps}"
MANIFEST="${K3S_REPO}/rendered-k3s-manifests/30-medvision.yaml"

TAG="2026-06-16b"
FULL_RECOVERY=false

for arg in "$@"; do
  case "$arg" in
    --full-recovery) FULL_RECOVERY=true ;;
    --*)             echo "[ERREUR] Argument inconnu : $arg" >&2; exit 1 ;;
    *)               TAG="$arg" ;;
  esac
done

log()  { echo "[$(date +%H:%M:%S)] $*"; }
die()  { echo "[ERREUR] $*" >&2; exit 1; }
warn() { echo "[AVERT]  $*"; }

# ─── Vérification du manifest ────────────────────────────────────────────────
if [ ! -f "$MANIFEST" ]; then
  die "Manifest introuvable : $MANIFEST
     Vérifiez que k3s-fromOVHVps est cloné à côté de medvision-ai,
     ou définissez : K3S_REPO=/chemin/vers/k3s-fromOVHVps"
fi

# ─── 0. Full-recovery : prérequis cluster ────────────────────────────────────
# À faire uniquement après une réinstallation de k3s (perte du cluster).
if [ "$FULL_RECOVERY" = "true" ]; then
  log "=== MODE FULL RECOVERY ==="

  log "Nœuds actuels :"
  kubectl get nodes -o wide

  log "Pose des labels node-pool (5 s pour Ctrl-C si les noms de nœuds ne correspondent pas)…"
  read -r -t 5 || true

  MASTER_NODE=$(kubectl get nodes --selector='node-role.kubernetes.io/control-plane' \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
  WORKER_NODE=$(kubectl get nodes --selector='!node-role.kubernetes.io/control-plane' \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

  if [ -n "$MASTER_NODE" ]; then
    kubectl label node "$MASTER_NODE" node-pool=apps-a --overwrite
    log "  node-pool=apps-a → $MASTER_NODE"
  else
    warn "Master non détecté — labeler manuellement : kubectl label node <NOM> node-pool=apps-a"
  fi
  if [ -n "$WORKER_NODE" ]; then
    kubectl label node "$WORKER_NODE" node-pool=apps-b --overwrite
    log "  node-pool=apps-b → $WORKER_NODE"
  else
    warn "Worker non détecté — labeler manuellement : kubectl label node <NOM> node-pool=apps-b"
  fi

  # cert-manager
  if ! kubectl get namespace cert-manager >/dev/null 2>&1; then
    log "Installation cert-manager…"
    helm repo add jetstack https://charts.jetstack.io --force-update
    helm upgrade --install cert-manager jetstack/cert-manager \
      --namespace cert-manager --create-namespace \
      --set installCRDs=true --wait --timeout 5m
  else
    log "cert-manager OK ✓"
  fi

  # ClusterIssuer Let's Encrypt
  if ! kubectl get clusterissuer letsencrypt-prod >/dev/null 2>&1; then
    log "Création ClusterIssuer letsencrypt-prod…"
    kubectl apply -f "$K3S_REPO/rendered-k3s-manifests/00-namespaces.yaml" 2>/dev/null || true
    # Le ClusterIssuer est dans le script dédié du repo k3s si disponible
    if [ -f "$K3S_REPO/scripts/install_ingress_cert_manager.sh" ]; then
      bash "$K3S_REPO/scripts/install_ingress_cert_manager.sh"
    else
      warn "install_ingress_cert_manager.sh absent — créer le ClusterIssuer manuellement."
    fi
  else
    log "ClusterIssuer letsencrypt-prod OK ✓"
  fi

  # ingress-nginx
  if ! kubectl get namespace ingress-nginx >/dev/null 2>&1; then
    log "Installation ingress-nginx…"
    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx --force-update
    helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
      --namespace ingress-nginx --create-namespace --wait --timeout 5m
  else
    log "ingress-nginx OK ✓"
  fi

  log ""
  log "Prérequis cluster OK — démarrage du déploiement applicatif."
  log ""
fi

# ─── 1. Vérifications préalables ─────────────────────────────────────────────
log "kubectl cluster-info…"
kubectl cluster-info --request-timeout=5s >/dev/null 2>&1 \
  || die "kubectl ne répond pas. Vérifiez votre contexte k8s."

log "AWS credentials…"
aws sts get-caller-identity --query Account --output text >/dev/null 2>&1 \
  || die "AWS session expirée. Lancez : aws sso login"

log "Déploiement du tag ${TAG} sur le namespace ${NAMESPACE}…"

# ─── 2. Namespace ────────────────────────────────────────────────────────────
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
  || kubectl create namespace "$NAMESPACE"

# ─── 3. Refresh ECR credentials ──────────────────────────────────────────────
log "Refresh ECR token (TTL 12 h)…"
ECR_TOKEN=$(aws ecr get-login-password --region "$REGION")

# Méthode A : ecr-pull-secret (imagePullSecrets dans les pods)
kubectl create secret docker-registry ecr-pull-secret \
  --namespace="$NAMESPACE" \
  --docker-server="${REGISTRY%/platform}" \
  --docker-username=AWS \
  --docker-password="$ECR_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

# Méthode B : registries.yaml sur chaque nœud worker (containerd)
# apps-b = worker-ovh-094, apps-a = worker-ovh-233.
# apps-c (vps-7f9dbc3f) utilise uniquement ecr-pull-secret (SSH non configuré).
_refresh_worker() {
  local host="$1" label="$2"
  log "Refresh containerd registries.yaml sur ${label} (${host})…"
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$host" "
set -euo pipefail
sudo mkdir -p /etc/rancher/k3s
cat <<YAML | sudo tee /etc/rancher/k3s/registries.yaml
mirrors:
  ${REGISTRY%/platform}:
    endpoint:
      - \"https://${REGISTRY%/platform}\"
configs:
  \"${REGISTRY%/platform}\":
    auth:
      username: AWS
      password: \"${ECR_TOKEN}\"
YAML
sudo systemctl restart k3s-agent
echo 'k3s-agent redémarré'
" || warn "SSH vers ${host} a échoué — ecr-pull-secret sera utilisé à la place."
}

_refresh_worker "$WORKER_SSH_B" "apps-b (worker-ovh-094)"
_refresh_worker "$WORKER_SSH_A" "apps-a (worker-ovh-233)"
sleep 10

# ─── 4. Secret AWS (pour dvc pull depuis S3 au démarrage du pod) ─────────────
log "Secret medvision-aws-creds…"
kubectl create secret generic medvision-aws-creds \
  --namespace="$NAMESPACE" \
  --from-literal=AWS_ACCESS_KEY_ID="$(aws configure get aws_access_key_id)" \
  --from-literal=AWS_SECRET_ACCESS_KEY="$(aws configure get aws_secret_access_key)" \
  --from-literal=AWS_DEFAULT_REGION="$REGION" \
  --dry-run=client -o yaml | kubectl apply -f -

# ─── 5. Apply du manifest (source de vérité) ─────────────────────────────────
# Le manifest k3s-fromOVHVps/rendered-k3s-manifests/30-medvision.yaml contient
# tous les objets k8s (ConfigMap, PVCs, Deployments, Services, Ingress).
# On l'applique tel quel — l'image sera mise à jour juste après via kubectl set image.
log "Apply manifest k3s : $MANIFEST"
kubectl apply -f "$MANIFEST"

# ─── 6. Mise à jour de l'image ───────────────────────────────────────────────
# kubectl set image est la méthode recommandée pour mettre à jour un tag sans
# toucher au manifest (le manifest garde le tag de référence ; le cluster a le
# tag réel). Pour un tag permanent, mettre à jour 30-medvision.yaml dans
# k3s-fromOVHVps et commiter.
log "Mise à jour de l'image → ${IMAGE}:${TAG}"
NEW_IMAGE="${IMAGE}:${TAG}"
kubectl set image deployment/medvision-api      "api=${NEW_IMAGE}"       -n "$NAMESPACE"
kubectl set image deployment/medvision-streamlit "streamlit=${NEW_IMAGE}" -n "$NAMESPACE"
kubectl set image deployment/medvision-mlflow   "mlflow=${NEW_IMAGE}"    -n "$NAMESPACE"

# ─── 7. Attente des rollouts ─────────────────────────────────────────────────
log "Attente rollout medvision-api…"
kubectl rollout status deployment/medvision-api -n "$NAMESPACE" --timeout=180s

log "Attente rollout medvision-streamlit…"
kubectl rollout status deployment/medvision-streamlit -n "$NAMESPACE" --timeout=180s

# ─── 8. Vérification finale ──────────────────────────────────────────────────
log "État des pods :"
kubectl get pods -n "$NAMESPACE" -o wide

log "Modèles dans le pod API (dvc pull au démarrage) :"
if kubectl exec -n "$NAMESPACE" deploy/medvision-api -- ls /app/artifacts/models/ 2>/dev/null; then
  log "Modèles OK ✓"
else
  warn "/app/artifacts/models absent ou vide — dvc pull a peut-être échoué."
  warn "Vérifier : kubectl logs -n medvision deploy/medvision-api | grep dvc"
fi

log ""
log "=== DÉPLOIEMENT TERMINÉ ==="
log "API    : https://api.medvision.doctumconsilium.com"
log "App    : https://app.medvision.doctumconsilium.com"
log "MLflow : kubectl port-forward -n medvision svc/medvision-mlflow 5000"

if [ "$FULL_RECOVERY" = "true" ]; then
  log ""
  log "=== RÉCUPÉRATION DES DONNÉES (si PVCs vides) ==="
  log "Données brutes (radiographies) — re-télécharger depuis Kaggle :"
  log "  bash scripts/download_segmentation_brain.sh"
  log "  kubectl cp data/raw/ medvision/<pod>:/app/data/raw/"
  log ""
  log "Modèles ML — depuis S3 via DVC (auto au démarrage, sinon forcer) :"
  log "  kubectl exec -n medvision deploy/medvision-api -- dvc pull artifacts/"
  log "  Si S3 vide : entraîner localement puis bash scripts/migrate-models-to-s3.sh"
fi
