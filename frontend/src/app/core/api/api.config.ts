/**
 * Adresse de base de l'API MedVision.
 *
 * POURQUOI un chemin relatif et non une URL absolue : en production le
 * navigateur parle à nginx, qui proxifie `/api` vers le service
 * `medvision-api:8000` du cluster. En développement, le proxy du serveur
 * `ng serve` (frontend/proxy.conf.json) fait la même chose vers l'API
 * distante. Dans les deux cas le front n'a donc RIEN à savoir de l'hôte
 * de l'API — pas de fichier d'environnement à maintenir, pas de CORS à
 * configurer, et une image Docker identique quel que soit le domaine.
 */
export const API_BASE = '/api';
