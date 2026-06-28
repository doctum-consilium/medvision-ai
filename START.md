# START — Reprise rapide MedVision AI sur k3s

Ce fichier répond à une seule question : **"j'ai un problème sur le cluster k3s, par où je commence ?"**

Pour l'onboarding complet (env local, entraînement, DVC), voir [ONBOARDING.md](ONBOARDING.md).

---

## Diagnostic rapide (toujours commencer ici)

```bash
kubectl get pods -n medvision          # état des pods medvision
kubectl get pods -A                    # état de TOUS les pods du cluster
kubectl get pods -n medvision -o wide  # + nœud d'exécution
kubectl logs -n medvision deploy/medvision-streamlit --tail=50
kubectl logs -n medvision deploy/medvision-api --tail=50
kubectl describe pod -n medvision <nom-du-pod-en-erreur>
```

États attendus pour medvision :
```
medvision-api-xxx        Running   # FastAPI + dvc pull au démarrage
medvision-streamlit-xxx  Running   # Streamlit
medvision-mlflow-xxx     Running   # MLflow (nœud apps-a)
```

---

## Cas 1 — Pod crashé / CrashLoopBackOff

```bash
kubectl logs -n medvision deploy/medvision-api --previous
```

Causes fréquentes :
- `dvc pull` échoue → secret AWS manquant ou S3 inaccessible
- Modèle absent dans `artifacts/models/` → relancer `migrate-models-to-s3.sh`
- Image ECR non trouvée (`ImagePullBackOff`) → token ECR expiré (TTL 12 h)

### Refresh token ECR (ImagePullBackOff)

```bash
ECR_TOKEN=$(aws ecr get-login-password --region eu-west-3)
kubectl create secret docker-registry ecr-pull-secret \
  --namespace=medvision \
  --docker-server=113301685315.dkr.ecr.eu-west-3.amazonaws.com \
  --docker-username=AWS \
  --docker-password="$ECR_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment -n medvision
```

---

## Cas 2 — Redéploiement d'une nouvelle image

```bash
bash scripts/redeploy-k3s.sh 2026-06-15f
```

Le script est idempotent : refresh ECR, apply du manifest `k3s-fromOVHVps/rendered-k3s-manifests/30-medvision.yaml`, `kubectl set image`, attente rollout.

---

## Cas 3 — Plusieurs services en vrac (pas seulement medvision)

Les manifests de TOUS les services sont dans le repo `k3s-fromOVHVps`.
Re-appliquer un ou plusieurs services :

```bash
cd ~/Documents/GithubPerso/k3s-fromOVHVps/rendered-k3s-manifests

kubectl apply -f 30-medvision.yaml           # medvision-ai
kubectl apply -f 60-doctum-trading-platform.yaml  # bot trading
kubectl apply -f 87-trade-analytics.yaml     # trade analytics
kubectl apply -f 40-litellm-gateway.yaml     # LLM gateway
kubectl apply -f 20-tradejournal.yaml        # trade journal
# etc. — voir la liste complète ci-dessous
```

Liste complète des manifests (ordre d'application recommandé) :
```
00-namespaces.yaml
05-doctumconsilium-website.yaml
06-streetfighter-enhanced.yaml
10-market-insight.yaml
20-tradejournal.yaml
30-medvision.yaml
40-litellm-gateway.yaml
50-market-screener.yaml
60-doctum-trading-platform.yaml
61-rl-retrain.yaml
65-keycloak-postgres.yaml / 70-keycloak.yaml
80-products.yaml
85-backtest-react.yaml / 87-trade-analytics.yaml
90-monitoring.yaml
95-strategy-maker.yaml / 95-tradeify-crypto.yaml
```

Ou tout re-appliquer d'un coup :
```bash
cd ~/Documents/GithubPerso/k3s-fromOVHVps/rendered-k3s-manifests
for f in $(ls *.yaml | sort); do
  echo "--- $f ---"
  kubectl apply -f "$f" || echo "[SKIP] $f a échoué (secret CHANGE_ME ?)"
done
```

---

## Cas 4 — Disaster total : cluster k3s perdu ou réinstallé

Le cluster est mort (VPS recréé, k3s réinstallé, tout effacé).

### Étape 1 — Depuis le workspace local (VS Code + repos git)

```bash
# S'assurer que les repos sont à jour
cd ~/Documents/GithubPerso/k3s-fromOVHVps && git pull
cd ~/Documents/GithubPerso/medvision-ai && git pull
# (idem pour doctum-trading-platform, tradejournal, etc.)
```

### Étape 2 — Bootstrap du cluster k3s (control plane + workers)

Le script `deploy_cluster.sh` orchestre l'install complète depuis zéro :

```bash
cd ~/Documents/GithubPerso/k3s-fromOVHVps

# 1. Copier et remplir le fichier de config (IPs VPS, domaine, ECR...)
cp scripts/deploy_cluster.env.example scripts/deploy_cluster.env
# → Éditer deploy_cluster.env avec les vraies IPs et variables

# 2. Lancer le bootstrap complet
bash scripts/deploy_cluster.sh scripts/deploy_cluster.env
```

Ce script :
- Installe k3s sur le control-plane
- Joint les workers
- Refresh les credentials ECR
- Applique tous les manifests `rendered-k3s-manifests/*.yaml`
- Configure le DNS OVH (optionnel)

### Étape 3 — Re-appliquer medvision spécifiquement

```bash
cd ~/Documents/GithubPerso/medvision-ai
bash scripts/redeploy-k3s.sh 2026-06-15f --full-recovery
```

Le flag `--full-recovery` :
1. Détecte et relabele les nœuds (`node-pool=apps-a/b`)
2. Installe cert-manager + ClusterIssuer Let's Encrypt si absents
3. Installe ingress-nginx si absent
4. Apply le manifest + met à jour le tag image
5. Affiche les étapes de récupération des données

### Étape 4 — Récupération des données (si PVCs vides)

**Données brutes (radiographies)** :
```bash
bash scripts/download_segmentation_brain.sh
kubectl cp data/raw/ medvision/<pod-api>:/app/data/raw/
```

**Modèles ML** (téléchargés automatiquement depuis S3 au démarrage via `dvc pull`) :
```bash
# Si le pod tourne mais n'a pas les modèles :
kubectl exec -n medvision deploy/medvision-api -- dvc pull artifacts/
# Si S3 est vide (jamais pushé) → entraîner localement :
source .venv/bin/activate        # ou : conda activate <votre-env>  (deps : requirements-train.txt)
dvc repro                        # pipeline complet reproductible
bash scripts/migrate-models-to-s3.sh
```

---

## Nœuds k3s attendus

| Label | Nœud | Workloads |
|---|---|---|
| `node-pool=apps-a` | master-ovh-xxx | MLflow, services légers |
| `node-pool=apps-b` | worker-ovh-094 (51.38.235.94) | API, Streamlit (inférence CPU) |

Re-labeler manuellement :
```bash
kubectl label node <NOM-MASTER> node-pool=apps-a --overwrite
kubectl label node <NOM-WORKER> node-pool=apps-b --overwrite
```

---

## Vérification end-to-end

```bash
kubectl get pods -A                     # tous les pods du cluster
kubectl get pods -n medvision           # medvision spécifiquement
curl -s https://api.medvision.doctumconsilium.com/health
```

---

## URLs

| Service | URL |
|---|---|
| App Streamlit | https://app.medvision.doctumconsilium.com |
| API FastAPI | https://api.medvision.doctumconsilium.com |
| MLflow | `kubectl port-forward -n medvision svc/medvision-mlflow 5000` |
