# Plan maître — MedVision AI : portabilité, câblage prod des 17 modèles, migration SPA

> À dupliquer dans `docs/plans/2026-06-28-prod-all-models-et-spa.md` à la sortie du mode plan
> (règle CLAUDE.md « Plan files »). Suite de `docs/plans/2026-06-28-train-all-models.md`.

## Context
Session partie d'un `dvc pull` cassé (`~/.aws/config` corrompu) qui a révélé une chaîne de
problèmes de **reproductibilité d'un poste à l'autre** (docs liées à une machine, `src/models`
absent du repo, deux frameworks GPU incompatibles dans un seul env, modèles non câblés en prod).
Objectif global : qu'un clone neuf sur Ubuntu/WSL2 puisse installer, **entraîner les 17 modèles**
du registry, les **pousser sur S3 + k3s**, et préparer le **remplacement de Streamlit par une SPA**.

## Déjà livré cette session (contexte, non à refaire)
- Réparation `~/.aws/config` + restauration `~/.kaggle/kaggle.json`.
- Garde-fous permissions dans `~/.claude/settings.json` (allow `Bash` + deny/ask destructeurs).
- **Architecture 2 environnements** (collision NCCL cu12/cu13) : `requirements-train.txt` (TF,
  `.venv`) + `requirements-torch.txt` (torch 2.6.0+cu124, `.venv-torch`) — validés (GPU OK).
- `scripts/install_prereqs.sh` (Ubuntu & WSL2, idempotent), `scripts/gpu_env.sh` (fix libs CUDA
  TF 2.16), `scripts/train_all.sh` (entraîne les 17, gère les 2 envs).
- `src/models/backbones.py` : clé `optimized` (alias EfficientNetV2B0) — pull de `origin/main`.
- onnx épinglé `<1.18` (conflit ml_dtypes/TF). Docs dé-machinifiées + ROADMAP + plans.

---

## Chantier A (maintenant) — Les 17 modèles en prod via pipeline DVC `foreach`

### A.1 Problème
La prod (`docker/entrypoint.sh : dvc pull convert_to_onnx`) ne récupère que les **4 ONNX**
déclarés par cette stage. Le registry (`src/registry/model_registry.py`) en référence **17**.
Décision : tout câbler dans DVC (reproductible) — `dvc repro` entraîne+convertit+versionne les 17.

### A.2 Architecture
**Wrappers d'env (déjà créés, conserver, `chmod +x`)** — évitent le YAML à quotes imbriquées :
- `scripts/_dvc_tf.sh <cmd>` → active `.venv` + `gpu_env.sh`, `exec <cmd>`.
- `scripts/_dvc_torch.sh <args>` → `exec env -u LD_LIBRARY_PATH .venv-torch/bin/python <args>`.
- `scripts/_dvc_convert.sh` → passe 1 keras (TF, `|| true`), passe 2 `.pt` (torch).

**`dvc.yaml`** : remplacer `train_chest_xray` et `train_brain_mri` par des stages `foreach`
(6 backbones chacun), ajouter `train_brain_mri_torch` (foreach 3), étendre `convert_to_onnx`
(17 deps / 17 outs). `download_*`/`prepare_*`/`train_*_segmentation` : préfixer leur `cmd` par
`bash scripts/_dvc_tf.sh` (robustesse multi-shell), sinon inchangées.

Noms de sortie **vérifiés dans le code** (sinon `dvc repro` échoue « output not produced ») :
- chest `train.py` : `{item}_model.keras` + `{item}_{classification_report.txt|confusion_matrix.png|history.json|metrics.json}`.
- brain `train_brain_mri.py` : `brain_mri_{item}.keras` + `brain_mri_{item}_{…}`.
- torch `train_brain_mri_torch.py` : `brain_mri_{item}.pt`, `brain_mri_{item}_metrics.json`, `brain_mri_{item}_history.json`.

**Incohérences pré-existantes corrigées :** (1) `train_brain_mri` déclarait `brain_mri_metrics.json`
≠ sortie réelle `brain_mri_optimized_metrics.json` → `foreach` utilise `brain_mri_${item}_metrics.json` ;
(2) `convert_to_onnx` dépendait de `baseline_model.keras` sans stage le produisant → produit par le foreach chest.

Stages cibles (extrait) :
```yaml
  train_chest_xray:
    foreach: [baseline, optimized, densenet121, efficientnetv2b0, convnexttiny, resnet50v2]
    do:
      cmd: bash scripts/_dvc_tf.sh python -m src.training.train --config configs/config.yaml --model ${item} --epochs ${chest_xray.epochs}
      deps: [src/training/train.py, src/utils/dataset.py, src/evaluation/metrics.py, configs/config.yaml, data/raw/chest_xray]
      params: [chest_xray]
      outs: [artifacts/models/${item}_model.keras, artifacts/reports/${item}_classification_report.txt,
             artifacts/reports/${item}_confusion_matrix.png, artifacts/reports/${item}_history.json]
      metrics: [{artifacts/reports/${item}_metrics.json: {cache: false}}]
  train_brain_mri:        # idem, src.training.train_brain_mri, outs brain_mri_${item}.*
  train_brain_mri_torch:  # foreach [densenet121_torch, resnet50_torch, swin_v2_s_torch]
      cmd: bash scripts/_dvc_torch.sh -m src.training.train_brain_mri_torch --config configs/brain_tumor_mri.yaml --model ${item} --epochs ${brain_mri.epochs}
      outs: [artifacts/models/brain_mri_${item}.pt, artifacts/reports/brain_mri_${item}_history.json]
  convert_to_onnx:
      cmd: bash scripts/_dvc_convert.sh
      deps: [scripts/convert_to_onnx.py, <les 17 .keras/.pt>]
      outs: [<les 17 .onnx de mêmes radicaux>]
```
(Liste exhaustive des 17 deps/outs : voir énumération registry — 6 chest + 6 brain keras + 3 `.pt` + 2 `*_unet`.)

### A.3 Surface
`dvc.yaml` (réécriture stages train + convert) ; `scripts/_dvc_*.sh` (déjà créés) ;
`docker/entrypoint.sh` (commentaire ; `dvc pull convert_to_onnx` inchangé → pull 17) ;
`dvc.lock` régénéré par `dvc repro` (jamais édité main) ; **aucun** changement registry.

### A.4 Vérification
1. Statique : `dvc stage list` + `dvc dag` parsent (valide `${item}` + params, 17 stages générés) ;
   `bash -n` + shellcheck des wrappers ; sanity GPU TF & torch via les wrappers.
2. Bout-en-bout (utilisateur, GPU multi-heures) : `dvc repro` → `ls artifacts/models/*.onnx | wc -l`
   = 17 ; `dvc push` ; `bash scripts/redeploy-k3s.sh <TAG>` ; pod pull 17 ; `GET /registry` liste 17.

---

## ⏸ PAUSE — entraînement des 17 modèles par l'utilisateur (entre A et B)

**Jalon obligatoire avant de démarrer le Chantier B.** Une fois le Chantier A implémenté et
validé statiquement (`dvc dag` OK), **je m'arrête** et te rends la main pour l'entraînement
GPU long (plusieurs heures), que tu lances toi-même :

```bash
source .venv/bin/activate && source scripts/gpu_env.sh
dvc repro                  # entraîne les 17 + convertit en ONNX (régénère dvc.lock)
dvc push                   # → S3
bash scripts/redeploy-k3s.sh "$(date +%Y-%m-%d)a"   # déploie en prod (pods pull les 17)
```

Critères de reprise (avant Chantier B) : `ls artifacts/models/*.onnx | wc -l` = 17, `dvc push`
réussi, `GET /registry` en prod liste les 17. Je ne commence le Chantier B qu'après ton feu vert.

---

## Chantier B (suivant) — Migration du front Streamlit → SPA (POC React + Angular)

### B.1 Décisions actées
- **POC comparatif** : même écran `/predict` (upload image → appel API → classe + confiance +
  overlay segmentation) implémenté en **React (Vite + TS)** ET **Angular (TS)**, pour trancher
  sur DX, taille de bundle, ergonomie, maintenabilité — AVANT de s'engager.
- **Streamlit remplacé à terme** : la SPA devient le front public ; Streamlit gardé pendant la
  transition (parité fonctionnelle) puis retiré.

### B.2 Architecture cible
- SPA = client statique (build) consommant l'API FastAPI existante (`src/api/main.py` :
  `/health`, `/registry`, `/predict?model_name=…`, `/compare`). Aucun rendu serveur requis.
- Nouveau dossier `frontend/` (monorepo) : `frontend/poc-react/`, `frontend/poc-angular/`,
  puis `frontend/app/` (gagnant). Client API typé généré depuis l'OpenAPI FastAPI (`/openapi.json`).
- Prod k3s : nouvelle image (nginx servant le build statique) poussée sur ECR, déployée comme
  service `medvision-web` dans le namespace `medvision`, exposée via ingress
  `app.medvision.doctumconsilium.com` (manifests dans `k3s-fromOVHVps/`).

### B.3 Phases
1. **B-POC** : scaffolder les 2 POC sur l'écran `/predict` (même appel API, même UX cible).
   Critère de choix documenté → décision React **ou** Angular.
2. **Backend prep** : activer **CORS** FastAPI pour l'origine SPA ; figer le contrat OpenAPI ;
   vérifier les endpoints requis (`/registry` pour lister les 17 modèles, `/compare`, overlays).
3. **B-Parité** : développer le front gagnant à parité Streamlit (navigation des 17 modèles par
   tâche, prédiction, comparaison, affichage masque de segmentation).
4. **B-Déploiement** : Dockerfile nginx + manifests k3s (`medvision-web` + ingress) ; cohabitation
   avec Streamlit (sous-domaines distincts).
5. **B-Cutover** : bascule de l'ingress public vers la SPA ; retrait de Streamlit une fois la
   parité confirmée.

### B.4 Surface (prévisionnelle)
- **Nouveau** `frontend/` (POC ×2 puis app). **Nouveau** Dockerfile front + manifests k3s
  (`k3s-fromOVHVps/rendered-k3s-manifests/` + template). **Modif** `src/api/main.py` (CORS).
  Streamlit (`src/streamlit/app.py`) inchangé jusqu'au cutover.

### B.5 Vérification
- POC : les 2 appellent `/predict` et affichent un résultat réel ; tableau comparatif → décision.
- Parité : checklist fonctionnelle Streamlit ↔ SPA cochée.
- Prod : `app.medvision…/` répond, `/predict` fonctionne contre l'API, ingress + TLS OK.

### B.6 Hors scope (chantier B)
- Auth/comptes utilisateurs, i18n, refonte design system (à cadrer séparément si besoin).

---

## Rollback
- Chantier A : `git checkout -- dvc.yaml docker/entrypoint.sh` ; `git rm scripts/_dvc_*.sh` ;
  restaurer `dvc.lock` depuis `origin/main`. Artefacts S3 déjà poussés conservés (non destructif).
- Chantier B : purement additif (dossier `frontend/`, nouveau service k3s) tant que le cutover
  d'ingress n'est pas fait ; revert = supprimer le service/ingress `medvision-web`.

## Ordre d'exécution conseillé
Chantier A (câblage DVC, court) → **⏸ PAUSE : tu entraînes les 17 (`dvc repro` multi-heures) +
`dvc push` + redeploy** → reprise sur ton feu vert → Chantier B (B-POC → B-Parité → B-Déploiement → B-Cutover).
