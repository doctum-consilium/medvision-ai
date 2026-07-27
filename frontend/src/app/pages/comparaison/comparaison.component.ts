/**
 * Écran « Comparer les modèles ».
 *
 * Deux lectures de la même donnée, parce qu'elles ne répondent pas à la même
 * question : le tableau dit « combien exactement » (et se trie), le graphe dit
 * « lequel se détache » d'un coup d'œil.
 *
 * Les métriques peuvent manquer, et ce n'est PAS une panne : seul le stage
 * ONNX est tiré par DVC au démarrage du pod, les rapports d'entraînement ne
 * suivent pas toujours. L'écran le dit alors calmement plutôt que d'afficher
 * une erreur qui inquiéterait pour rien.
 */
import { Component, computed, effect, inject, input, signal } from '@angular/core';

import { ComparaisonService } from '../../core/api/comparaison.service';
import { FR } from '../../core/i18n/libelles.fr';
import { RegistreStore } from '../../core/state/registre.store';
import { GrapheBarresComponent, type SerieBarres } from '../../shared/graphe-barres.component';

/** Une ligne du tableau, métriques et informations de fichier réunies. */
export interface LigneModele {
  modele: string;
  disponible: boolean;
  /** Taille du fichier ONNX en méga-octets, ou null s'il est absent. */
  tailleMo: number | null;
  /** Date de dernière modification, déjà mise en forme, ou null. */
  misAJour: string | null;
  metriques: Record<string, number>;
}

/** Sens de tri d'une colonne. */
type Sens = 'asc' | 'desc';

/** Un méga-octet, pour convertir les tailles renvoyées en octets. */
const OCTETS_PAR_MO = 1024 * 1024;

@Component({
  selector: 'app-comparaison',
  standalone: true,
  imports: [GrapheBarresComponent],
  templateUrl: './comparaison.component.html',
  styleUrl: './comparaison.component.css',
})
export class ComparaisonComponent {
  readonly fr = FR;
  readonly store = inject(RegistreStore);
  private readonly api = inject(ComparaisonService);

  /** Type d'analyse demandé dans l'URL (`/comparaison?probleme=…`). */
  readonly probleme = input('');

  readonly problemeId = signal('');
  readonly chargement = signal(false);

  /** Métriques brutes renvoyées par l'API, indexées par modèle. */
  private readonly metriquesParModele = signal<Record<string, Record<string, number>>>({});

  /** Colonne de tri courante : un nom de métrique, ou `modele`. */
  readonly colonneTri = signal('modele');
  readonly sensTri = signal<Sens>('asc');

  /**
   * Les métriques réellement présentes, dans un ordre stable.
   *
   * Deux modèles peuvent ne pas exposer les mêmes : on prend l'union, et une
   * case vide vaut « non mesuré » — jamais zéro, qui se lirait comme un
   * résultat catastrophique.
   */
  readonly colonnesMetriques = computed(() => {
    const noms = new Set<string>();
    for (const metriques of Object.values(this.metriquesParModele())) {
      for (const nom of Object.keys(metriques)) {
        noms.add(nom);
      }
    }
    return [...noms].sort();
  });

  /** Les lignes du tableau, triées selon la colonne choisie. */
  readonly lignes = computed<LigneModele[]>(() => {
    const entree = this.store.problemes()[this.problemeId()];
    const metriques = this.metriquesParModele();
    if (!entree) {
      return [];
    }

    const lignes: LigneModele[] = Object.entries(entree.models).map(([modele, meta]) => ({
      modele,
      disponible: meta.available,
      tailleMo: meta.size_bytes === null ? null : meta.size_bytes / OCTETS_PAR_MO,
      misAJour: meta.modified_at === null ? null : meta.modified_at.slice(0, 10),
      metriques: metriques[modele] ?? {},
    }));

    return this.trier(lignes);
  });

  /** Vrai quand aucun modèle n'expose la moindre mesure. */
  readonly aucuneMesure = computed(() => this.colonnesMetriques().length === 0);

  /** Étiquettes du graphe : les modèles disponibles. */
  readonly etiquettesGraphe = computed(() =>
    this.lignes().filter((l) => l.disponible).map((l) => l.modele),
  );

  /** Une série par métrique, dans l'ordre des étiquettes. */
  readonly seriesGraphe = computed<SerieBarres[]>(() => {
    const lignes = this.lignes().filter((l) => l.disponible);
    return this.colonnesMetriques().map((nom) => ({
      nom,
      valeurs: lignes.map((ligne) => ligne.metriques[nom] ?? 0),
    }));
  });

  constructor() {
    // Sélection initiale : celle de l'URL si elle existe, sinon la première.
    effect(() => {
      const cartes = this.store.cartes();
      if (this.problemeId() !== '' || cartes.length === 0) {
        return;
      }
      const demande = this.probleme();
      const existe = cartes.some((c) => c.id === demande);
      this.choisirProbleme(existe ? demande : cartes[0].id);
    });
  }

  /** Change de type d'analyse et recharge ses mesures. */
  choisirProbleme(id: string): void {
    this.problemeId.set(id);
    this.colonneTri.set('modele');
    this.sensTri.set('asc');
    void this.charger(id);
  }

  /**
   * Trie sur une colonne. Recliquer la même colonne inverse le sens.
   *
   * @param colonne `modele` ou le nom d'une métrique.
   */
  trierPar(colonne: string): void {
    if (this.colonneTri() === colonne) {
      this.sensTri.set(this.sensTri() === 'asc' ? 'desc' : 'asc');
      return;
    }
    this.colonneTri.set(colonne);
    // Une métrique se lit « du meilleur au moins bon » : on part en
    // décroissant. Un nom de modèle, lui, se lit dans l'ordre alphabétique.
    this.sensTri.set(colonne === 'modele' ? 'asc' : 'desc');
  }

  /**
   * Annonce l'état de tri d'une colonne aux technologies d'assistance.
   *
   * @param colonne `modele` ou le nom d'une métrique.
   * @returns La valeur de l'attribut `aria-sort` attendue par les lecteurs
   *   d'écran : `ascending`, `descending`, ou `none` si ce n'est pas la
   *   colonne de tri courante.
   */
  ariaTri(colonne: string): 'ascending' | 'descending' | 'none' {
    if (this.colonneTri() !== colonne) {
      return 'none';
    }
    return this.sensTri() === 'asc' ? 'ascending' : 'descending';
  }

  /**
   * Flèche affichée dans l'en-tête d'une colonne.
   *
   * Les colonnes non triées gardent une flèche pâle plutôt que rien : sans
   * elle, on ne devine pas qu'elles sont triables tant qu'on n'a pas cliqué.
   *
   * @param colonne `modele` ou le nom d'une métrique.
   * @returns Le caractère à afficher.
   */
  flecheTri(colonne: string): string {
    if (this.colonneTri() !== colonne) {
      return '↕';
    }
    return this.sensTri() === 'asc' ? '▲' : '▼';
  }

  /** Met en forme une métrique (trois décimales), ou un tiret si absente. */
  formaterMetrique(ligne: LigneModele, colonne: string): string {
    const valeur = ligne.metriques[colonne];
    return valeur === undefined ? '—' : valeur.toFixed(3);
  }

  /** Met en forme une taille de fichier, ou un tiret si le modèle est absent. */
  formaterTaille(ligne: LigneModele): string {
    return ligne.tailleMo === null ? '—' : `${ligne.tailleMo.toFixed(1)} Mo`;
  }

  /** Applique le tri courant à une copie des lignes. */
  private trier(lignes: LigneModele[]): LigneModele[] {
    const colonne = this.colonneTri();
    const facteur = this.sensTri() === 'asc' ? 1 : -1;

    return [...lignes].sort((a, b) => {
      if (colonne === 'modele') {
        return a.modele.localeCompare(b.modele) * facteur;
      }
      // Un modèle sans mesure part toujours en fin de liste, quel que soit le
      // sens : le trier comme s'il valait zéro le ferait passer pour mauvais.
      const va = a.metriques[colonne];
      const vb = b.metriques[colonne];
      if (va === undefined && vb === undefined) {
        return 0;
      }
      if (va === undefined) {
        return 1;
      }
      if (vb === undefined) {
        return -1;
      }
      return (va - vb) * facteur;
    });
  }

  /** Récupère les mesures d'un type d'analyse. */
  private async charger(probleme: string): Promise<void> {
    this.chargement.set(true);
    try {
      const reponse = await this.api.lire(probleme);
      const parModele: Record<string, Record<string, number>> = {};
      for (const ligne of reponse.rows) {
        const metriques: Record<string, number> = {};
        for (const [cle, valeur] of Object.entries(ligne)) {
          // `model_name` et `available` décrivent la ligne, pas une mesure ;
          // et une métrique textuelle ne se compare pas — on l'écarte.
          if (cle !== 'model_name' && cle !== 'available' && typeof valeur === 'number') {
            metriques[cle] = valeur;
          }
        }
        parModele[String(ligne.model_name)] = metriques;
      }
      this.metriquesParModele.set(parModele);
    } catch {
      this.metriquesParModele.set({});
    } finally {
      this.chargement.set(false);
    }
  }
}
