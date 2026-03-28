/**
 * News and sentiment service.
 * Provides access to news articles, insider sentiment, and analyst data.
 */

import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, tap, catchError, of, map } from 'rxjs';
import { NewsArticle, InsiderSentiment, AnalystConsensus, SentimentSummary } from '../models/news.model';
import { environment } from '../../../environments/environment';

interface ApiResponse<T> {
  success: boolean;
  data: T;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class NewsService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiUrl}/api/news`;

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

    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('days', days.toString());

    this.http.get<ApiResponse<NewsArticle[]>>(`${this.baseUrl}/${epic}`, { params })
      .pipe(
        tap(response => {
          if (response.success) {
            this.news.set(response.data);
          } else {
            this.error.set(response.error || 'Failed to fetch news');
          }
        }),
        catchError(error => {
          this.error.set('Failed to fetch news');
          this.news.set([]);
          return of({ success: false, data: [] as NewsArticle[] });
        })
      )
      .subscribe(() => this.isLoading.set(false));
  }

  /**
   * Get insider sentiment (MSPR) for a stock.
   */
  getInsiderSentiment(epic: string, startDate?: string, endDate?: string): void {
    let params = new HttpParams();
    if (startDate) params = params.set('start_date', startDate);
    if (endDate) params = params.set('end_date', endDate);

    this.http.get<ApiResponse<InsiderSentiment>>(`${this.baseUrl}/insider/${epic}`, { params })
      .pipe(
        tap(response => {
          if (response.success) {
            this.insiderSentiment.set(response.data);
          } else {
            this.insiderSentiment.set(null);
          }
        }),
        catchError(error => {
          this.insiderSentiment.set(null);
          return of({ success: false, data: null });
        })
      )
      .subscribe();
  }

  /**
   * Get aggregated sentiment score for an asset.
   */
  getSentiment(epic: string, days: number = 7): Observable<number> {
    const params = new HttpParams().set('days', days.toString());

    return this.http.get<ApiResponse<SentimentSummary>>(`${this.baseUrl}/sentiment/${epic}`, { params })
      .pipe(
        map(response => {
          const sentiment = response.success ? response.data.sentiment : 0;
          this.sentimentScore.set(sentiment);
          return sentiment;
        }),
        catchError(error => {
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
