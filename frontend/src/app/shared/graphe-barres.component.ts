/**
 * Graphe en barres réutilisable (Chart.js).
 *
 * Sert deux besoins : les probabilités par catégorie dans le studio, et la
 * comparaison des métriques entre modèles. Un seul composant pour les deux
 * garantit que les deux écrans se lisent de la même façon.
 *
 * POURQUOI Chart.js appelé directement plutôt qu'un habillage Angular : on
 * n'enregistre que les quatre éléments dont on se sert, ce qui laisse le
 * reste de la bibliothèque hors du bundle ; et il n'y a pas de dépendance
 * supplémentaire à réaligner à chaque montée de version majeure d'Angular.
 *
 * POURQUOI relire les couleurs à chaque dessin : un canvas n'est qu'une
 * image, il ne « suit » pas les variables CSS. Sans cela, basculer en thème
 * sombre laisserait un graphe aux couleurs du thème clair.
 */
import {
  Component,
  DestroyRef,
  ElementRef,
  effect,
  inject,
  input,
  viewChild,
} from '@angular/core';
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Legend,
  LinearScale,
  Tooltip,
  type ChartDataset,
} from 'chart.js';

import { ThemeService } from '../core/theme/theme.service';

// Enregistrement explicite et minimal : tout ce qui n'est pas listé ici
// (camemberts, courbes, échelles temporelles, animations avancées…) reste
// hors du bundle envoyé au navigateur.
Chart.register(BarController, BarElement, CategoryScale, LinearScale, Legend, Tooltip);

/** Une série de valeurs, alignée sur le tableau `etiquettes`. */
export interface SerieBarres {
  nom: string;
  valeurs: number[];
}

@Component({
  selector: 'app-graphe-barres',
  standalone: true,
  template: `<canvas #toile [attr.aria-label]="descriptionAccessible()" role="img"></canvas>`,
  styles: [':host { display: block; position: relative; width: 100%; }'],
})
export class GrapheBarresComponent {
  private readonly theme = inject(ThemeService);
  private readonly toile = viewChild.required<ElementRef<HTMLCanvasElement>>('toile');

  /** Étiquettes de l'axe horizontal (catégories ou noms de modèles). */
  readonly etiquettes = input.required<string[]>();

  /** Séries à tracer. Une seule série = barres simples ; plusieurs = groupées. */
  readonly series = input.required<SerieBarres[]>();

  /** Borne haute de l'axe vertical. `null` pour laisser Chart.js décider. */
  readonly maximum = input<number | null>(1);

  /** Barres horizontales — plus lisibles quand les étiquettes sont longues. */
  readonly horizontal = input(false);

  /** Résumé lu par les lecteurs d'écran, qui ne voient pas le canvas. */
  readonly descriptionAccessible = input('Graphique en barres');

  private graphe: Chart | null = null;

  constructor() {
    // Un seul effet couvre tout : premier rendu, changement de données ET
    // bascule de thème (le signal `theme` est lu, donc l'effet en dépend).
    effect(() => {
      const etiquettes = this.etiquettes();
      const series = this.series();
      this.theme.theme();
      this.dessiner(etiquettes, series);
    });

    // Chart.js pose des écouteurs de redimensionnement sur le canvas : sans
    // destruction explicite, ils survivent au composant et fuient.
    inject(DestroyRef).onDestroy(() => this.graphe?.destroy());
  }

  /** (Re)construit le graphe avec les couleurs du thème courant. */
  private dessiner(etiquettes: string[], series: SerieBarres[]): void {
    const contexte = this.toile().nativeElement;
    const encre = this.theme.couleur('ink-muted');
    const trait = this.theme.couleur('line');
    const palette = [
      this.theme.couleur('accent'),
      this.theme.couleur('accent-2'),
      this.theme.couleur('warn'),
      this.theme.couleur('danger'),
    ];

    const datasets: ChartDataset<'bar', number[]>[] = series.map((serie, index) => ({
      label: serie.nom,
      data: serie.valeurs,
      backgroundColor: palette[index % palette.length],
      borderRadius: 5,
      borderSkipped: false,
      maxBarThickness: 42,
    }));

    // Détruire puis recréer plutôt que muter : le code de mise à jour
    // incrémentale de Chart.js est une source classique de graphes
    // fantômes quand le nombre de séries change. Ici les jeux de données
    // sont minuscules, la reconstruction est imperceptible.
    this.graphe?.destroy();
    this.graphe = new Chart(contexte, {
      type: 'bar',
      data: { labels: etiquettes, datasets },
      options: {
        indexAxis: this.horizontal() ? 'y' : 'x',
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 240 },
        plugins: {
          legend: { display: series.length > 1 },
          tooltip: { displayColors: series.length > 1 },
        },
        scales: {
          x: {
            grid: { display: this.horizontal(), color: trait },
            ticks: { color: encre },
            max: this.horizontal() ? (this.maximum() ?? undefined) : undefined,
          },
          y: {
            grid: { display: !this.horizontal(), color: trait },
            ticks: { color: encre },
            max: this.horizontal() ? undefined : (this.maximum() ?? undefined),
            beginAtZero: true,
          },
        },
      },
    });
  }
}
