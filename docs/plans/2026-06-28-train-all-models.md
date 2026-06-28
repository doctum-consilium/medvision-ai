# Plan — Pipeline « entraîner tous les modèles d'un coup »

## Context
`dvc repro` (pipeline `dvc.yaml`) n'entraîne que la variante `optimized` de chaque tâche
+ 2 segmentations + 4 ONNX déclarés. Or le registry (`src/registry/model_registry.py`)
référence **17 modèles** : 6 backbones chest, 6 backbones brain_mri Keras, 3 brain_mri
PyTorch, 2 segmentations U-Net. On veut une commande unique qui entraîne **tous** les 17.

Contrainte : l'architecture impose **deux environnements** séparés (`.venv` TensorFlow,
`.venv-torch` PyTorch) — collision NCCL `libnccl.so.2` cu12/cu13. Une stage DVC unique ne
peut pas basculer d'env proprement, et un `foreach` DVC entrerait en collision d'outputs
avec le `dvc.yaml` existant (qui sert la prod via `dvc pull convert_to_onnx`). On choisit
donc un **script orchestrateur** (`scripts/train_all.sh`) plutôt qu'une 2ᵉ `dvc.yaml`.

## Architecture
Script séquentiel, résilient (un modèle qui échoue n'arrête pas les autres), idempotent
(`--skip-existing`). Trois phases, chacune dans le bon environnement :

1. **TensorFlow (`.venv` + `gpu_env.sh`)** : 6 chest (`src.training.train`), 6 brain_mri
   Keras (délégué à `run_training_brain_mri_all.sh`), 2 segmentations.
2. **PyTorch (`.venv-torch`)** : 3 modèles (`src.training.train_brain_mri_torch`).
3. **ONNX** : `convert_to_onnx.py` lancé d'abord dans `.venv` (keras ; les `.pt` échouent →
   toléré `|| true`), puis dans `.venv-torch` (les `.pt` ; les `.onnx` keras déjà présents
   sont skippés → exit 0). Réunion = tous les `.onnx`.

## Surface des changements
- **Nouveau** `scripts/train_all.sh` (orchestrateur, options `--skip-existing`, `--no-torch`,
  `--no-onnx`, `--no-download`, `-h`).
- **Doc** : note dans `ONBOARDING.md` (section entraînement) + entrée `ROADMAP.md`.
- Aucune modification de `dvc.yaml`, des trainers, ou du flux prod existant.

## Vérification
- `bash -n scripts/train_all.sh` (syntaxe).
- `bash scripts/train_all.sh -h` (aide).
- Exécution réelle laissée à l'utilisateur (entraînement GPU multi-heures) — le script
  log chaque modèle (OK/SKIP/FAIL) et un récap final (#keras/#pt/#onnx produits).

## Hors scope (étape suivante, déjà signalée)
- **Déploiement S3/k3s des 13 modèles non-`optimized`** : `dvc.yaml` ne déclare que 4 ONNX
  en sortie de `convert_to_onnx`, donc seuls ceux-là sont poussés/servis. Étendre le câblage
  (déclarer les 17 ONNX, adapter `entrypoint.sh`/`redeploy-k3s.sh`) fera l'objet d'un plan
  dédié si validé.

## Rollback
- `git rm scripts/train_all.sh docs/plans/2026-06-28-train-all-models.md` + revert des notes
  doc. Aucun effet sur l'existant (ajout pur).
