/**
 * Superposition d'un masque de segmentation sur l'image analysée.
 *
 * LE POINT CLÉ : le serveur ne renvoie PAS un masque déjà décidé (noir ou
 * blanc), il renvoie une carte de PROBABILITÉS en niveaux de gris. Chaque
 * pixel dit « j'appartiens à la zone avec telle confiance ». Du coup, changer
 * la sensibilité revient à re-comparer ces valeurs à un seuil — un calcul de
 * quelques millisecondes dans le navigateur. Sans cela, chaque mouvement du
 * curseur relancerait une inférence sur un pod déjà à l'étroit, et l'utilisateur
 * attendrait une seconde à chaque cran.
 *
 * Trois façons de regarder la même donnée :
 *  - `superposition` : l'image, avec la zone retenue teintée par-dessus ;
 *  - `masque` : la zone retenue seule, en aplat, sans l'image ;
 *  - `probabilite` : la carte complète en dégradé, qui montre *où le modèle
 *    hésite* — c'est souvent l'information la plus honnête.
 */
import {
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';

import { ThemeService } from '../core/theme/theme.service';

/** Les trois vues proposées à l'utilisateur. */
export type VueSegmentation = 'superposition' | 'masque' | 'probabilite';

/** Préfixe à ajouter au base64 renvoyé par l'API (elle n'en met pas). */
const PREFIXE_PNG = 'data:image/png;base64,';

@Component({
  selector: 'app-superposition-segmentation',
  standalone: true,
  template: `
    <canvas #toile [attr.aria-label]="descriptionAccessible()" role="img"></canvas>
    @if (!pret()) {
      <div class="skeleton chargement"></div>
    }
  `,
  styles: [
    `
      :host {
        display: block;
        position: relative;
        width: 100%;
      }
      canvas {
        display: block;
        width: 100%;
        height: auto;
        border-radius: var(--radius-sm);
        background: var(--surface-2);
        /* Les images médicales sont petites (256 px) et volontairement
           pixellisées : lisser masquerait la granularité du masque. */
        image-rendering: pixelated;
      }
      .chargement {
        position: absolute;
        inset: 0;
        border-radius: var(--radius-sm);
      }
    `,
  ],
})
export class SuperpositionSegmentationComponent {
  private readonly theme = inject(ThemeService);
  private readonly toile = viewChild.required<ElementRef<HTMLCanvasElement>>('toile');

  /** Image telle que vue par le modèle (PNG base64, sans préfixe). */
  readonly imagePng = input.required<string>();

  /** Carte de probabilités en niveaux de gris (PNG base64, sans préfixe). */
  readonly masqueProbaPng = input.required<string>();

  /** Sensibilité : un pixel est retenu si sa probabilité l'atteint. */
  readonly seuil = input(0.5);

  /** Opacité de la teinte, de 0 (invisible) à 1 (opaque). */
  readonly opacite = input(0.55);

  /** Vue affichée. */
  readonly vue = input<VueSegmentation>('superposition');

  readonly descriptionAccessible = input('Zones détectées par le modèle');

  /** Faux tant que les deux images ne sont pas décodées. */
  readonly pret = signal(false);

  /** Images décodées, gardées en mémoire pour ne pas les redécoder à chaque cran. */
  private readonly image = signal<HTMLImageElement | null>(null);
  private readonly masque = signal<HTMLImageElement | null>(null);

  /** Probabilités brutes du masque, une valeur [0,1] par pixel. */
  private readonly probabilites = computed(() => {
    const masque = this.masque();
    return masque ? this.extraireProbabilites(masque) : null;
  });

  constructor() {
    // Décodage : ne se relance QUE si les images changent (nouvelle analyse),
    // pas quand on bouge le curseur.
    effect(() => {
      const png = this.imagePng();
      const masquePng = this.masqueProbaPng();
      this.pret.set(false);
      void Promise.all([this.charger(png), this.charger(masquePng)]).then(
        ([image, masque]) => {
          this.image.set(image);
          this.masque.set(masque);
          this.pret.set(true);
        },
      );
    });

    // Rendu : dépend du seuil, de l'opacité, de la vue et du thème. C'est
    // CETTE partie qui tourne à chaque mouvement du curseur — et elle ne
    // touche jamais le réseau.
    effect(() => {
      const image = this.image();
      const probabilites = this.probabilites();
      const seuil = this.seuil();
      const opacite = this.opacite();
      const vue = this.vue();
      this.theme.theme();
      if (image && probabilites) {
        this.dessiner(image, probabilites, seuil, opacite, vue);
      }
    });

    inject(DestroyRef).onDestroy(() => {
      this.image.set(null);
      this.masque.set(null);
    });
  }

  /** Charge un PNG base64 en image décodée. */
  private charger(base64: string): Promise<HTMLImageElement> {
    return new Promise((resoudre, rejeter) => {
      const image = new Image();
      image.onload = () => resoudre(image);
      image.onerror = () => rejeter(new Error('PNG illisible'));
      image.src = PREFIXE_PNG + base64;
    });
  }

  /**
   * Extrait les probabilités du PNG en niveaux de gris.
   *
   * Le canal rouge suffit : l'image est grise, donc rouge = vert = bleu.
   * On normalise sur [0,1] une fois pour toutes, ce qui rend le re-seuillage
   * ensuite quasi instantané (une comparaison par pixel).
   */
  private extraireProbabilites(masque: HTMLImageElement): {
    valeurs: Float32Array;
    largeur: number;
    hauteur: number;
  } {
    const largeur = masque.naturalWidth;
    const hauteur = masque.naturalHeight;
    const tampon = document.createElement('canvas');
    tampon.width = largeur;
    tampon.height = hauteur;
    const contexte = tampon.getContext('2d', { willReadFrequently: true });
    if (!contexte) {
      return { valeurs: new Float32Array(0), largeur: 0, hauteur: 0 };
    }
    contexte.drawImage(masque, 0, 0);
    const pixels = contexte.getImageData(0, 0, largeur, hauteur).data;

    const valeurs = new Float32Array(largeur * hauteur);
    for (let i = 0; i < valeurs.length; i += 1) {
      valeurs[i] = pixels[i * 4] / 255;
    }
    return { valeurs, largeur, hauteur };
  }

  /** Compose la vue demandée dans le canvas visible. */
  private dessiner(
    image: HTMLImageElement,
    probabilites: { valeurs: Float32Array; largeur: number; hauteur: number },
    seuil: number,
    opacite: number,
    vue: VueSegmentation,
  ): void {
    const { valeurs, largeur, hauteur } = probabilites;
    if (largeur === 0 || hauteur === 0) {
      return;
    }

    const toile = this.toile().nativeElement;
    toile.width = largeur;
    toile.height = hauteur;
    const contexte = toile.getContext('2d');
    if (!contexte) {
      return;
    }

    contexte.clearRect(0, 0, largeur, hauteur);
    if (vue !== 'masque') {
      contexte.drawImage(image, 0, 0, largeur, hauteur);
    }

    const teinte = this.composantesRvb(this.theme.couleur('accent'));
    const calque = contexte.createImageData(largeur, hauteur);

    for (let i = 0; i < valeurs.length; i += 1) {
      const probabilite = valeurs[i];
      const decalage = i * 4;

      if (vue === 'probabilite') {
        // Dégradé continu : plus le modèle est sûr, plus c'est marqué. On
        // laisse transparent en dessous de 5 % pour ne pas voiler l'image
        // entière d'un brouillard uniforme.
        calque.data[decalage] = teinte[0];
        calque.data[decalage + 1] = teinte[1];
        calque.data[decalage + 2] = teinte[2];
        calque.data[decalage + 3] = probabilite < 0.05 ? 0 : probabilite * 255 * opacite;
        continue;
      }

      const retenu = probabilite >= seuil;
      calque.data[decalage] = teinte[0];
      calque.data[decalage + 1] = teinte[1];
      calque.data[decalage + 2] = teinte[2];
      calque.data[decalage + 3] = retenu ? (vue === 'masque' ? 255 : opacite * 255) : 0;
    }

    // `putImageData` écraserait l'image du dessous : on passe par un canvas
    // intermédiaire pour obtenir une vraie composition alpha.
    const tampon = document.createElement('canvas');
    tampon.width = largeur;
    tampon.height = hauteur;
    tampon.getContext('2d')?.putImageData(calque, 0, 0);
    contexte.drawImage(tampon, 0, 0);
  }

  /**
   * Convertit une couleur CSS (`#rrggbb` ou `#rgb`) en composantes.
   *
   * @returns Le triplet rouge/vert/bleu, ou le vert médical par défaut si la
   *   couleur n'est pas reconnue.
   */
  private composantesRvb(couleur: string): [number, number, number] {
    const hex = couleur.trim().replace('#', '');
    const complet =
      hex.length === 3
        ? hex
            .split('')
            .map((c) => c + c)
            .join('')
        : hex;
    if (complet.length !== 6 || Number.isNaN(Number.parseInt(complet, 16))) {
      return [15, 122, 102];
    }
    return [
      Number.parseInt(complet.slice(0, 2), 16),
      Number.parseInt(complet.slice(2, 4), 16),
      Number.parseInt(complet.slice(4, 6), 16),
    ];
  }
}
