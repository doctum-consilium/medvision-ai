/**
 * Source de vérité de l'application : le registre des modèles.
 *
 * POURQUOI un store et pas un appel HTTP par écran : les trois écrans
 * (accueil, studio, comparaison) parlent des mêmes types d'analyse et des
 * mêmes modèles. Les charger une fois, au même endroit, garantit qu'ils
 * racontent tous la même chose — y compris après l'arrivée d'un modèle
 * annoncée par le flux temps réel.
 *
 * On utilise `@ngrx/signals` : la déclaration tient en un fichier, l'état
 * reste en lecture seule pour les composants, et les valeurs dérivées
 * (compteurs, listes triées) se recalculent toutes seules.
 */
import { computed, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withMethods,
  withState,
} from '@ngrx/signals';

import { NOMS_ANALYSES } from '../i18n/libelles.fr';
import { RegistreService } from '../api/registre.service';
import type { ProblemeAvecModeles } from '../api/api.types';

/** Un type d'analyse prêt à être affiché sur une carte d'accueil. */
export interface CarteProbleme {
  id: string;
  label: string;
  taskType: ProblemeAvecModeles['task_type'];
  classNames: string[];
  modelesDisponibles: number;
  modelesTotal: number;
  /** Vrai pour les analyses qui délimitent des zones sans poser de diagnostic. */
  estSegmentation: boolean;
}

interface EtatRegistre {
  version: string;
  problemes: Record<string, ProblemeAvecModeles>;
  chargement: boolean;
  /** Message lisible affiché à l'utilisateur, ou null si tout va bien. */
  erreur: string | null;
}

const ETAT_INITIAL: EtatRegistre = {
  version: '',
  problemes: {},
  chargement: false,
  erreur: null,
};

export const RegistreStore = signalStore(
  { providedIn: 'root' },
  withState(ETAT_INITIAL),

  withComputed(({ problemes, version }) => ({
    /** Les types d'analyse, mis en forme pour l'accueil et les sélecteurs. */
    cartes: computed<CarteProbleme[]>(() =>
      Object.entries(problemes()).map(([id, entree]) => {
        const modeles = Object.values(entree.models);
        return {
          id,
          // Nom français s'il existe, sinon le libellé du serveur (anglais) :
          // mieux vaut un nom non traduit qu'une carte sans nom.
          label: NOMS_ANALYSES[id] ?? entree.label,
          taskType: entree.task_type,
          classNames: entree.class_names,
          modelesDisponibles: modeles.filter((m) => m.available).length,
          modelesTotal: modeles.length,
          estSegmentation: entree.task_type === 'segmentation',
        };
      }),
    ),

    /** Nombre total de modèles utilisables, tous types d'analyse confondus. */
    totalDisponibles: computed(() =>
      Object.values(problemes()).reduce(
        (total, entree) =>
          total + Object.values(entree.models).filter((m) => m.available).length,
        0,
      ),
    ),

    /** Vrai tant qu'aucun registre n'a été chargé avec succès. */
    vide: computed(() => version() === ''),
  })),

  withMethods((store, api = inject(RegistreService)) => {
    /**
     * Recharge le registre depuis l'API.
     *
     * Ne vide PAS l'état en cas d'échec : mieux vaut afficher un registre
     * légèrement périmé avec un message d'erreur qu'un écran blanc — le
     * serveur peut simplement être en train de redémarrer.
     */
    const recharger = async (): Promise<void> => {
      patchState(store, { chargement: true, erreur: null });
      try {
        const reponse = await api.lire();
        patchState(store, {
          version: reponse.version,
          problemes: reponse.problems,
          chargement: false,
        });
      } catch {
        patchState(store, {
          chargement: false,
          erreur: 'Impossible de charger les données. Nouvelle tentative…',
        });
      }
    };

    /**
     * Recharge SEULEMENT si la version du serveur diffère de celle en mémoire.
     *
     * Appelé après une reconnexion du flux temps réel : dans la très grande
     * majorité des cas rien n'a bougé, et on économise le transfert du
     * registre complet.
     *
     * @returns Vrai si un rechargement a réellement eu lieu.
     */
    const resynchroniser = async (): Promise<boolean> => {
      try {
        const { version } = await api.lireVersion();
        if (version === store.version()) {
          return false;
        }
      } catch {
        // API injoignable : on retentera au prochain passage.
        return false;
      }
      await recharger();
      return true;
    };

    return { recharger, resynchroniser };
  }),
);
