/**
 * Thème clair / sombre.
 *
 * Le thème se matérialise par un seul attribut, `data-theme`, posé sur
 * `<html>` : les tokens CSS du design system en dépendent, et les
 * utilitaires Tailwind aussi (variant `dark:` reconfiguré dans styles.css).
 * Changer cet attribut suffit donc à repeindre toute l'application, sans
 * rechargement et sans qu'un seul composant ait à s'en occuper.
 *
 * Choix par défaut : la préférence du système d'exploitation. Dès que
 * l'utilisateur bascule manuellement, son choix est mémorisé et prime — on
 * ne lui réimpose pas le réglage système à chaque visite.
 */
import { Injectable, signal } from '@angular/core';

export type Theme = 'light' | 'dark';

const CLE_STOCKAGE = 'medvision.theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly themeInterne = signal<Theme>('light');

  /** Thème courant, à lire dans les gabarits. */
  readonly theme = this.themeInterne.asReadonly();

  constructor() {
    this.appliquer(this.themeInitial());
  }

  /**
   * Bascule entre clair et sombre et mémorise le choix.
   *
   * @returns Le thème désormais actif.
   */
  basculer(): Theme {
    const suivant: Theme = this.themeInterne() === 'dark' ? 'light' : 'dark';
    this.appliquer(suivant);
    try {
      localStorage.setItem(CLE_STOCKAGE, suivant);
    } catch {
      // Navigation privée ou stockage plein : le thème reste actif pour la
      // session, il ne sera simplement pas retenu. Ce n'est pas une erreur
      // à remonter à l'utilisateur.
    }
    return suivant;
  }

  /**
   * Lit la couleur associée à un token du design system.
   *
   * POURQUOI ici : Chart.js dessine dans un canvas, il ne comprend pas les
   * variables CSS — il lui faut une couleur résolue. Les graphes appellent
   * donc cette méthode, et la rappellent quand le thème bascule.
   *
   * @param token Nom de la variable, sans les tirets (ex. `accent`, `ink-muted`).
   * @returns La couleur résolue, ou une chaîne vide si le token n'existe pas.
   * @example const couleur = theme.couleur('accent'); // "#0f7a66"
   */
  couleur(token: string): string {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(`--${token}`)
      .trim();
  }

  /** Pose l'attribut sur `<html>` et met le signal à jour. */
  private appliquer(theme: Theme): void {
    document.documentElement.setAttribute('data-theme', theme);
    this.themeInterne.set(theme);
  }

  /** Choix mémorisé s'il existe, sinon préférence du système. */
  private themeInitial(): Theme {
    try {
      const memorise = localStorage.getItem(CLE_STOCKAGE);
      if (memorise === 'light' || memorise === 'dark') {
        return memorise;
      }
    } catch {
      // Stockage inaccessible : on retombe sur la préférence système.
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
}
