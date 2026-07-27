/**
 * Tests de l'écran de comparaison.
 *
 * Le piège qu'on verrouille ici : une métrique ABSENTE n'est pas une
 * métrique NULLE. Les rapports d'entraînement ne sont pas toujours tirés sur
 * le pod ; si on traitait l'absence comme un zéro, un très bon modèle
 * paraîtrait mauvais et finirait en bas du classement. Il doit afficher un
 * tiret et se ranger en fin de liste, quel que soit le sens du tri.
 */
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ComparaisonService } from '../../core/api/comparaison.service';
import { RegistreService } from '../../core/api/registre.service';
import { RegistreStore } from '../../core/state/registre.store';
import { ComparaisonComponent } from './comparaison.component';
import type { ComparaisonReponse, RegistreReponse } from '../../core/api/api.types';

const REGISTRE: RegistreReponse = {
  version: 'v1',
  problems: {
    chest: {
      label: 'Radiographie thoracique',
      task_type: 'binary',
      class_names: ['NORMAL', 'PNEUMONIA'],
      models: {
        alpha: {
          available: true,
          framework: 'tf',
          metrics: {},
          report_available: true,
          size_bytes: 12 * 1024 * 1024,
          modified_at: '2026-07-18T10:30:00+00:00',
        },
        beta: {
          available: true,
          framework: 'tf',
          metrics: {},
          report_available: true,
          size_bytes: 8 * 1024 * 1024,
          modified_at: '2026-07-17T09:00:00+00:00',
        },
        sansMesure: {
          available: true,
          framework: 'tf',
          metrics: {},
          report_available: false,
          size_bytes: 5 * 1024 * 1024,
          modified_at: null,
        },
      },
    },
  },
};

const COMPARAISON: ComparaisonReponse = {
  problem: 'chest',
  version: 'v1',
  rows: [
    { model_name: 'alpha', available: true, accuracy: 0.91, f1: 0.88 },
    { model_name: 'beta', available: true, accuracy: 0.95, f1: 0.93 },
    // Ce modèle n'a AUCUNE mesure : le rapport n'est pas sur le pod.
    { model_name: 'sansMesure', available: true },
  ],
};

class RegistreFactice {
  lire(): Promise<RegistreReponse> {
    return Promise.resolve(REGISTRE);
  }
  lireVersion(): Promise<{ version: string; refreshed_at: string | null }> {
    return Promise.resolve({ version: 'v1', refreshed_at: null });
  }
}

class ComparaisonFactice {
  lire(): Promise<ComparaisonReponse> {
    return Promise.resolve(COMPARAISON);
  }
}

describe('ComparaisonComponent', () => {
  async function monter() {
    TestBed.configureTestingModule({
      imports: [ComparaisonComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: RegistreService, useClass: RegistreFactice },
        { provide: ComparaisonService, useClass: ComparaisonFactice },
      ],
    });
    await TestBed.inject(RegistreStore).recharger();
    const fixture = TestBed.createComponent(ComparaisonComponent);
    fixture.detectChanges();
    // Laisse la promesse du chargement des mesures se résoudre.
    await Promise.resolve();
    fixture.detectChanges();
    return fixture;
  }

  it('ne retient comme colonnes que les mesures réellement présentes', async () => {
    const composant = (await monter()).componentInstance;
    expect(composant.colonnesMetriques()).toEqual(['accuracy', 'f1']);
    expect(composant.aucuneMesure()).toBeFalse();
  });

  it('trie du meilleur au moins bon au premier clic sur une mesure', async () => {
    const composant = (await monter()).componentInstance;

    composant.trierPar('accuracy');

    expect(composant.sensTri()).toBe('desc');
    expect(composant.lignes().map((l) => l.modele)).toEqual(['beta', 'alpha', 'sansMesure']);
  });

  it('garde le modèle sans mesure en fin de liste même en tri croissant', async () => {
    const composant = (await monter()).componentInstance;

    composant.trierPar('accuracy'); // décroissant
    composant.trierPar('accuracy'); // recliquer inverse → croissant

    expect(composant.sensTri()).toBe('asc');
    const ordre = composant.lignes().map((l) => l.modele);
    expect(ordre[ordre.length - 1]).toBe('sansMesure');
    expect(ordre[0]).toBe('alpha');
  });

  it('affiche un tiret, jamais un zéro, pour une mesure absente', async () => {
    const composant = (await monter()).componentInstance;
    const ligne = composant.lignes().find((l) => l.modele === 'sansMesure')!;

    expect(composant.formaterMetrique(ligne, 'accuracy')).toBe('—');
    expect(composant.formaterTaille(ligne)).toBe('5.0 Mo');
  });

  it('annonce l’état de tri aux lecteurs d’écran', async () => {
    const composant = (await monter()).componentInstance;

    expect(composant.ariaTri('accuracy')).toBe('none');
    composant.trierPar('accuracy');
    expect(composant.ariaTri('accuracy')).toBe('descending');
    expect(composant.ariaTri('f1')).toBe('none');
    composant.trierPar('accuracy');
    expect(composant.ariaTri('accuracy')).toBe('ascending');
  });

  it('signale qu’une colonne est triable avant tout clic', async () => {
    const composant = (await monter()).componentInstance;
    // Flèche double sur les colonnes non triées : sans elle, rien n'indique
    // qu'on peut cliquer.
    expect(composant.flecheTri('f1')).toBe('↕');
    composant.trierPar('f1');
    expect(composant.flecheTri('f1')).toBe('▼');
  });

  it('met la date de mise à jour en forme courte', async () => {
    const composant = (await monter()).componentInstance;
    const ligne = composant.lignes().find((l) => l.modele === 'alpha')!;
    expect(ligne.misAJour).toBe('2026-07-18');
  });
});
