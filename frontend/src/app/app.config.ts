import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { routes } from './app.routes';

/**
 * Configuration de l'application.
 *
 * - `withFetch()` : le client HTTP passe par l'API `fetch` du navigateur
 *   plutôt que par XMLHttpRequest — c'est la voie recommandée depuis
 *   Angular 17, et celle qui envoie sans surprise le `FormData` contenant
 *   l'image à analyser.
 * - `withComponentInputBinding()` : les paramètres d'URL (`?probleme=…`)
 *   arrivent directement dans les entrées des composants d'écran, ce qui
 *   rendra partageable un lien vers une analyse précise.
 */
export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withFetch()),
  ],
};
