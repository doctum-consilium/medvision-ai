# Plans — Index

| Fichier | Sujet | État |
|---|---|---|
| [2026-06-15-medvision-fix-registry-data.md](2026-06-15-medvision-fix-registry-data.md) | Fix registry (modèles orphelins) + génération samples | Livré 2026-06-15 |
| [2026-06-15-medvision-pipeline-dvc-ecr.md](2026-06-15-medvision-pipeline-dvc-ecr.md) | Architecture DVC+S3 + entrypoint + guide entraînement local | Livré 2026-06-15 |
| [2026-07-18-medvision-pr10-refonte-angular.md](2026-07-18-medvision-pr10-refonte-angular.md) | PR #10 débloquée + 17 modèles en prod + refonte Angular | Livré en partie 2026-07-18 (front au socle) |
| [2026-07-18-handoff-medvision.md](2026-07-18-handoff-medvision.md) | **Point de reprise** : état prod, causes racines, dettes, marche à suivre | À suivre |
| [2026-07-27-medvision-front-angular-b1.md](2026-07-27-medvision-front-angular-b1.md) | Reprise du chantier B1 : front Angular complet (accueil, studio, comparaison) jusqu'au déploiement `ui.medvision` | En cours 2026-07-27 |

## Résumé de ce qui a été livré (2026-06-15)

Session complète de mise en place de la chaîne DVC+S3+ECR+K3s :
- Modèles déplacés hors image Docker (DVC pull au démarrage)
- Entrypoint corrigé (git, syntaxe dvc pull, gestion erreurs)
- MLflow fix (sqlite://)
- Keras 3.3.3 pinné
- Images dataset copiées dans les PVCs
- Documentation complète (ONBOARDING.md, ONBOARDING_perso_inspiron_ubuntu.md, SESSION-STATE.md, LOCAL_TRAINING_GUIDE.md)
- Handoff dans CLAUDE.md, GEMINI.md, copilot-instructions.md
