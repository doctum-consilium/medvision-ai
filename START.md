# START — Reprise rapide MedVision AI sur k3s

Ce fichier répond à une seule question : **"j'ai un problème sur le cluster k3s, par où je commence ?"**

Pour l'onboarding complet (env local, entraînement, DVC), voir [ONBOARDING.md](ONBOARDING.md).

---

## Diagnostic rapide (toujours commencer ici)

```bash
kubectl get pods -n medvision          # état des pods
kubectl get pods -n medvision -o wide  # + nœud d'exécution
kubectl logs -n medvision deploy/medvision-streamlit --tail=50
kubectl logs -n medvision deploy/medvision-api --tail=50
kubectl describe pod -n medvision <nom-du-pod-en-erreur>
```

États attendus :
```
medvision-api-xxx       Running   # FastAPI + dvc pull au démarrage
medvision-streamlit-xxx Running   # Streamlit
medvision-mlflow-xxx    Running   # MLflow (nœud apps-a)
```

---

## Cas 1 — Pod crashé / CrashLoopBackOff

Le pod redémarre en boucle. La cause est dans les logs :

```bash
kubectl logs -n medvision deploy/medvision-api --previous
```

Causes fréquentes :
- `dvc pull` échoue → secret AWS manquant ou S3 inaccessible
- Modèle absent dans `artifacts/models/` → `migrate-models-to-s3.sh` à relancer
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

Après `docker build + push ECR` avec un nouveau tag (ex. `2026-06-16a`) :

```bash
bash scripts/redeploy-k3s.sh 2026-06-16a
```

Le script est idempotent — il re-sync les configs et attend que tous les pods soient Running.

---

## Cas 3 — Perte partielle (namespace supprimé, secrets perdus)

Redéployer sans toucher au cluster global :

```bash
bash scripts/redeploy-k3s.sh 2026-06-15f
```

Si les PVCs (données brutes) sont perdus, voir "Récupération des données" ci-dessous.

---

## Cas 4 — Perte totale du cluster k3s (réinstallation)

Après une réinstallation complète de k3s, le cluster est vide :
- Labels nœuds perdus
- cert-manager absent
- ingress-nginx absent
- Tous les namespaces et PVCs perdus

**Procédure complète** :

```bash
# 1. Vérifier kubectl pointe sur le nouveau cluster
kubectl cluster-info

# 2. Recréer tout (labels nœuds + cert-manager + ingress + déploiements)
bash scripts/redeploy-k3s.sh 2026-06-15f --full-recovery
```

Le flag `--full-recovery` fait :
1. Détecte automatiquement le master et le worker, ajoute les labels `node-pool=apps-a/b`.
2. Installe cert-manager + ClusterIssuer Let's Encrypt si absents.
3. Installe ingress-nginx si absent.
4. Recrée tous les namespaces, PVCs, secrets, ConfigMaps, Deployments, Services, Ingress.
5. Attend que tous les pods soient Running.
6. Affiche les étapes de récupération des données.

### Récupération des données après perte des PVCs

Les PVCs sont vides après réinstallation. Les données sont reconstruites depuis leurs sources :

**Données brutes (chest X-ray / brain MRI)** — re-télécharger depuis Kaggle :
```bash
# Depuis le nœud worker ou en local + kubectl cp
bash scripts/download_segmentation_brain.sh
bash scripts/run_prepare_segmentation_chest.sh
# Puis copier dans le pod :
kubectl cp data/raw/ medvision/$(kubectl get pod -n medvision -l app=medvision-api -o name | head -1 | cut -d/ -f2):/app/data/raw/
```

**Modèles ML** — depuis S3 via DVC (automatique au démarrage du pod) :
```bash
# Si le pod tourne mais n'a pas les modèles :
kubectl exec -n medvision deploy/medvision-api -- dvc pull artifacts/
# Si S3 est vide (modèles jamais pushés) → relancer l'entraînement local :
conda activate GPUMachineLearning
python src/training/train_classifier.py
bash scripts/migrate-models-to-s3.sh
```

**MLflow DB** — pas de backup automatique. Si perdu, relancer les runs d'entraînement.

---

## Vérification end-to-end après redéploiement

```bash
# Pods tous Running ?
kubectl get pods -n medvision

# API répond ?
curl -s https://api.medvision.doctumconsilium.com/health | python3 -m json.tool

# App accessible ?
open https://app.medvision.doctumconsilium.com   # ou navigateur

# Logs propres ?
kubectl logs -n medvision deploy/medvision-streamlit --tail=20
kubectl logs -n medvision deploy/medvision-api --tail=20
```

---

## Urls

| Service | URL |
|---|---|
| App Streamlit | https://app.medvision.doctumconsilium.com |
| API FastAPI | https://api.medvision.doctumconsilium.com |
| MLflow (port-forward) | `kubectl port-forward -n medvision svc/medvision-mlflow 5000` |

---

## Nœuds k3s attendus

| Label | Nœud | Workloads |
|---|---|---|
| `node-pool=apps-a` | master-ovh-xxx | MLflow, services légers |
| `node-pool=apps-b` | worker-ovh-094 (51.38.235.94) | API, Streamlit (inférence CPU) |

Re-labeler manuellement si nécessaire :
```bash
kubectl label node <NOM-MASTER> node-pool=apps-a --overwrite
kubectl label node <NOM-WORKER> node-pool=apps-b --overwrite
```
