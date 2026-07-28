/**
 * Libellés français de l'interface, centralisés.
 *
 * POURQUOI un objet const plutôt qu'une bibliothèque i18n : le produit est
 * francophone en v1 ; tout regrouper ici rend une traduction future
 * triviale sans payer une dépendance au runtime.
 *
 * Ton : grand public. Aucun jargon interne, aucun nom de variable, chaque
 * écran se comprend sans explication.
 */
/**
 * Noms français des types d'analyse.
 *
 * POURQUOI ici et pas côté serveur : le registre est alimenté par la
 * configuration d'entraînement, en anglais, et il sert aussi à des outils
 * techniques. Traduire au niveau de l'API imposerait le français à tout le
 * monde ; traduire ici garde le serveur neutre. Un identifiant absent de
 * cette table retombe sur le libellé d'origine — un nouveau modèle
 * s'affichera donc en anglais plutôt que de ne pas s'afficher du tout.
 */
export const NOMS_ANALYSES: Record<string, string> = {
  chest_xray: 'Radiographie thoracique — pneumonie',
  brain_mri: 'IRM cérébrale — type de tumeur',
  brain_tumor_segmentation: 'IRM cérébrale — délimitation de tumeur',
  chest_xray_segmentation: 'Radiographie thoracique — délimitation des poumons',
};

/**
 * Noms français des catégories prédites par les modèles.
 *
 * Même raison que pour les types d'analyse : les étiquettes viennent des
 * jeux de données, en anglais. Les traduire à l'affichage évite qu'une
 * interface française annonce « PNEUMONIA » ou « notumor » à quelqu'un qui
 * découvre le sujet.
 */
const NOMS_CLASSES: Record<string, string> = {
  normal: 'Normal',
  abnormal: 'Anormal',
  pneumonia: 'Pneumonie',
  glioma: 'Gliome',
  meningioma: 'Méningiome',
  notumor: 'Pas de tumeur',
  no_tumor: 'Pas de tumeur',
  // Les deux graphies coexistent selon le jeu de données : « pituitary »
  // pour la classification, « pituitary tumor » pour la segmentation.
  pituitary: 'Adénome hypophysaire',
  'pituitary tumor': 'Adénome hypophysaire',
  tumor: 'Tumeur',
  background: 'Fond',
};

/**
 * Traduit une catégorie prédite.
 *
 * @param classe Étiquette telle que renvoyée par l'API (casse quelconque).
 * @returns Le nom français, ou l'étiquette d'origine si elle est inconnue —
 *   un nouveau modèle affichera donc son étiquette brute plutôt que rien.
 * @example nomClasse('PNEUMONIA') // "Pneumonie"
 */
export function nomClasse(classe: string): string {
  return NOMS_CLASSES[classe.trim().toLowerCase()] ?? classe;
}

export const FR = {
  app: {
    titre: 'MedVision AI',
    sousTitre: 'Analyse d’images médicales assistée par intelligence artificielle',
    disclaimer:
      'Démonstrateur pédagogique — ne remplace en aucun cas un avis médical professionnel.',
    tempsReel: 'Temps réel',
    connecte: 'connecté',
    // « connexion… » à la première tentative, « reconnexion… » seulement après
    // une coupure : annoncer d'emblée une reconnexion laisse croire à un
    // incident alors que la page vient simplement de s'ouvrir.
    connexion: 'connexion…',
    reconnexion: 'reconnexion…',
    nouveauxModeles: 'De nouveaux modèles viennent d’arriver',
    theme: 'Changer de thème',
  },
  nav: {
    accueil: 'Accueil',
    studio: 'Analyser une image',
    comparaison: 'Comparer les modèles',
  },
  accueil: {
    // Accroche : on dit ce qu'on fait ET ce qu'on ne fait pas, dès la
    // première phrase. Sur un sujet médical, la franchise inspire plus
    // confiance qu'une promesse enthousiaste.
    accroche: 'Voir ce que les images ont à dire',
    intro:
      'Déposez une radiographie ou une IRM, et laissez plusieurs modèles d’intelligence artificielle vous donner leur lecture — côte à côte, avec leur degré de certitude. Un outil pour apprendre et comparer, jamais pour décider seul.',
    etapes: [
      {
        titre: 'Choisissez une image',
        texte: 'La vôtre, ou l’un des centaines d’exemples déjà à disposition.',
      },
      {
        titre: 'Interrogez plusieurs modèles',
        texte: 'Ils travaillent sur la même image, en une seule fois.',
      },
      {
        titre: 'Comparez leurs lectures',
        texte: 'Prédictions, degrés de certitude, zones délimitées.',
      },
    ],
    titre: 'Que souhaitez-vous analyser ?',
    sousTitre: 'Quatre types d’analyse, entraînés sur des jeux de données publics.',
    modelesPrets: 'modèles prêts',
    sur: 'sur',
    categories: 'catégories reconnues',
    // Court exprès : sur deux lignes, une pastille fait négligé. Le titre de
    // la carte dit déjà qu'il s'agit d'une délimitation.
    zonesSeules: 'Sans diagnostic',
    analyser: 'Analyser une image',
    comparer: 'Comparer',
    aucunModele: 'Aucun modèle disponible pour l’instant.',
    aucunModelePret: 'Aucun modèle prêt pour cette analyse',
    confiance:
      'Les résultats affichés proviennent de modèles entraînés sur des jeux de données publics. Ils illustrent une démarche ; ils n’ont aucune valeur clinique.',
  },
  studio: {
    titre: 'Analyser une image',
    intro:
      'Trois étapes : le type d’analyse, l’image, puis les modèles à interroger. Ils travaillent tous sur la même image et vous rendent leur lecture côte à côte.',
    choisirProbleme: 'Type d’analyse',
    source: 'Image à analyser',
    deposer: 'Déposer une image',
    deposerAide: 'Glissez une image ici, ou cliquez pour parcourir',
    banque: 'Banque d’exemples',
    recherche: 'Rechercher un exemple…',
    toutes: 'Toutes',
    aucuneImage: 'Aucune image ne correspond à ces filtres.',
    modeles: 'Modèles à interroger',
    toutSelectionner: 'Tout sélectionner',
    toutDeselectionner: 'Tout désélectionner',
    analyser: 'Lancer l’analyse',
    enCours: 'Analyse en cours…',
    resultats: 'Résultats',
    prediction: 'Prédiction',
    confiance: 'Confiance',
    probabilites: 'Probabilités par catégorie',
    zones: 'Zones détectées',
    surface: 'Surface détectée',
    seuil: 'Sensibilité',
    opacite: 'Opacité',
    vueSuperposition: 'Superposition',
    vueMasque: 'Masque',
    vueProbabilite: 'Probabilités',
    pasDeDiagnostic:
      'Cet écran délimite des zones ; il ne pose pas de diagnostic. Pour une prédiction, choisissez un type d’analyse par classification.',
    page: 'Page',
    sur: 'sur',
  },
  comparaison: {
    titre: 'Comparer les modèles',
    sousTitre: 'Les performances mesurées de chaque modèle, côte à côte.',
    modele: 'Modèle',
    etat: 'État',
    pret: 'Prêt',
    absent: 'Absent',
    taille: 'Taille',
    maj: 'Mis à jour',
    aucuneMesure: 'Aucune mesure disponible pour ce type d’analyse.',
  },
  erreurs: {
    chargement: 'Impossible de charger les données. Nouvelle tentative…',
    analyse: 'L’analyse a échoué.',
  },
} as const;
