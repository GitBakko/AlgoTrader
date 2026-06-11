/**
 * Vitest global test setup — jsdom gap-fillers.
 *
 * jsdom does not implement ResizeObserver, IntersectionObserver, matchMedia
 * or a real canvas 2D context (needed by lightweight-charts / chart.js /
 * ngx-scrollbar / CoreUI). Stub them defensively so component creation never
 * throws in the Node test environment. TestBed initialization is handled by
 * the @angular/build:unit-test builder itself.
 */
import { registerLocaleData } from '@angular/common';
import localeIt from '@angular/common/locales/it';

// Mirror app.config.ts: pipes render with the it-IT locale.
registerLocaleData(localeIt, 'it-IT');

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
(globalThis as any).ResizeObserver ??= ResizeObserverStub;

class IntersectionObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): unknown[] {
    return [];
  }
}
(globalThis as any).IntersectionObserver ??= IntersectionObserverStub;

window.matchMedia ??= ((query: string) =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  }) as MediaQueryList) as typeof window.matchMedia;

HTMLCanvasElement.prototype.getContext ??= (() =>
  null) as typeof HTMLCanvasElement.prototype.getContext;
