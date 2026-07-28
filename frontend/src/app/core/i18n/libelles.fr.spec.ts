/**
 * Tests de la traduction des étiquettes.
 *
 * Les jeux de données n'emploient pas les mêmes graphies d'un problème à
 * l'autre — « pituitary » pour la classification, « pituitary tumor » pour la
 * segmentation. Une étiquette non traduite ressort telle quelle à l'écran, en
 * anglais et en minuscules, au milieu d'une interface française : c'est
 * exactement ce que ces tests empêchent de laisser passer.
 */
import { nomClasse } from './libelles.fr';

describe('nomClasse', () => {
  it('traduit les catégories des quatre types d’analyse', () => {
    // Étiquettes relevées sur l'API de production.
    expect(nomClasse('NORMAL')).toBe('Normal');
    expect(nomClasse('PNEUMONIA')).toBe('Pneumonie');
    expect(nomClasse('ABNORMAL')).toBe('Anormal');
    expect(nomClasse('glioma')).toBe('Gliome');
    expect(nomClasse('meningioma')).toBe('Méningiome');
    expect(nomClasse('notumor')).toBe('Pas de tumeur');
  });

  it('traduit les deux graphies de l’adénome hypophysaire', () => {
    expect(nomClasse('pituitary')).toBe('Adénome hypophysaire');
    expect(nomClasse('pituitary tumor')).toBe('Adénome hypophysaire');
  });

  it('ignore la casse et les espaces superflus', () => {
    expect(nomClasse('  Glioma  ')).toBe('Gliome');
  });

  it('rend l’étiquette d’origine si elle est inconnue', () => {
    // Un modèle nouveau doit s'afficher, même sans traduction.
    expect(nomClasse('cardiomegaly')).toBe('cardiomegaly');
  });
});
