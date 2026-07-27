/**
 * Tests du store du registre.
 *
 * Ce qui compte ici, c'est la FRAÎCHEUR : après une coupure du flux temps
 * réel, l'interface doit se resynchroniser si — et seulement si — quelque
 * chose a changé. Recharger à chaque reconnexion userait le pod pour rien ;
 * ne jamais recharger laisserait un écran périmé sans que personne ne le
 * sache. Les deux erreurs sont verrouillées ci-dessous.
 */
import { TestBed } from '@angular/core/testing';

import { RegistreService } from '../api/registre.service';
import { RegistreStore } from './registre.store';
import type { RegistreReponse } from '../api/api.types';

const REGISTRE: RegistreReponse = {
  version: 'v1',
  problems: {
    chest_xray_pneumonia: {
      label: 'Radiographie thoracique',
      task_type: 'binary',
      class_names: ['NORMAL', 'PNEUMONIA'],
      models: {
        resnet: {
          available: true,
          framework: 'tf',
          metrics: {},
          report_available: false,
          size_bytes: 1,
          modified_at: null,
        },
        absent: {
          available: false,
          framework: 'tf',
          metrics: {},
          report_available: false,
          size_bytes: null,
          modified_at: null,
        },
      },
    },
    brain_seg: {
      label: 'Segmentation cérébrale',
      task_type: 'segmentation',
      class_names: [],
      models: {
        unet: {
          available: true,
          framework: 'torch',
          metrics: {},
          report_available: false,
          size_bytes: 2,
          modified_at: null,
        },
      },
    },
  },
};

/** Double de l'API : compte les appels pour prouver ce qui a été économisé. */
class ApiFactice {
  version = 'v1';
  appelsLire = 0;
  appelsVersion = 0;

  lire(): Promise<RegistreReponse> {
    this.appelsLire += 1;
    return Promise.resolve({ ...REGISTRE, version: this.version });
  }

  lireVersion(): Promise<{ version: string; refreshed_at: string | null }> {
    this.appelsVersion += 1;
    return Promise.resolve({ version: this.version, refreshed_at: null });
  }
}

describe('RegistreStore', () => {
  let api: ApiFactice;
  let store: InstanceType<typeof RegistreStore>;

  beforeEach(() => {
    api = new ApiFactice();
    TestBed.configureTestingModule({
      providers: [{ provide: RegistreService, useValue: api }],
    });
    store = TestBed.inject(RegistreStore);
  });

  it('compte les modèles réellement disponibles, pas les modèles déclarés', async () => {
    await store.recharger();
    expect(store.totalDisponibles()).toBe(2);
    const chest = store.cartes().find((c) => c.id === 'chest_xray_pneumonia');
    expect(chest?.modelesDisponibles).toBe(1);
    expect(chest?.modelesTotal).toBe(2);
  });

  it('marque les analyses de segmentation comme telles', async () => {
    await store.recharger();
    expect(store.cartes().find((c) => c.id === 'brain_seg')?.estSegmentation).toBeTrue();
    expect(
      store.cartes().find((c) => c.id === 'chest_xray_pneumonia')?.estSegmentation,
    ).toBeFalse();
  });

  it('ne recharge pas le registre si la version n’a pas bougé', async () => {
    await store.recharger();
    const avant = api.appelsLire;

    const aChange = await store.resynchroniser();

    expect(aChange).toBeFalse();
    expect(api.appelsLire).toBe(avant);
    expect(api.appelsVersion).toBe(1);
  });

  it('recharge le registre quand la version a changé', async () => {
    await store.recharger();
    const avant = api.appelsLire;
    api.version = 'v2';

    const aChange = await store.resynchroniser();

    expect(aChange).toBeTrue();
    expect(api.appelsLire).toBe(avant + 1);
    expect(store.version()).toBe('v2');
  });

  it('garde les données précédentes et signale l’erreur si l’API tombe', async () => {
    await store.recharger();
    spyOn(api, 'lire').and.returnValue(Promise.reject(new Error('502')));

    await store.recharger();

    expect(store.totalDisponibles()).toBe(2);
    expect(store.erreur()).toBeTruthy();
  });
});
