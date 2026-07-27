/**
 * Banque d'exemples (`GET /api/images`, `GET /api/images/{id}/file`).
 *
 * POURQUOI des identifiants opaques plutôt que des chemins de fichiers :
 * l'API n'expose jamais l'arborescence disque du pod, et n'interprète jamais
 * un chemin fourni par le navigateur — c'est ce qui rend impossible la
 * remontée d'arborescence (`../../etc/passwd`). Le front manipule donc des
 * `sample_id` et rien d'autre.
 */
import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { API_BASE } from './api.config';
import type { ImagesReponse } from './api.types';

/** Critères de recherche dans la banque d'exemples. */
export interface FiltreImages {
  probleme: string;
  /** Classes retenues ; vide = toutes. */
  labels?: string[];
  /** Recherche libre sur l'identifiant ou la classe. */
  recherche?: string;
  page?: number;
  taillePage?: number;
}

@Injectable({ providedIn: 'root' })
export class ImagesService {
  private readonly http = inject(HttpClient);

  /**
   * Liste paginée des exemples d'un type d'analyse.
   *
   * @param filtre Type d'analyse, filtres de classe, recherche et pagination.
   * @returns Le total, la page demandée et jusqu'à quatre exemples « recommandés ».
   * @throws HttpErrorResponse 404 si le type d'analyse est inconnu.
   */
  lister(filtre: FiltreImages): Promise<ImagesReponse> {
    let params = new HttpParams().set('problem', filtre.probleme);
    if (filtre.labels?.length) {
      params = params.set('labels', filtre.labels.join(','));
    }
    if (filtre.recherche) {
      params = params.set('q', filtre.recherche);
    }
    params = params
      .set('page', String(filtre.page ?? 1))
      .set('page_size', String(filtre.taillePage ?? 12));

    return firstValueFrom(this.http.get<ImagesReponse>(`${API_BASE}/images`, { params }));
  }

  /**
   * Construit l'URL de l'image d'un exemple.
   *
   * On renvoie une URL (et non les octets) pour laisser le navigateur gérer
   * le cache et le chargement paresseux des vignettes — c'est lui qui fait ça
   * le mieux, et l'API pose déjà une heure de cache.
   *
   * @param probleme Type d'analyse (les index sont tenus par problème).
   * @param sampleId Identifiant opaque de l'exemple.
   * @param vignette True pour la vignette 256 px, false pour la pleine taille.
   * @returns L'URL à placer dans un `src`.
   * @example
   * <img [src]="images.urlFichier('chest_xray_pneumonia', s.sample_id)" />
   */
  urlFichier(probleme: string, sampleId: string, vignette = true): string {
    const params = new URLSearchParams({ problem: probleme, thumb: String(vignette) });
    return `${API_BASE}/images/${encodeURIComponent(sampleId)}/file?${params.toString()}`;
  }
}
