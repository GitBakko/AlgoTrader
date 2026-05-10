/**
 * News and sentiment service.
 * Provides access to news articles, insider sentiment, and analyst data.
 *
 * H4-FE-AUDIT / H1-CORE: migrated from raw HttpClient to ApiService so
 * the response envelope is unwrapped centrally and the request goes
 * through the same interceptor pipeline as every other API caller.
 */

import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap, catchError, of, map } from 'rxjs';
import { NewsArticle, InsiderSentiment, AnalystConsensus, SentimentSummary } from '../models/news.model';
import { ApiService } from './api.service';

@Injectable({
  providedIn: 'root'
})
export class NewsService {
  private readonly api = inject(ApiService);

  // Signals for reactive state
  readonly news = signal<NewsArticle[]>([]);
  readonly insiderSentiment = signal<InsiderSentiment | null>(null);
  readonly analystConsensus = signal<AnalystConsensus | null>(null);
  readonly sentimentScore = signal<number>(0);
  readonly isLoading = signal<boolean>(false);
  readonly error = signal<string | null>(null);

  /**
   * Get news articles with sentiment for an asset.
   */
  getNews(epic: string, limit: number = 20, days: number = 7): void {
    this.isLoading.set(true);
    this.error.set(null);

    this.api.get<NewsArticle[]>(`/api/news/${epic}`, { limit, days })
      .pipe(
        tap(data => this.news.set(data ?? [])),
        catchError(() => {
          this.error.set('Failed to fetch news');
          this.news.set([]);
          return of([] as NewsArticle[]);
        })
      )
      // M1-CORE: explicit error/next callbacks so isLoading always clears.
      .subscribe({
        next: () => this.isLoading.set(false),
        error: () => this.isLoading.set(false),
      });
  }

  /**
   * Get insider sentiment (MSPR) for a stock.
   */
  getInsiderSentiment(epic: string, startDate?: string, endDate?: string): void {
    const params: Record<string, string | number> = {};
    if (startDate) params['start_date'] = startDate;
    if (endDate) params['end_date'] = endDate;

    this.api.get<InsiderSentiment>(`/api/news/insider/${epic}`, params)
      .pipe(
        tap(data => this.insiderSentiment.set(data ?? null)),
        catchError(() => {
          this.insiderSentiment.set(null);
          return of(null);
        })
      )
      .subscribe();
  }

  /**
   * Get aggregated sentiment score for an asset.
   */
  getSentiment(epic: string, days: number = 7): Observable<number> {
    return this.api.get<SentimentSummary>(`/api/news/sentiment/${epic}`, { days })
      .pipe(
        map(data => {
          const sentiment = data?.sentiment ?? 0;
          this.sentimentScore.set(sentiment);
          return sentiment;
        }),
        catchError(() => {
          this.sentimentScore.set(0);
          return of(0);
        })
      );
  }

  /**
   * Clear all data (useful when switching assets).
   */
  clearData(): void {
    this.news.set([]);
    this.insiderSentiment.set(null);
    this.analystConsensus.set(null);
    this.sentimentScore.set(0);
    this.error.set(null);
  }
}
