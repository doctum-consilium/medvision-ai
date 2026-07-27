# MedVision AI — interface web

Interface publique d'analyse d'images médicales. Elle consomme l'API v2 de
`src/api/` (préfixe `/api`) et coexiste avec l'interface Streamlit historique :
Streamlit reste sur `app.medvision.doctumconsilium.com`, celle-ci vise
`ui.medvision.doctumconsilium.com`.

## Démarrer en développement

```bash
npm ci                      # installe EXACTEMENT ce que dit package-lock.json
npm start                   # http://localhost:4200
```

Le serveur de développement proxifie `/api` vers l'API de production
(`proxy.conf.json`). Pour viser une API locale, changez la cible de ce fichier
en `http://localhost:8000` — le code de l'application, lui, ne connaît jamais
l'hôte de l'API : il appelle toujours `/api`.

## Vérifier avant de pousser

```bash
npm run build                                            # compilation stricte + budgets
CHROME_BIN=$(which google-chrome) \
  npx ng test --watch=false --browsers=ChromeHeadless    # tests unitaires
```

Ces deux commandes sont exactement celles du job GitHub `CI Front`
(`.github/workflows/ci-front.yml`), et `scripts/ci_local.sh` les rejoue depuis
la racine du dépôt.

## Comment c'est organisé

| Dossier | Rôle |
|---|---|
| `src/app/core/api/` | Clients HTTP typés + `api.types.ts`, **miroir des schémas FastAPI** |
| `src/app/core/realtime/` | Flux temps réel (SSE) : reconnexion et resynchronisation |
| `src/app/core/state/` | `RegistreStore` — la source de vérité partagée par tous les écrans |
| `src/app/core/theme/` | Thème clair/sombre par l'attribut `data-theme` |
| `src/app/core/i18n/` | Tous les libellés français, en un seul endroit |
| `src/app/shared/` | Composants réutilisables (graphes, superpositions) |
| `src/app/pages/` | Un dossier par écran |
| `src/styles.css` | Tokens du design system **et** pont vers Tailwind |

## En production

L'interface est en ligne sur **<https://ui.medvision.doctumconsilium.com>**
(image `medvision-web:2026-07-27`). L'interface Streamlit historique reste en
service sur `app.medvision.doctumconsilium.com`.

## Deux règles à ne pas casser

1. **Les types suivent l'API.** Toute évolution de schéma côté FastAPI se
   répercute dans `core/api/api.types.ts`. La compilation stricte est ce qui
   attrape l'oubli — c'est voulu.
2. **La segmentation ne pose aucun diagnostic.** Sur un problème dont le
   `task_type` vaut `segmentation`, l'interface n'affiche ni classe prédite,
   ni confiance, ni probabilités : seulement les zones délimitées. La tête de
   classification de ces modèles annonçait « NORMAL » avec une confiance de
   1,000 sur des pneumonies manifestes — c'est une décision produit, pas un
   détail d'affichage.
