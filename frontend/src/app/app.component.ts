/**
 * Coquille de l'application : en-tête, navigation, avertissement médical.
 *
 * C'est ici qu'on charge le registre et qu'on ouvre le flux temps réel, une
 * fois pour toute l'application — les écrans n'ont plus qu'à lire le store.
 * Le composant reste volontairement mince : il orchestre, il n'affiche pas
 * de données métier.
 */
import { Component, computed, effect, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { FR } from './core/i18n/libelles.fr';
import { SseService } from './core/realtime/sse.service';
import { RegistreStore } from './core/state/registre.store';
import { ThemeService } from './core/theme/theme.service';

/** Un onglet de la navigation principale. */
interface Onglet {
  chemin: string;
  libelle: string;
}

/** Durée d'affichage du message « nouveaux modèles » (millisecondes). */
const DUREE_ANNONCE_MS = 8_000;

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
})
export class AppComponent {
  readonly fr = FR;
  readonly store = inject(RegistreStore);
  readonly theme = inject(ThemeService);
  private readonly sse = inject(SseService);

  /**
   * Onglets proposés. La liste grandit au fur et à mesure que les écrans
   * sont livrés — on ne propose jamais un lien qui mène à une page absente.
   */
  readonly onglets: Onglet[] = [
    { chemin: '', libelle: FR.nav.accueil },
    { chemin: 'studio', libelle: FR.nav.studio },
    { chemin: 'comparaison', libelle: FR.nav.comparaison },
  ];

  /** État de la connexion temps réel, pour la pastille de l'en-tête. */
  readonly etatFlux = this.sse.etat;

  /** Texte de la pastille : « connecté » ou « reconnexion… ». */
  readonly libelleFlux = computed(() =>
    this.etatFlux() === 'connecte' ? FR.app.connecte : FR.app.reconnexion,
  );

  /** Vrai pendant quelques secondes après l'arrivée de nouveaux modèles. */
  readonly annonceNouveaute = signal(false);

  /** Version du registre déjà annoncée, pour ne pas répéter le message. */
  private versionAnnoncee = '';

  constructor() {
    void this.store.recharger();

    this.sse.demarrer(() => {
      // Reconnexion : on a peut-être manqué une arrivée de modèles pendant
      // la coupure. On demande la version au serveur ; s'il n'y a rien de
      // neuf, ça ne coûte que quelques octets.
      void this.store.resynchroniser().then((aChange) => {
        if (aChange) {
          this.annoncer();
        }
      });
    });

    // Un modèle est arrivé alors qu'on était connecté : recharger et le dire,
    // sans que l'utilisateur ait à rafraîchir la page.
    effect(() => {
      const evenement = this.sse.dernierEvenement();
      if (!evenement || evenement.version === this.versionAnnoncee) {
        return;
      }
      this.versionAnnoncee = evenement.version;
      void this.store.recharger();
      this.annoncer();
    });
  }

  /** Bascule le thème clair/sombre. */
  basculerTheme(): void {
    this.theme.basculer();
  }

  /** Affiche le message « nouveaux modèles » puis l'efface tout seul. */
  private annoncer(): void {
    this.annonceNouveaute.set(true);
    setTimeout(() => this.annonceNouveaute.set(false), DUREE_ANNONCE_MS);
  }
}
