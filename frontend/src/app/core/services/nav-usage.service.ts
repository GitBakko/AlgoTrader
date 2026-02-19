import { Injectable, inject, signal, computed, DestroyRef } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';
import { navItems } from '../../layout/default-layout/_nav';

export interface NavLink {
  name: string;
  url: string;
  icon: string;
}

const STORAGE_KEY = 'mantis-nav-usage';
const TOP_COUNT = 3;

/** Routes excluded from tracking (not real navigable pages). */
const EXCLUDED_ROUTES = new Set([
  '/dashboard',  // Always pinned, don't track
  '/login',
  '/register',
  '/profile',
  '/404',
  '/403',
  '/500',
]);

/** All trackable nav items from sidebar definition. */
const NAV_LOOKUP = new Map<string, NavLink>(
  navItems
    .filter((item): item is typeof item & { url: string } =>
      typeof item.url === 'string' && !item.title)
    .map(item => [
      item.url,
      { name: item.name!, url: item.url, icon: item.iconComponent?.name ?? '' },
    ] as const)
);

/** Default links when no usage data exists. */
const DEFAULTS: NavLink[] = [
  NAV_LOOKUP.get('/positions')!,
  NAV_LOOKUP.get('/signals')!,
  NAV_LOOKUP.get('/news')!,
];

@Injectable({ providedIn: 'root' })
export class NavUsageService {
  readonly #router = inject(Router);
  readonly #destroyRef = inject(DestroyRef);
  readonly #counts = signal<Record<string, number>>(this.#load());

  readonly topLinks = computed<NavLink[]>(() => {
    const counts = this.#counts();
    const entries = Object.entries(counts)
      .filter(([url]) => NAV_LOOKUP.has(url))
      .sort((a, b) => b[1] - a[1])
      .slice(0, TOP_COUNT);

    if (entries.length === 0) {
      return DEFAULTS;
    }

    const links = entries.map(([url]) => NAV_LOOKUP.get(url)!);

    // Pad with defaults if fewer than 3 tracked pages
    if (links.length < TOP_COUNT) {
      for (const d of DEFAULTS) {
        if (links.length >= TOP_COUNT) break;
        if (!links.some(l => l.url === d.url)) {
          links.push(d);
        }
      }
    }

    return links;
  });

  constructor() {
    this.#router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed(this.#destroyRef),
      )
      .subscribe(e => this.#trackVisit(e.urlAfterRedirects ?? e.url));
  }

  #trackVisit(rawUrl: string): void {
    // Strip query params and fragment
    const url = rawUrl.split('?')[0].split('#')[0];

    if (EXCLUDED_ROUTES.has(url) || !NAV_LOOKUP.has(url)) return;

    const counts = { ...this.#counts() };
    counts[url] = (counts[url] ?? 0) + 1;
    this.#counts.set(counts);
    this.#save(counts);
  }

  #load(): Record<string, number> {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  #save(counts: Record<string, number>): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(counts));
    } catch { /* storage full — silently ignore */ }
  }
}
