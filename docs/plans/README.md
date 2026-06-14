# Plans — Index

| Fichier | Sujet | État |
|---|---|---|
| [2026-06-15-medvision-fix-registry-data.md](2026-06-15-medvision-fix-registry-data.md) | Fix registry (modèles orphelins) + génération samples | Livré 2026-06-15 |
| [2026-06-15-medvision-pipeline-dvc-ecr.md](2026-06-15-medvision-pipeline-dvc-ecr.md) | Architecture DVC+S3 + entrypoint + guide entraînement local | Livré 2026-06-15 |

## Résumé de ce qui a été livré (2026-06-15)

Session complète de mise en place de la chaîne DVC+S3+ECR+K3s :
- Modèles déplacés hors image Docker (DVC pull au démarrage)
- Entrypoint corrigé (git, syntaxe dvc pull, gestion erreurs)
- MLflow fix (sqlite://)
- Keras 3.3.3 pinné
- Images dataset copiées dans les PVCs
- Documentation complète (ONBOARDING.md, ONBOARDING_perso_inspiron_ubuntu.md, SESSION-STATE.md, LOCAL_TRAINING_GUIDE.md)
- Handoff dans CLAUDE.md, GEMINI.md, copilot-instructions.md
