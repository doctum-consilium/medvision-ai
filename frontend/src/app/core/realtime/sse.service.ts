/**
 * Flux temps réel des modèles (`GET /api/events`, Server-Sent Events).
 *
 * POURQUOI un flux poussé et pas du sondage : quand un modèle est entraîné
 * puis poussé dans S3, le serveur le détecte et le télécharge tout seul. Sans
 * flux, l'interface ne l'apprendrait qu'au prochain rechargement de page —
 * ou obligerait chaque onglet ouvert à interroger l'API en boucle, ce qui
 * réveille un pod à 2 Gi pour rien la plupart du temps.
 *
 * Deux événements arrivent sur ce flux :
 *  - `heartbeat` toutes les 25 s — il ne dit rien d'utile, mais son ABSENCE
 *    prouve que la connexion est morte (un proxy peut couper sans prévenir) ;
 *  - `models_updated` — le registre a changé, il faut le relire.
 *
 * À la reconnexion, on ne fait pas confiance au flux pour rattraper ce qui
 * s'est passé pendant la coupure : on interroge `/api/models/version` et on ne
 * recharge le registre que si la version a bougé.
 */
import { DestroyRef, Injectable, NgZone, inject, signal } from '@angular/core';

import { API_BASE } from '../api/api.config';

/** État de la connexion, tel qu'affiché par la pastille de l'en-tête. */
export type EtatFlux = 'connexion' | 'connecte' | 'reconnexion';

/** Charge utile de l'événement `models_updated`. */
export interface EvenementModeles {
  version: string;
  /** Modèles devenus disponibles depuis la dernière synchronisation. */
  changed: string[];
  at: string | null;
}

/** Première attente avant reconnexion, puis doublement jusqu'au plafond. */
const BACKOFF_INITIAL_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

@Injectable({ providedIn: 'root' })
export class SseService {
  private readonly zone = inject(NgZone);
  private readonly etatInterne = signal<EtatFlux>('connexion');

  /** État de la connexion, à lire dans les gabarits. */
  readonly etat = this.etatInterne.asReadonly();

  /**
   * Dernier événement `models_updated` reçu. Le store s'y abonne pour
   * recharger, et l'en-tête pour afficher le message « nouveaux modèles ».
   */
  private readonly dernierEvenementInterne = signal<EvenementModeles | null>(null);
  readonly dernierEvenement = this.dernierEvenementInterne.asReadonly();

  private source: EventSource | null = null;
  private attenteMs = BACKOFF_INITIAL_MS;
  private minuteur: ReturnType<typeof setTimeout> | null = null;
  private demarre = false;
  /**
   * Vrai dès la PREMIÈRE ouverture réussie. Sert à distinguer « je me
   * connecte » de « je me RE-connecte » : seule la seconde justifie de
   * vérifier ce qu'on a manqué. Un drapeau explicite plutôt qu'une déduction
   * à partir du délai de recul, qui devenait fausse dès la deuxième coupure.
   */
  private dejaConnecte = false;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.arreter());
  }

  /**
   * Ouvre le flux. Appelable plusieurs fois sans risque : les appels
   * suivants sont ignorés tant que le flux vit.
   *
   * @param surReconnexion Appelé après chaque reconnexion réussie — c'est là
   *   que l'appelant vérifie s'il a manqué quelque chose pendant la coupure.
   */
  demarrer(surReconnexion?: () => void): void {
    if (this.demarre) {
      return;
    }
    this.demarre = true;
    this.connecter(surReconnexion);
  }

  /** Ferme le flux et annule toute reconnexion en attente. */
  arreter(): void {
    this.demarre = false;
    if (this.minuteur !== null) {
      clearTimeout(this.minuteur);
      this.minuteur = null;
    }
    this.source?.close();
    this.source = null;
  }

  /**
   * Ouvre une connexion et arme la reconnexion en cas de coupure.
   *
   * Les rappels d'`EventSource` arrivent hors de la zone Angular : on
   * repasse dedans (`zone.run`) pour que la mise à jour des signaux déclenche
   * bien un rafraîchissement de l'affichage.
   */
  private connecter(surReconnexion?: () => void): void {
    const source = new EventSource(`${API_BASE}/events`);
    this.source = source;

    source.onopen = () => {
      this.zone.run(() => {
        this.etatInterne.set('connecte');
        this.attenteMs = BACKOFF_INITIAL_MS;
        if (this.dejaConnecte) {
          surReconnexion?.();
        }
        this.dejaConnecte = true;
      });
    };

    source.addEventListener('models_updated', (evenement) => {
      this.zone.run(() => {
        try {
          this.dernierEvenementInterne.set(
            JSON.parse((evenement as MessageEvent<string>).data) as EvenementModeles,
          );
        } catch {
          // Un message illisible ne doit pas tuer le flux : on l'ignore.
          // Le prochain événement (ou la resynchronisation) rattrapera.
        }
      });
    });

    source.onerror = () => {
      // EventSource se reconnecte tout seul, mais sans plafond ni recul :
      // sur une API en train de redémarrer, ça martèle. On reprend la main.
      source.close();
      this.source = null;
      this.zone.run(() => this.etatInterne.set('reconnexion'));
      if (!this.demarre) {
        return;
      }
      this.minuteur = setTimeout(() => this.connecter(surReconnexion), this.attenteMs);
      this.attenteMs = Math.min(this.attenteMs * 2, BACKOFF_MAX_MS);
    };
  }
}
