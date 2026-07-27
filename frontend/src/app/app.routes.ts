import { Routes } from '@angular/router';

/**
 * Les écrans du produit.
 *
 * Chargement paresseux (`loadComponent`) : l'accueil s'affiche sans attendre
 * le code des autres écrans — et Chart.js, qui ne sert qu'à eux, ne pèse pas
 * sur le premier affichage.
 *
 * Les écrans « studio » et « comparaison » s'ajouteront ici au fur et à
 * mesure ; la navigation (app.component) ne propose que ce qui existe.
 */
export const routes: Routes = [
  {
    path: '',
    title: 'MedVision AI — Accueil',
    loadComponent: () =>
      import('./pages/accueil/accueil.component').then((m) => m.AccueilComponent),
  },
  {
    path: 'studio',
    title: 'MedVision AI — Analyser une image',
    loadComponent: () =>
      import('./pages/studio/studio.component').then((m) => m.StudioComponent),
  },
  { path: '**', redirectTo: '' },
];
