#!/usr/bin/env bash
# Purpose  : Redéploie medvision-ai sur le cluster k3s OVH.
#            Deux modes :
#              - normal         : met à jour l'image, re-sync configs (pod crash, rollout).
#              - --full-recovery: rebuild depuis zéro après perte du cluster k3s
#                                 (labels nœuds, cert-manager, PVCs, tout).
#
# Usage    : ./scripts/redeploy-k3s.sh [TAG] [--full-recovery]
# Arguments:
#   TAG             Tag ECR de l'image (défaut : 2026-06-15f)
#   --full-recovery Rétablit les prérequis cluster avant le déploiement.
#                   À utiliser si k3s vient d'être réinstallé.
# Exit codes:
#   0  Déploiement réussi, tous les pods Running
#   1  Erreur (voir message)
#
# Prérequis :
#   - kubectl configuré (contexte pointant sur le cluster k3s)
#   - aws CLI connecté (aws sts get-caller-identity doit fonctionner)
#   - SSH sur worker-ovh-094 (51.38.235.94) pour refresh containerd credentials
#
# Namespaces créés : medvision
# Images ECR       : platform/medvision-ai:TAG (api, streamlit, mlflow)
# PVCs             : medvision-raw-data, medvision-mlflow-store, medvision-model-artifacts
#
# Modèles ML :
#   Téléchargés depuis S3 via dvc pull au démarrage du pod (entrypoint.sh).
#   En cas de perte des modèles en S3 : relancer l'entraînement local
#   puis bash scripts/migrate-models-to-s3.sh.
#
# Nœuds attendus :
#   node-pool=apps-a → master-ovh-xxx  (MLflow, services légers)
#   node-pool=apps-b → worker-ovh-094  (API + Streamlit, inférence CPU)
set -euo pipefail

REGISTRY="113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform"
REGION="eu-west-3"
TAG="${1:-2026-06-15f}"
NAMESPACE="medvision"
WORKER_SSH="yannsmatti@51.38.235.94"
FULL_RECOVERY=false

# Parse args (TAG peut être absent si seul --full-recovery est passé)
for arg in "$@"; do
  if [ "$arg" = "--full-recovery" ]; then
    FULL_RECOVERY=true
  fi
done
# Si le premier arg est --full-recovery, TAG reste la valeur par défaut
if [ "${1:-}" = "--full-recovery" ]; then
  TAG="2026-06-15f"
fi

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "[ERREUR] $*" >&2; exit 1; }
warn() { echo "[AVERT]  $*"; }

# ─── 0. Full-recovery : prérequis cluster ───────────────────────────────────
# À faire uniquement après une réinstallation de k3s (perte du cluster).
# En mode normal (pod crash / rollout), cette section est sautée.
if [ "$FULL_RECOVERY" = "true" ]; then
  log "=== MODE FULL RECOVERY ==="
  log "Ce mode recrée les labels nœuds, vérifie cert-manager et l'ingress-nginx."
  log ""

  # Labels nœuds — obtenus via 'kubectl get nodes'
  log "Nœuds actuels :"
  kubectl get nodes -o wide

  log ""
  log "Ajout des labels node-pool sur les nœuds (adapter si les noms ont changé) :"
  log "  Appuyez sur Ctrl-C maintenant si les noms de nœuds listés ci-dessus ne correspondent pas."
  log "  Attendez 5 s ou Entrée pour continuer..."
  read -r -t 5 || true

  # Récupère le nom du master (premier nœud avec rôle control-plane)
  MASTER_NODE=$(kubectl get nodes --selector='node-role.kubernetes.io/control-plane' -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
  WORKER_NODE=$(kubectl get nodes --selector='!node-role.kubernetes.io/control-plane' -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

  if [ -n "$MASTER_NODE" ]; then
    kubectl label node "$MASTER_NODE" node-pool=apps-a --overwrite
    log "Label apps-a → $MASTER_NODE"
  else
    warn "Impossible de détecter le master — labeler manuellement : kubectl label node <NOM> node-pool=apps-a"
  fi

  if [ -n "$WORKER_NODE" ]; then
    kubectl label node "$WORKER_NODE" node-pool=apps-b --overwrite
    log "Label apps-b → $WORKER_NODE"
  else
    warn "Impossible de détecter le worker — labeler manuellement : kubectl label node <NOM> node-pool=apps-b"
  fi

  # cert-manager
  log "Vérification cert-manager…"
  if ! kubectl get namespace cert-manager >/dev/null 2>&1; then
    log "cert-manager absent — installation via Helm…"
    helm repo add jetstack https://charts.jetstack.io --force-update
    helm upgrade --install cert-manager jetstack/cert-manager \
      --namespace cert-manager --create-namespace \
      --set installCRDs=true \
      --wait --timeout 5m
  else
    log "cert-manager déjà installé ✓"
  fi

  # ClusterIssuer Let's Encrypt (si absent)
  if ! kubectl get clusterissuer letsencrypt-prod >/dev/null 2>&1; then
    log "ClusterIssuer letsencrypt-prod absent — création…"
    kubectl apply -f - <<ISSUER
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: smatti.yann@gmail.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
      - http01:
          ingress:
            class: nginx
ISSUER
  else
    log "ClusterIssuer letsencrypt-prod déjà présent ✓"
  fi

  # ingress-nginx
  log "Vérification ingress-nginx…"
  if ! kubectl get namespace ingress-nginx >/dev/null 2>&1; then
    log "ingress-nginx absent — installation via Helm…"
    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx --force-update
    helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
      --namespace ingress-nginx --create-namespace \
      --wait --timeout 5m
  else
    log "ingress-nginx déjà installé ✓"
  fi

  log ""
  log "=== Prérequis cluster OK — démarrage du déploiement applicatif ==="
  log ""
fi

# ─── 1. Vérifications préalables ────────────────────────────────────────────
log "Vérification kubectl…"
kubectl cluster-info --request-timeout=5s >/dev/null 2>&1 || die "kubectl ne répond pas. Vérifiez votre contexte k8s."

log "Vérification AWS credentials…"
aws sts get-caller-identity --query Account --output text >/dev/null 2>&1 \
  || die "AWS session expirée. Lancez : aws sso login (ou aws login)"

# ─── 2. Namespace ───────────────────────────────────────────────────────────
log "Namespace $NAMESPACE…"
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
  || kubectl create namespace "$NAMESPACE"

# ─── 3. Refresh ECR credentials ─────────────────────────────────────────────
# Méthode A : ecr-pull-secret (pour les pods avec imagePullSecrets)
log "Refresh ecr-pull-secret dans $NAMESPACE…"
ECR_TOKEN=$(aws ecr get-login-password --region "$REGION")

kubectl create secret docker-registry ecr-pull-secret \
  --namespace="$NAMESPACE" \
  --docker-server="${REGISTRY%/platform}" \
  --docker-username=AWS \
  --docker-password="$ECR_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

# Méthode B : registries.yaml sur le nœud worker-ovh-094 (containerd)
log "Refresh containerd registries.yaml sur $WORKER_SSH…"
ssh -o StrictHostKeyChecking=no "$WORKER_SSH" "
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
" || log "Avertissement : SSH vers worker-ovh-094 a échoué — ecr-pull-secret sera utilisé à la place."
sleep 15

# ─── 4. ConfigMap ───────────────────────────────────────────────────────────
log "ConfigMap medvision-config…"
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: medvision-config
  namespace: $NAMESPACE
data:
  PYTHONUNBUFFERED: "1"
EOF

# ─── 4b. Secret AWS (pour dvc pull depuis S3 au démarrage du pod) ───────────
log "Secret medvision-aws-creds…"
kubectl create secret generic medvision-aws-creds \
  --namespace="$NAMESPACE" \
  --from-literal=AWS_ACCESS_KEY_ID="$(aws configure get aws_access_key_id)" \
  --from-literal=AWS_SECRET_ACCESS_KEY="$(aws configure get aws_secret_access_key)" \
  --from-literal=AWS_DEFAULT_REGION="$REGION" \
  --dry-run=client -o yaml | kubectl apply -f -

# ─── 5. PVCs (idempotents — ne recréent pas si existants) ───────────────────
log "PVCs…"
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: medvision-raw-data
  namespace: $NAMESPACE
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
  storageClassName: local-path
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: medvision-mlflow-store
  namespace: $NAMESPACE
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
  storageClassName: local-path
---
# Artefacts MLflow (artifacts trackés manuellement ou via mlflow.log_artifact)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: medvision-model-artifacts
  namespace: $NAMESPACE
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 5Gi
  storageClassName: local-path
EOF

# ─── 6. Deployments ─────────────────────────────────────────────────────────
log "Deployment medvision-api…"
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: medvision-api
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: medvision-api
  template:
    metadata:
      labels:
        app: medvision-api
    spec:
      nodeSelector:
        node-pool: apps-b
      imagePullSecrets:
        - name: ecr-pull-secret
      containers:
        - name: api
          image: ${REGISTRY}/medvision-ai:${TAG}
          imagePullPolicy: Always
          command: ["/entrypoint.sh", "uvicorn"]
          args: ["src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: medvision-config
            - secretRef:
                name: medvision-aws-creds
          # Les modèles sont récupérés depuis S3 via dvc pull (entrypoint.sh).
          # Le PVC medvision-raw-data peut aussi être peuplé manuellement ou via dvc pull.
          volumeMounts:
            - name: medvision-raw-data
              mountPath: /app/data/raw
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "1"
              memory: "2Gi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 20
            periodSeconds: 10
      volumes:
        - name: medvision-raw-data
          persistentVolumeClaim:
            claimName: medvision-raw-data
EOF

log "Deployment medvision-streamlit…"
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: medvision-streamlit
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: medvision-streamlit
  template:
    metadata:
      labels:
        app: medvision-streamlit
    spec:
      nodeSelector:
        node-pool: apps-b
      imagePullSecrets:
        - name: ecr-pull-secret
      containers:
        - name: streamlit
          image: ${REGISTRY}/medvision-ai:${TAG}
          imagePullPolicy: Always
          ports:
            - containerPort: 8501
          envFrom:
            - configMapRef:
                name: medvision-config
            - secretRef:
                name: medvision-aws-creds
          volumeMounts:
            - name: medvision-raw-data
              mountPath: /app/data/raw
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "500m"
              memory: "1Gi"
      volumes:
        - name: medvision-raw-data
          persistentVolumeClaim:
            claimName: medvision-raw-data
EOF

log "Deployment medvision-mlflow…"
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: medvision-mlflow
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: medvision-mlflow
  template:
    metadata:
      labels:
        app: medvision-mlflow
    spec:
      nodeSelector:
        node-pool: apps-a
      imagePullSecrets:
        - name: ecr-pull-secret
      containers:
        - name: mlflow
          image: ${REGISTRY}/medvision-ai:${TAG}
          imagePullPolicy: Always
          command: ["mlflow", "server"]
          args:
            - "--backend-store-uri=sqlite:////mlflow/mlflow.db"
            - "--default-artifact-root=/mlflow/artifacts"
            - "--host=0.0.0.0"
            - "--port=5000"
          ports:
            - containerPort: 5000
          volumeMounts:
            - name: medvision-mlflow-store
              mountPath: /mlflow
            - name: medvision-model-artifacts
              mountPath: /mlflow/artifacts
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
      volumes:
        - name: medvision-mlflow-store
          persistentVolumeClaim:
            claimName: medvision-mlflow-store
        - name: medvision-model-artifacts
          persistentVolumeClaim:
            claimName: medvision-model-artifacts
EOF

# ─── 7. Services ────────────────────────────────────────────────────────────
log "Services…"
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: medvision-api
  namespace: $NAMESPACE
spec:
  selector:
    app: medvision-api
  ports:
    - port: 8000
      targetPort: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: medvision-streamlit
  namespace: $NAMESPACE
spec:
  selector:
    app: medvision-streamlit
  ports:
    - port: 8501
      targetPort: 8501
---
apiVersion: v1
kind: Service
metadata:
  name: medvision-mlflow
  namespace: $NAMESPACE
spec:
  selector:
    app: medvision-mlflow
  ports:
    - port: 5000
      targetPort: 5000
EOF

# ─── 8. Ingress ─────────────────────────────────────────────────────────────
log "Ingress…"
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: medvision-ingress
  namespace: $NAMESPACE
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
spec:
  ingressClassName: nginx
  rules:
    - host: api.medvision.doctumconsilium.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: medvision-api
                port:
                  number: 8000
    - host: app.medvision.doctumconsilium.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: medvision-streamlit
                port:
                  number: 8501
  tls:
    - hosts:
        - api.medvision.doctumconsilium.com
        - app.medvision.doctumconsilium.com
      secretName: medvision-tls
EOF

# ─── 9. Attente des rollouts ────────────────────────────────────────────────
log "Attente rollout medvision-api…"
kubectl rollout status deployment/medvision-api -n "$NAMESPACE" --timeout=180s

log "Attente rollout medvision-streamlit…"
kubectl rollout status deployment/medvision-streamlit -n "$NAMESPACE" --timeout=180s

# ─── 10. Vérification finale ────────────────────────────────────────────────
log "État des pods :"
kubectl get pods -n "$NAMESPACE" -o wide

log "Vérification des modèles dans le pod API :"
if kubectl exec -n "$NAMESPACE" deploy/medvision-api -- ls /app/artifacts/models/ 2>/dev/null; then
  log "Modèles OK ✓"
else
  log "Avertissement : /app/artifacts/models absent ou vide — vérifiez l'image ECR."
fi

log ""
log "=== DÉPLOIEMENT TERMINÉ ==="
log "API    : https://api.medvision.doctumconsilium.com"
log "App    : https://app.medvision.doctumconsilium.com"
log "MLflow : accès interne uniquement (port-forward: kubectl port-forward -n medvision svc/medvision-mlflow 5000)"
log ""
if [ "$FULL_RECOVERY" = "true" ]; then
  log "=== RÉCUPÉRATION DES DONNÉES (si PVCs perdus) ==="
  log "Les PVCs sont vides après une réinstallation. Pour les repeupler :"
  log ""
  log "1) Données brutes (radiographies chest X-ray / brain MRI) :"
  log "   kubectl exec -n medvision deploy/medvision-api -- bash -c 'cd /app && python scripts/download_segmentation_chest.sh'"
  log "   OU copier depuis un backup local :"
  log "   kubectl cp data/raw/ medvision/<pod-name>:/app/data/raw/"
  log ""
  log "2) Modèles ML (depuis S3 via DVC) :"
  log "   Les pods téléchargent automatiquement les modèles au démarrage via dvc pull."
  log "   Si les modèles S3 sont absents : relancer l'entraînement local puis :"
  log "   bash scripts/migrate-models-to-s3.sh"
  log ""
  log "3) MLflow DB : pas de backup automatique — si perdu, relancer les runs d'entraînement."
fi
