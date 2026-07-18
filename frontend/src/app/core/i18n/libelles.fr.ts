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
export const FR = {
  app: {
    titre: 'MedVision AI',
    sousTitre: 'Analyse d’images médicales assistée par intelligence artificielle',
    disclaimer:
      'Démonstrateur pédagogique — ne remplace en aucun cas un avis médical professionnel.',
    tempsReel: 'Temps réel',
    connecte: 'connecté',
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
    titre: 'Que souhaitez-vous analyser ?',
    modelesPrets: 'modèles prêts',
    sur: 'sur',
    categories: 'catégories reconnues',
    zonesSeules: 'Délimite des zones (pas de diagnostic)',
    analyser: 'Analyser',
    comparer: 'Comparer',
    aucunModele: 'Aucun modèle disponible pour l’instant.',
  },
  studio: {
    titre: 'Analyser une image',
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
