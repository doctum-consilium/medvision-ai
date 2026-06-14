# ONBOARDING personnel — Inspiron 14 Plus (Ubuntu)

Notes de reprise propres à cette machine. Complète `ONBOARDING.md` (guide général).

---

## Machine

| Info | Valeur |
|---|---|
| Hostname | `yann-Inspiron-14-Plus-7430` |
| OS | Ubuntu 24.04 LTS |
| Disque principal | `/dev/nvme0n1p5` — 846 Go total (~78 Go libres après nettoyage 2026-06-15) |
| GPU | Intel intégré (pas de CUDA disponible localement → entraînement CPU ou cloud) |

---

## Environnement conda

```bash
conda activate GPUMachineLearning
```

- TensorFlow 2.16.1 / **Keras 3.3.3** (version critique — voir § Bugs connus)
- PyTorch installé (CPU)
- DVC avec support S3 (`dvc[s3]`)

```bash
# Vérifier que l'env est actif et les bonnes versions
python -c "import tensorflow as tf; import keras; print('TF:', tf.__version__, '/ Keras:', keras.__version__)"
# Attendu : TF: 2.16.1 / Keras: 3.3.3
```

---

## Chemins

```
Projet : ~/Documents/GithubPerso/medvision-ai/
Kaggle  : ~/.kaggle/kaggle.json       (chmod 600 obligatoire)
AWS     : ~/.aws/credentials           (profil default configuré)
```

---

## AWS CLI

```bash
# Vérifier que les credentials sont actifs
aws sts get-caller-identity

# Région : eu-west-3 (Paris)
# Registry ECR : 113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform/
```

---

## Commandes de reprise rapide

### Vérifier l'état du cluster K3s

```bash
kubectl get pods -n medvision
# Attendu : medvision-api, medvision-streamlit, medvision-mlflow → Running
curl https://api.medvision.doctumconsilium.com/health
# Attendu : {"status":"ok"}
```

### Rebuilder et déployer une nouvelle image ECR

```bash
conda activate GPUMachineLearning
cd ~/Documents/GithubPerso/medvision-ai

# 1. Rafraîchir le token ECR (expire toutes les 12h)
eval $(aws configure export-credentials --format env)
REGISTRY="113301685315.dkr.ecr.eu-west-3.amazonaws.com/platform"
aws ecr get-login-password --region eu-west-3 | docker login --username AWS --password-stdin $REGISTRY

# 2. Build + push (remplacer TAG par la date du jour + lettre)
TAG="2026-06-15f"   # exemple
docker build -f docker/Dockerfile -t $REGISTRY/medvision-ai:$TAG .
docker push $REGISTRY/medvision-ai:$TAG

# 3. Deploy sur K3s
kubectl set image deployment/medvision-api api=$REGISTRY/medvision-ai:$TAG -n medvision
kubectl set image deployment/medvision-streamlit streamlit=$REGISTRY/medvision-ai:$TAG -n medvision
kubectl set image deployment/medvision-mlflow mlflow=$REGISTRY/medvision-ai:$TAG -n medvision
kubectl rollout status deployment/medvision-api deployment/medvision-streamlit deployment/medvision-mlflow -n medvision
```

### Entraîner un modèle et pousser vers S3

```bash
conda activate GPUMachineLearning
cd ~/Documents/GithubPerso/medvision-ai

# 1. Télécharger les données si pas encore fait (~15 Go depuis Kaggle)
bash scripts/download_dataset.sh

# 2. Entraîner (DVC gère les dépendances)
dvc repro   # rejoue tout le pipeline

# 3. Pousser les artefacts vers S3
dvc push

# 4. Vérifier
dvc status  # doit afficher "Data and pipelines are up to date"

# 5. Rebuild ECR + deploy (voir commandes ci-dessus)
```

### Ajouter des images de démo dans le PVC K3s (sans rebuild)

```bash
# Copier un dossier local vers le PVC (persiste entre les restarts)
POD=$(kubectl get pod -n medvision -l app=medvision-streamlit -o jsonpath='{.items[0].metadata.name}')
kubectl cp data/raw/brain_tumor_mri medvision/$POD:/app/data/raw/brain_tumor_mri

# Vider le cache Streamlit (@st.cache_data)
kubectl rollout restart deployment/medvision-streamlit -n medvision
```

---

## Bugs connus et fixes appliqués (session 2026-06-15)

| Bug | Cause | Fix appliqué |
|---|---|---|
| `AttributeError: 'NoneType' object has no attribute 'pop'` au chargement modèle | Keras 3.12.x (pip sans pin) incompatible avec modèles sauvés en 3.3.3 | `keras==3.3.3` dans `requirements.txt` |
| `git: command not found` dans l'entrypoint | `python:3.10-slim` n'inclut pas git, DVC en a besoin | `apt-get install git` dans le Dockerfile |
| `ERROR: /app is not a git repository` (DVC) | Le conteneur n'a pas de `.git` | `git init -q` dans `entrypoint.sh` si absent |
| `ERROR: 'artifacts/models/' does not exist as a stage` (DVC) | `dvc pull <chemin>` n'est pas une syntaxe valide — DVC attend un nom de stage | `dvc pull train_chest_xray train_brain_mri train_brain_tumor_segmentation` |
| `NotADirectoryError: [Errno 20] Not a directory: '/mlflow/mlflow.db/.trash'` | `--backend-store-uri=/mlflow/mlflow.db` sans `sqlite://` → FileStore mode | `--backend-store-uri=sqlite:////mlflow/mlflow.db` |
| "No local image samples" pour brain_mri | `data/raw/brain_tumor_mri/` absent du PVC (seul chest_xray y était) | `kubectl cp` + rollout restart |
| "No local image samples" pour brain_tumor_seg | Même cause | Idem |

---

## État DVC (2026-06-15)

```bash
dvc status  # sur la machine locale
```

- Stages commitées : `train_chest_xray`, `train_brain_mri`, `train_brain_tumor_segmentation`
- S3 remote : `s3://platform-medvision-dvc-artifacts/models` (région eu-west-3)
- 11 fichiers en S3 (stubs — pas encore de vrais modèles entraînés)
- Stages **non** commitées : `download_*`, `prepare_*` — les datasets bruts ne sont pas en S3

---

## Nettoyage disque effectué (2026-06-15)

34 Go → 78 Go libres après :
- `docker builder prune -f` (34 Go de build cache)
- `conda clean --all -y` (~8.5 Go de packages cache)
- `pip cache purge` (~4 Go)
- `uv cache clean` (~600 Mo)
- Suppression des anciens tags ECR locaux (medvision-ai a→d)
