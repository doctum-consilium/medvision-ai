/**
 * Tests de l'écran d'analyse.
 *
 * Le test central est celui de la SEGMENTATION : ces modèles délimitent des
 * zones et ne posent aucun diagnostic. Leur tête de classification annonçait
 * « NORMAL » avec une confiance de 1,000 sur des pneumonies manifestes — si
 * un jour ce chiffre réapparaît à l'écran, ce test doit tomber. C'est sa
 * seule raison d'être, et elle est médicale, pas cosmétique.
 */
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ImagesService } from '../../core/api/images.service';
import { RegistreService } from '../../core/api/registre.service';
import { RegistreStore } from '../../core/state/registre.store';
import { StudioComponent } from './studio.component';
import type { RegistreReponse, ResultatModele } from '../../core/api/api.types';

const REGISTRE: RegistreReponse = {
  version: 'v1',
  problems: {
    chest: {
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

/**
 * Résultat piégeux : le modèle de segmentation renvoie AUSSI une classe et
 * une confiance parfaite. L'interface doit les ignorer.
 */
const RESULTAT_SEGMENTATION: ResultatModele = {
  model_name: 'unet',
  predicted_class: 'NORMAL',
  confidence: 1,
  probabilities: { NORMAL: 1, PNEUMONIA: 0 },
  segmentation: {
    // PNG 1×1 valide, suffisant : on teste l'affichage, pas le rendu.
    mask_prob_png:
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGP4DwABAQEAJzhkoAAAAABJRU5ErkJggg==',
    preprocessed_png:
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGP4DwABAQEAJzhkoAAAAABJRU5ErkJggg==',
    mask_foreground_ratio: 0.1234,
    prob_mean: 0.4,
    prob_max: 0.9,
    prob_min: 0,
    threshold: 0.5,
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

class ImagesFactice {
  lister(): Promise<never> {
    // Banque indisponible : l'écran doit rester utilisable (dépôt manuel).
    return Promise.reject(new Error('pas de dataset monté'));
  }
  urlFichier(): string {
    return '';
  }
}

describe('StudioComponent', () => {
  async function monter() {
    TestBed.configureTestingModule({
      imports: [StudioComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: RegistreService, useClass: RegistreFactice },
        { provide: ImagesService, useClass: ImagesFactice },
      ],
    });
    await TestBed.inject(RegistreStore).recharger();
    const fixture = TestBed.createComponent(StudioComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('présélectionne le premier type d’analyse et ses modèles disponibles', async () => {
    const fixture = await monter();
    const composant = fixture.componentInstance;
    expect(composant.problemeId()).toBe('chest');
    expect([...composant.modelesChoisis()]).toEqual(['resnet']);
  });

  it('n’affiche NI prédiction NI confiance sur une analyse de segmentation', async () => {
    const fixture = await monter();
    const composant = fixture.componentInstance;

    composant.choisirProbleme('brain_seg');
    composant.resultats.set([RESULTAT_SEGMENTATION]);
    fixture.detectChanges();

    const texte = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(composant.estSegmentation()).toBeTrue();
    expect(texte).not.toContain(composant.fr.studio.prediction + ' :');
    expect(texte).not.toContain(composant.fr.studio.confiance + ' :');
    expect(texte).not.toContain('NORMAL');
    // Ce qu'on doit voir à la place : la surface, et la phrase de renvoi.
    expect(texte).toContain('12.3 %');
    expect(texte).toContain(composant.fr.studio.pasDeDiagnostic);
  });

  it('affiche prédiction et confiance sur une analyse par classification', async () => {
    const fixture = await monter();
    const composant = fixture.componentInstance;

    composant.resultats.set([
      { model_name: 'resnet', predicted_class: 'PNEUMONIA', confidence: 0.87 },
    ]);
    fixture.detectChanges();

    const texte = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texte).toContain('PNEUMONIA');
    expect(texte).toContain('87.0 %');
  });

  it('isole l’erreur d’un modèle sans masquer les autres résultats', async () => {
    const fixture = await monter();
    const composant = fixture.componentInstance;

    composant.resultats.set([
      { model_name: 'casse', error: 'Modèle indisponible' },
      { model_name: 'resnet', predicted_class: 'NORMAL', confidence: 0.6 },
    ]);
    fixture.detectChanges();

    const texte = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texte).toContain('Modèle indisponible');
    expect(texte).toContain('NORMAL');
  });

  it('refuse de lancer une analyse tant qu’aucune image n’est fournie', async () => {
    const fixture = await monter();
    expect(fixture.componentInstance.peutAnalyser()).toBeFalse();
  });
});
