/**
 * Écran d'accueil : « Que souhaitez-vous analyser ? »
 *
 * Une carte par type d'analyse, avec le nombre de modèles réellement prêts.
 * POURQUOI afficher « 5 sur 5 » plutôt qu'un simple « 5 » : un modèle peut
 * être déclaré au registre sans que son fichier soit présent sur le disque du
 * pod. Montrer les deux chiffres évite de faire croire à une panne quand un
 * modèle est simplement en cours d'arrivée.
 */
import { Component, inject } from '@angular/core';

import { FR } from '../../core/i18n/libelles.fr';
import { RegistreStore } from '../../core/state/registre.store';

@Component({
  selector: 'app-accueil',
  standalone: true,
  templateUrl: './accueil.component.html',
  styleUrl: './accueil.component.css',
})
export class AccueilComponent {
  readonly fr = FR;
  readonly store = inject(RegistreStore);
}
