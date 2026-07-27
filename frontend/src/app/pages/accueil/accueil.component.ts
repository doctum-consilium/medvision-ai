/**
 * Écran d'accueil.
 *
 * Il a deux missions, dans cet ordre : mettre en confiance, puis orienter.
 * D'où une accroche qui dit franchement ce que l'outil fait ET ce qu'il ne
 * fait pas, trois étapes qui montrent le parcours en un regard, et seulement
 * ensuite les types d'analyse.
 *
 * POURQUOI afficher « 5 sur 5 » plutôt qu'un simple « 5 » : un modèle peut
 * être déclaré au registre sans que son fichier soit présent sur le disque du
 * pod. Montrer les deux chiffres évite de faire croire à une panne quand un
 * modèle est simplement en cours d'arrivée.
 */
import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { FR, nomClasse } from '../../core/i18n/libelles.fr';
import { RegistreStore, type CarteProbleme } from '../../core/state/registre.store';

/** Famille d'illustration associée à un type d'analyse. */
export type Illustration = 'thorax' | 'cerveau' | 'zones';

@Component({
  selector: 'app-accueil',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './accueil.component.html',
  styleUrl: './accueil.component.css',
})
export class AccueilComponent {
  readonly fr = FR;
  readonly store = inject(RegistreStore);

  /**
   * Choisit l'illustration d'une carte.
   *
   * POURQUOI une déduction depuis l'identifiant plutôt qu'un champ de l'API :
   * le registre décrit des modèles, pas des pictogrammes. Ajouter une colonne
   * « icône » côté serveur mélangerait présentation et données ; et si un
   * nouveau type d'analyse arrive sans correspondance, on retombe simplement
   * sur l'illustration générique des zones.
   *
   * @param carte Le type d'analyse à illustrer.
   * @returns La famille d'illustration à afficher.
   * @example illustration({ id: 'chest_xray', … }) // 'thorax'
   */
  illustration(carte: CarteProbleme): Illustration {
    if (carte.estSegmentation) {
      return 'zones';
    }
    if (carte.id.includes('chest') || carte.id.includes('xray')) {
      return 'thorax';
    }
    if (carte.id.includes('brain') || carte.id.includes('mri')) {
      return 'cerveau';
    }
    return 'zones';
  }

  /**
   * Part des modèles réellement prêts, pour la jauge de la carte.
   *
   * @param carte Le type d'analyse concerné.
   * @returns Un pourcentage entre 0 et 100 (0 si aucun modèle n'est déclaré).
   */
  partPrete(carte: CarteProbleme): number {
    if (carte.modelesTotal === 0) {
      return 0;
    }
    return (carte.modelesDisponibles / carte.modelesTotal) * 100;
  }

  /**
   * Phrase du compteur, accordée en nombre.
   *
   * « 1 sur 1 modèles prêts » se remarque immédiatement et fait négligé sur
   * un produit qu'on veut sérieux — d'où cet accord explicite.
   *
   * @param carte Le type d'analyse concerné.
   * @returns Le texte qui suit le grand chiffre, par exemple
   *   « sur 5 modèles prêts » ou « sur 1 modèle prêt ».
   * @example compteDetail({ modelesTotal: 1, … }) // "sur 1 modèle prêt"
   */
  compteDetail(carte: CarteProbleme): string {
    const pluriel = carte.modelesTotal > 1 ? 's' : '';
    return `${FR.accueil.sur} ${carte.modelesTotal} modèle${pluriel} prêt${pluriel}`;
  }

  /**
   * Catégories reconnues, en français et prêtes à afficher.
   *
   * @param carte Le type d'analyse concerné.
   * @returns Les noms séparés par des virgules, par exemple
   *   « Normal, Pneumonie ».
   */
  classesLisibles(carte: CarteProbleme): string {
    return carte.classNames.map(nomClasse).join(', ');
  }
}
