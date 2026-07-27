/**
 * Écran « Analyser une image ».
 *
 * L'utilisateur choisit un type d'analyse, fournit une image (la sienne ou
 * une de la banque d'exemples), coche les modèles à interroger, et lit les
 * résultats côte à côte.
 *
 * RÈGLE PRODUIT QUI GOUVERNE CET ÉCRAN : sur un type d'analyse de
 * segmentation, on n'affiche NI classe prédite, NI confiance, NI
 * probabilités. Ces modèles délimitent des zones, point. Leur tête de
 * classification annonçait « NORMAL » avec une confiance de 1,000 sur des
 * pneumonies manifestes — laisser passer ce chiffre serait trompeur, et sur
 * un sujet médical c'est inacceptable. Le gabarit s'appuie sur
 * `estSegmentation` pour trancher ; ne jamais contourner ce garde-fou.
 */
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { FR, nomClasse } from '../../core/i18n/libelles.fr';
import { ImagesService } from '../../core/api/images.service';
import { PredictionService } from '../../core/api/prediction.service';
import { RegistreStore } from '../../core/state/registre.store';
import { GrapheBarresComponent } from '../../shared/graphe-barres.component';
import {
  SuperpositionSegmentationComponent,
  type VueSegmentation,
} from '../../shared/superposition-segmentation.component';
import type { Echantillon, ImagesReponse, ResultatModele } from '../../core/api/api.types';

/** D'où vient l'image à analyser. */
type SourceImage = 'banque' | 'depot';

/** Un modèle proposé à la sélection. */
interface ModeleChoisissable {
  nom: string;
  disponible: boolean;
}

@Component({
  selector: 'app-studio',
  standalone: true,
  imports: [FormsModule, GrapheBarresComponent, SuperpositionSegmentationComponent],
  templateUrl: './studio.component.html',
  styleUrl: './studio.component.css',
})
export class StudioComponent {
  readonly fr = FR;
  /** Exposé au gabarit pour traduire les étiquettes venues de l'API. */
  readonly nomClasse = nomClasse;
  readonly store = inject(RegistreStore);
  private readonly imagesApi = inject(ImagesService);
  private readonly predictionApi = inject(PredictionService);

  /**
   * Type d'analyse demandé dans l'URL (`/studio?probleme=…`).
   *
   * Alimenté par le routeur (`withComponentInputBinding`) : c'est ce qui
   * permet à l'accueil d'ouvrir directement la bonne analyse, et à un lien
   * partagé de retomber sur le même écran.
   */
  readonly probleme = input('');

  // ── Choix de l'utilisateur ────────────────────────────────────────────
  readonly problemeId = signal('');
  readonly source = signal<SourceImage>('banque');
  readonly labelsChoisis = signal<string[]>([]);
  readonly recherche = signal('');
  readonly page = signal(1);
  readonly sampleChoisi = signal<Echantillon | null>(null);
  readonly fichier = signal<File | null>(null);
  readonly apercuDepot = signal<string | null>(null);
  readonly modelesChoisis = signal<Set<string>>(new Set());

  // ── Réglages d'affichage des zones (100 % côté navigateur) ────────────
  readonly seuil = signal(0.5);
  readonly opacite = signal(0.55);
  readonly vue = signal<VueSegmentation>('superposition');

  // ── État de l'analyse ─────────────────────────────────────────────────
  readonly banque = signal<ImagesReponse | null>(null);
  readonly chargementBanque = signal(false);
  readonly enCours = signal(false);
  readonly resultats = signal<ResultatModele[]>([]);
  readonly erreur = signal<string | null>(null);

  /** Le type d'analyse courant, tel que décrit par le registre. */
  readonly carte = computed(() =>
    this.store.cartes().find((c) => c.id === this.problemeId()) ?? null,
  );

  /** Vrai si l'analyse courante délimite des zones sans poser de diagnostic. */
  readonly estSegmentation = computed(() => this.carte()?.estSegmentation ?? false);

  /** Les modèles du type d'analyse courant, indisponibles compris. */
  readonly modeles = computed<ModeleChoisissable[]>(() => {
    const entree = this.store.problemes()[this.problemeId()];
    if (!entree) {
      return [];
    }
    return Object.entries(entree.models).map(([nom, meta]) => ({
      nom,
      disponible: meta.available,
    }));
  });

  /** Classes proposées comme filtres de la banque d'exemples. */
  readonly classes = computed(() => this.carte()?.classNames ?? []);

  /** Nombre de pages de la banque, pour la pagination. */
  readonly nombrePages = computed(() => {
    const banque = this.banque();
    if (!banque || banque.page_size === 0) {
      return 1;
    }
    return Math.max(1, Math.ceil(banque.total / banque.page_size));
  });

  /** Vrai quand tout est réuni pour lancer une analyse. */
  readonly peutAnalyser = computed(() => {
    if (this.enCours() || this.modelesChoisis().size === 0) {
      return false;
    }
    return this.source() === 'depot' ? this.fichier() !== null : this.sampleChoisi() !== null;
  });

  constructor() {
    // Sélection initiale : celle demandée dans l'URL si elle existe, sinon le
    // premier type d'analyse. Arriver sur un écran vide avec trois listes à
    // remplir décourage.
    effect(() => {
      const cartes = this.store.cartes();
      if (this.problemeId() !== '' || cartes.length === 0) {
        return;
      }
      const demande = this.probleme();
      const existe = cartes.some((c) => c.id === demande);
      this.choisirProbleme(existe ? demande : cartes[0].id);
    });

    // La banque se recharge dès qu'un critère change.
    effect(() => {
      const probleme = this.problemeId();
      const labels = this.labelsChoisis();
      const recherche = this.recherche();
      const page = this.page();
      if (probleme === '') {
        return;
      }
      void this.chargerBanque(probleme, labels, recherche, page);
    });
  }

  /**
   * Change de type d'analyse et repart d'un état propre.
   *
   * On coche d'emblée les modèles disponibles : l'intérêt de l'écran est de
   * comparer, pas de cliquer.
   */
  choisirProbleme(id: string): void {
    this.problemeId.set(id);
    this.labelsChoisis.set([]);
    this.recherche.set('');
    this.page.set(1);
    this.sampleChoisi.set(null);
    this.resultats.set([]);
    this.erreur.set(null);

    const entree = this.store.problemes()[id];
    const disponibles = entree
      ? Object.entries(entree.models)
          .filter(([, meta]) => meta.available)
          .map(([nom]) => nom)
      : [];
    // Au-delà de trois modèles l'écran devient illisible et l'analyse longue :
    // on en propose trois, l'utilisateur en ajoute s'il veut.
    this.modelesChoisis.set(new Set(disponibles.slice(0, 3)));
  }

  /** Active ou désactive un filtre de classe dans la banque d'exemples. */
  basculerLabel(label: string): void {
    const courants = new Set(this.labelsChoisis());
    if (courants.has(label)) {
      courants.delete(label);
    } else {
      courants.add(label);
    }
    this.labelsChoisis.set([...courants]);
    this.page.set(1);
  }

  /** Coche ou décoche un modèle. */
  basculerModele(nom: string): void {
    const courants = new Set(this.modelesChoisis());
    if (courants.has(nom)) {
      courants.delete(nom);
    } else {
      courants.add(nom);
    }
    this.modelesChoisis.set(courants);
  }

  /** Coche tous les modèles disponibles. */
  toutSelectionner(): void {
    this.modelesChoisis.set(
      new Set(this.modeles().filter((m) => m.disponible).map((m) => m.nom)),
    );
  }

  /** Décoche tout. */
  toutDeselectionner(): void {
    this.modelesChoisis.set(new Set());
  }

  /** Choisit un exemple de la banque. */
  choisirExemple(exemple: Echantillon): void {
    this.source.set('banque');
    this.sampleChoisi.set(exemple);
    this.resultats.set([]);
  }

  /** Prend en compte une image déposée par l'utilisateur. */
  deposerFichier(fichier: File | null | undefined): void {
    if (!fichier) {
      return;
    }
    const ancien = this.apercuDepot();
    if (ancien) {
      // Libérer l'URL précédente : sans ça, chaque dépôt laisse une image en
      // mémoire jusqu'au rechargement de la page.
      URL.revokeObjectURL(ancien);
    }
    this.source.set('depot');
    this.fichier.set(fichier);
    this.apercuDepot.set(URL.createObjectURL(fichier));
    this.sampleChoisi.set(null);
    this.resultats.set([]);
  }

  /** Récupère le fichier d'un `<input type="file">`. */
  surSelectionFichier(evenement: Event): void {
    this.deposerFichier((evenement.target as HTMLInputElement).files?.[0]);
  }

  /** Récupère le fichier d'un glisser-déposer. */
  surDepot(evenement: DragEvent): void {
    evenement.preventDefault();
    this.deposerFichier(evenement.dataTransfer?.files?.[0]);
  }

  /** URL de la vignette d'un exemple. */
  urlVignette(exemple: Echantillon): string {
    return this.imagesApi.urlFichier(this.problemeId(), exemple.sample_id);
  }

  /** URL pleine taille de l'exemple sélectionné. */
  urlApercu(): string | null {
    const exemple = this.sampleChoisi();
    if (this.source() === 'depot') {
      return this.apercuDepot();
    }
    return exemple ? this.imagesApi.urlFichier(this.problemeId(), exemple.sample_id, false) : null;
  }

  /** Étiquettes du graphe de probabilités d'un résultat, en français. */
  etiquettesProbabilites(resultat: ResultatModele): string[] {
    return Object.keys(resultat.probabilities ?? {}).map(nomClasse);
  }

  /**
   * Classe prédite, traduite pour l'affichage.
   *
   * @param resultat Le résultat d'un modèle.
   * @returns Le nom français de la classe, ou une chaîne vide s'il n'y en a
   *   pas (cas des analyses de segmentation).
   */
  classePredite(resultat: ResultatModele): string {
    return resultat.predicted_class ? nomClasse(resultat.predicted_class) : '';
  }

  /** Séries du graphe de probabilités d'un résultat. */
  seriesProbabilites(resultat: ResultatModele): { nom: string; valeurs: number[] }[] {
    return [{ nom: this.fr.studio.probabilites, valeurs: Object.values(resultat.probabilities ?? {}) }];
  }

  /** Surface détectée, en pourcentage lisible. */
  surfacePourcent(resultat: ResultatModele): string {
    const ratio = resultat.segmentation?.mask_foreground_ratio ?? 0;
    return `${(ratio * 100).toFixed(1)} %`;
  }

  /**
   * Lance l'analyse sur les modèles cochés.
   *
   * Les erreurs par modèle reviennent DANS la réponse (champ `error`) : seule
   * une panne globale (réseau, 404) atterrit ici.
   */
  async analyser(): Promise<void> {
    if (!this.peutAnalyser()) {
      return;
    }
    this.enCours.set(true);
    this.erreur.set(null);
    try {
      const reponse = await this.predictionApi.analyser({
        probleme: this.problemeId(),
        modeles: [...this.modelesChoisis()],
        fichier: this.source() === 'depot' ? (this.fichier() ?? undefined) : undefined,
        sampleId: this.source() === 'banque' ? this.sampleChoisi()?.sample_id : undefined,
        seuilMasque: this.seuil(),
      });
      this.resultats.set(reponse.results);
    } catch {
      this.erreur.set(FR.erreurs.analyse);
    } finally {
      this.enCours.set(false);
    }
  }

  /** Charge une page de la banque d'exemples. */
  private async chargerBanque(
    probleme: string,
    labels: string[],
    recherche: string,
    page: number,
  ): Promise<void> {
    this.chargementBanque.set(true);
    try {
      this.banque.set(await this.imagesApi.lister({ probleme, labels, recherche, page }));
    } catch {
      // La banque peut être absente (dataset non monté sur le pod) : ce n'est
      // pas une panne de l'application, l'utilisateur peut toujours déposer
      // sa propre image.
      this.banque.set(null);
    } finally {
      this.chargementBanque.set(false);
    }
  }
}
