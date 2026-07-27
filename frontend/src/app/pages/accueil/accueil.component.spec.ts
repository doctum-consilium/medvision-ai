/**
 * Tests de l'écran d'accueil.
 *
 * Deux choses valent d'être verrouillées ici. D'abord la franchise : la page
 * doit dire d'emblée que l'outil ne remplace pas un avis médical, et signaler
 * les analyses qui délimitent des zones sans poser de diagnostic. Ensuite la
 * lisibilité des compteurs : un modèle déclaré mais absent du disque ne doit
 * jamais être compté comme prêt.
 */
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AccueilComponent } from './accueil.component';
import { RegistreService } from '../../core/api/registre.service';
import { RegistreStore } from '../../core/state/registre.store';
import type { RegistreReponse } from '../../core/api/api.types';

function modele(disponible: boolean) {
  return {
    available: disponible,
    framework: 'tf',
    metrics: {},
    report_available: false,
    size_bytes: disponible ? 1 : null,
    modified_at: null,
  };
}

const REGISTRE: RegistreReponse = {
  version: 'v1',
  problems: {
    chest_xray: {
      label: 'Radiographie thoracique',
      task_type: 'binary',
      class_names: ['NORMAL', 'PNEUMONIA'],
      // Deux prêts sur trois : le troisième est déclaré mais absent du disque.
      models: { a: modele(true), b: modele(true), c: modele(false) },
    },
    brain_mri: {
      label: 'IRM cérébrale',
      task_type: 'multiclass',
      class_names: ['glioma', 'meningioma', 'notumor', 'pituitary'],
      models: { a: modele(true) },
    },
    brain_tumor_segmentation: {
      label: 'Segmentation cérébrale',
      task_type: 'segmentation',
      class_names: [],
      models: { unet: modele(true) },
    },
  },
};

class RegistreFactice {
  lire(): Promise<RegistreReponse> {
    return Promise.resolve(REGISTRE);
  }
  lireVersion(): Promise<{ version: string; refreshed_at: string | null }> {
    return Promise.resolve({ version: 'v1', refreshed_at: null });
  }
}

describe('AccueilComponent', () => {
  async function monter() {
    TestBed.configureTestingModule({
      imports: [AccueilComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: RegistreService, useClass: RegistreFactice },
      ],
    });
    await TestBed.inject(RegistreStore).recharger();
    const fixture = TestBed.createComponent(AccueilComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('annonce d’emblée que l’outil ne décide pas à la place du praticien', async () => {
    const fixture = await monter();
    const texte = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texte).toContain('jamais pour décider seul');
  });

  it('signale les analyses qui délimitent des zones sans diagnostic', async () => {
    const fixture = await monter();
    const texte = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texte).toContain(fixture.componentInstance.fr.accueil.zonesSeules);
  });

  it('ne compte comme prêts que les modèles réellement présents', async () => {
    const fixture = await monter();
    const composant = fixture.componentInstance;
    const chest = composant.store.cartes().find((c) => c.id === 'chest_xray')!;

    expect(chest.modelesDisponibles).toBe(2);
    expect(chest.modelesTotal).toBe(3);
    expect(composant.partPrete(chest)).toBeCloseTo(66.67, 1);
    expect(composant.store.totalDisponibles()).toBe(4);
  });

  it('choisit une illustration cohérente avec le type d’analyse', async () => {
    const composant = (await monter()).componentInstance;
    const par = (id: string) => composant.store.cartes().find((c) => c.id === id)!;

    expect(composant.illustration(par('chest_xray'))).toBe('thorax');
    expect(composant.illustration(par('brain_mri'))).toBe('cerveau');
    // La segmentation prime sur l'organe : c'est ce qu'elle fait qui compte.
    expect(composant.illustration(par('brain_tumor_segmentation'))).toBe('zones');
  });

  it('ne propose pas d’analyser un type sans aucun modèle prêt', async () => {
    const composant = (await monter()).componentInstance;
    expect(composant.partPrete({ ...composant.store.cartes()[0], modelesTotal: 0 })).toBe(0);
  });
});
