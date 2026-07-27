/**
 * Tests de la coquille applicative.
 *
 * On vérifie ce qui est structurel et non négociable : l'avertissement
 * médical est toujours affiché, et la pastille de connexion reflète bien
 * l'état réel du flux (un flux coupé ne doit JAMAIS être présenté comme
 * connecté — c'est ce qui ferait croire à un écran à jour alors qu'il ne
 * l'est plus).
 */
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';

import { AppComponent } from './app.component';
import { FR } from './core/i18n/libelles.fr';
import { SseService, type EtatFlux } from './core/realtime/sse.service';

/** Double du flux temps réel : aucun EventSource réel n'est ouvert en test. */
class SseFactice {
  readonly etatInterne = signal<EtatFlux>('connexion');
  readonly etat = this.etatInterne.asReadonly();
  readonly dernierEvenement = signal(null).asReadonly();
  demarrer(): void {
    /* rien : le test pilote l'état à la main */
  }
  arreter(): void {
    /* rien */
  }
}

describe('AppComponent', () => {
  let sse: SseFactice;

  beforeEach(async () => {
    sse = new SseFactice();
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SseService, useValue: sse },
      ],
    }).compileComponents();
  });

  it('affiche en permanence l’avertissement médical', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const texte = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texte).toContain(FR.app.disclaimer);
  });

  it('annonce « reconnexion » tant que le flux n’est pas établi', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.libelleFlux()).toBe(FR.app.reconnexion);
  });

  it('annonce « connecté » dès que le flux est ouvert', () => {
    const fixture = TestBed.createComponent(AppComponent);
    sse.etatInterne.set('connecte');
    fixture.detectChanges();
    expect(fixture.componentInstance.libelleFlux()).toBe(FR.app.connecte);
  });
});
