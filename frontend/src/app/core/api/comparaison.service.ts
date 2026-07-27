/**
 * Tableau comparatif des modèles (`GET /api/compare`).
 *
 * Les métriques viennent des rapports produits à l'entraînement. Elles
 * peuvent manquer : seul le stage ONNX est tiré par DVC au démarrage du pod,
 * les rapports ne suivent pas toujours. L'écran doit donc savoir afficher
 * « aucune mesure disponible » sans considérer ça comme une erreur.
 */
import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { API_BASE } from './api.config';
import type { ComparaisonReponse } from './api.types';

@Injectable({ providedIn: 'root' })
export class ComparaisonService {
  private readonly http = inject(HttpClient);

  /**
   * Lit les métriques de tous les modèles d'un type d'analyse.
   *
   * @param probleme Identifiant du type d'analyse.
   * @returns Une ligne par modèle, avec ses métriques à plat.
   * @throws HttpErrorResponse 404 si le type d'analyse est inconnu.
   */
  lire(probleme: string): Promise<ComparaisonReponse> {
    const params = new HttpParams().set('problem', probleme);
    return firstValueFrom(this.http.get<ComparaisonReponse>(`${API_BASE}/compare`, { params }));
  }
}
