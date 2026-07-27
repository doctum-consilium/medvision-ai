/**
 * Accès au registre des modèles (`GET /api/models`, `GET /api/models/version`).
 *
 * Le registre est la source de vérité du produit : quels types d'analyse
 * existent, quels modèles sont réellement présents sur le disque du pod, et
 * quelles métriques ils affichent. Il change tout seul quand un modèle est
 * poussé via DVC — d'où la notion de « version » (voir SseService).
 */
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { API_BASE } from './api.config';
import type { RegistreReponse } from './api.types';

/** Réponse allégée de `/api/models/version`, utilisée pour la resynchronisation. */
export interface VersionRegistre {
  version: string;
  refreshed_at: string | null;
}

@Injectable({ providedIn: 'root' })
export class RegistreService {
  private readonly http = inject(HttpClient);

  /**
   * Lit le registre complet (tous les problèmes et tous leurs modèles).
   *
   * @returns Le registre enrichi (taille et date de chaque fichier ONNX).
   * @throws HttpErrorResponse Si l'API est injoignable ou répond en erreur.
   */
  lire(): Promise<RegistreReponse> {
    return firstValueFrom(this.http.get<RegistreReponse>(`${API_BASE}/models`));
  }

  /**
   * Lit uniquement la version du registre.
   *
   * POURQUOI un appel séparé : après une coupure du flux temps réel, on veut
   * savoir si quelque chose a bougé sans retélécharger tout le registre. Une
   * chaîne contre quelques kilo-octets.
   *
   * @returns La version courante et la date du dernier rafraîchissement.
   */
  lireVersion(): Promise<VersionRegistre> {
    return firstValueFrom(this.http.get<VersionRegistre>(`${API_BASE}/models/version`));
  }
}
