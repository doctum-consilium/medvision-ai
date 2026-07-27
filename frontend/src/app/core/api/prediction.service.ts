/**
 * Lancement d'une analyse (`POST /api/predict`).
 *
 * POURQUOI une seule requête pour N modèles : le studio compare plusieurs
 * modèles sur la MÊME image. Un appel unique = un seul envoi de l'image et un
 * seul prétraitement côté serveur, là où N appels feraient N fois le travail
 * sur un pod à 2 Gi de mémoire.
 *
 * Les erreurs sont rapportées PAR MODÈLE (champ `error` de chaque résultat) :
 * un fichier ONNX manquant ne doit pas faire échouer toute la comparaison.
 */
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { API_BASE } from './api.config';
import type { PredictionReponse } from './api.types';

/**
 * Demande d'analyse. L'image vient SOIT d'un dépôt de fichier, SOIT de la
 * banque d'exemples — jamais des deux (l'API rejette le cas ambigu en 400).
 */
export interface DemandeAnalyse {
  probleme: string;
  modeles: string[];
  fichier?: File;
  sampleId?: string;
  /**
   * Seuil initial de binarisation du masque de segmentation. Il n'est
   * qu'indicatif : le masque revient en probabilités, et le curseur de
   * sensibilité de l'interface re-seuille côté navigateur sans rappeler
   * le serveur.
   */
  seuilMasque?: number;
}

@Injectable({ providedIn: 'root' })
export class PredictionService {
  private readonly http = inject(HttpClient);

  /**
   * Analyse une image avec les modèles demandés.
   *
   * @param demande Type d'analyse, modèles, et source de l'image.
   * @returns Un résultat par modèle, dans l'ordre demandé.
   * @throws Error Si ni fichier ni exemple n'est fourni (ou les deux).
   * @throws HttpErrorResponse 404 si le type d'analyse ou l'exemple est inconnu.
   */
  analyser(demande: DemandeAnalyse): Promise<PredictionReponse> {
    const aFichier = demande.fichier !== undefined;
    const aExemple = demande.sampleId !== undefined;
    if (aFichier === aExemple) {
      throw new Error('Fournir soit une image déposée, soit un exemple — pas les deux.');
    }

    const form = new FormData();
    form.append('problem', demande.probleme);
    // `model_names` est un champ RÉPÉTÉ côté FastAPI (list[str] = Form(...)),
    // pas une liste sérialisée : une entrée par modèle.
    for (const modele of demande.modeles) {
      form.append('model_names', modele);
    }
    form.append('mask_threshold', String(demande.seuilMasque ?? 0.5));
    if (demande.fichier) {
      form.append('file', demande.fichier, demande.fichier.name);
    }
    if (demande.sampleId) {
      form.append('sample_id', demande.sampleId);
    }

    return firstValueFrom(this.http.post<PredictionReponse>(`${API_BASE}/predict`, form));
  }
}
