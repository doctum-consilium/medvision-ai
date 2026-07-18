/**
 * Types miroir des réponses de l'API MedVision (préfixe /api).
 *
 * Ils reflètent exactement ce que renvoient les routes FastAPI de
 * `src/api/routes/` — toute évolution de schéma côté serveur doit être
 * répercutée ici (le `ng build` en mode strict fera échouer la CI si un
 * champ manque à l'appel).
 */

/** Un type d'analyse proposé à l'utilisateur (carte d'accueil). */
export interface Probleme {
  id: string;
  label: string;
  /** 'binary' | 'multiclass' → diagnostic ; 'segmentation' → zones seules. */
  task_type: 'binary' | 'multiclass' | 'segmentation';
  class_names: string[];
  models_total: number;
  models_available: number;
}

/** Un modèle du registre, enrichi de sa taille et de sa date de mise à jour. */
export interface Modele {
  available: boolean;
  framework: string;
  metrics: Record<string, number | string>;
  report_available: boolean;
  size_bytes: number | null;
  modified_at: string | null;
}

export interface ProblemeAvecModeles {
  label: string;
  task_type: Probleme['task_type'];
  class_names: string[];
  models: Record<string, Modele>;
}

export interface RegistreReponse {
  /** Change dès qu'un fichier de modèle apparaît, change ou disparaît. */
  version: string;
  problems: Record<string, ProblemeAvecModeles>;
}

/** Un échantillon de la banque d'exemples — jamais un chemin disque. */
export interface Echantillon {
  sample_id: string;
  label: string;
  display: string;
}

export interface ImagesReponse {
  total: number;
  page: number;
  page_size: number;
  recommended: Echantillon[];
  items: Echantillon[];
}

/** Bloc segmentation : le masque revient en probabilités, pas binarisé. */
export interface Segmentation {
  /** PNG base64 en niveaux de gris — re-seuillé côté client, sans ré-inférence. */
  mask_prob_png: string;
  /** PNG base64 de l'image telle que vue par le modèle. */
  preprocessed_png: string;
  mask_foreground_ratio: number;
  prob_mean: number;
  prob_max: number;
  prob_min: number;
  threshold: number;
}

/**
 * Résultat pour UN modèle. Les champs de classification sont absents sur
 * les analyses de segmentation pure, et `error` remplace tout le reste
 * quand ce modèle précis a échoué (les autres restent exploitables).
 */
export interface ResultatModele {
  model_name: string;
  predicted_class?: string;
  confidence?: number;
  probabilities?: Record<string, number>;
  metrics?: Record<string, number | string>;
  segmentation?: Segmentation;
  error?: string;
}

export interface PredictionReponse {
  problem: string;
  image: { source: 'upload' | 'dataset'; sample_id?: string };
  results: ResultatModele[];
}

export interface LigneComparaison {
  model_name: string;
  available: boolean;
  [metrique: string]: number | string | boolean;
}

export interface ComparaisonReponse {
  problem: string;
  version: string;
  rows: LigneComparaison[];
}
