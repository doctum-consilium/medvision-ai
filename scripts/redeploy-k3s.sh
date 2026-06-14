#!/usr/bin/env bash
# Purpose  : Redéploie medvision-ai sur le cluster k3s OVH depuis zéro (disaster recovery).
# Usage    : ./scripts/redeploy-k3s.sh [TAG]
# Arguments: TAG — tag ECR de l'image (défaut : 2026-04-16)
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
# PVCs conservés   : medvision-raw-data (radiographies), medvision-mlflow-store (MLflow DB)
#
# IMPORTANT — modèles ML :
#   Les modèles .keras sont BAKED dans l'image ECR à la compilation (artifacts/ non exclu du
#   .dockerignore). Le PVC medvision-model-artifacts est VIDE et NON monté sur api/streamlit.
#   Pour mettre à jour les modèles : reconstruire l'image (make train → docker build → push ECR).
set -euo pipefail

REGISTRY="113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform"
REGION="eu-west-3"
TAG="${1:-2026-04-16}"
NAMESPACE="medvision"
WORKER_SSH="yannsmatti@51.38.235.94"

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "[ERREUR] $*" >&2; exit 1; }

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
EOF
# medvision-model-artifacts PVC laissé en place s'il existe (vide mais inoffensif)

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
