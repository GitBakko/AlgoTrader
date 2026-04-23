/**
 * News Widget Component - Compact news display for dashboard widgets
 * Shows essential news info: title, sentiment, time
 */

import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BadgeComponent } from '@coreui/angular';
import { NewsArticle } from '../../../core/models/news.model';

@Component({
  selector: 'app-news-widget',
  standalone: true,
  imports: [CommonModule, BadgeComponent],
  template: `
    <div class="news-widget">
      @if (news.length === 0) {
        <div class="text-center py-3 text-body-secondary small">
          <span>📰</span>
          <p class="mb-0 mt-1">Nessuna notizia disponibile</p>
        </div>
      } @else {
        @for (article of displayedNews; track article.url) {
          <div class="news-widget-item" [class.border-bottom]="!$last">
            <div class="d-flex justify-content-between align-items-start gap-2 mb-1">
              <a
                [href]="article.url"
                target="_blank"
                rel="noopener noreferrer"
                class="news-widget-title text-decoration-none">
                {{ article.title }}
              </a>
              <span
                class="sentiment-mini flex-shrink-0"
                [ngClass]="sentimentClass(article.sentiment)">
                {{ article.sentiment >= 0 ? '+' : '' }}{{ article.sentiment | number:'1.1-1' }}
              </span>
            </div>
            <div class="d-flex gap-2 align-items-center">
              <small class="text-body-secondary">
                {{ getRelativeTime(article.published_at) }}
              </small>
              <c-badge
                [color]="article.source === 'finnhub' ? 'primary' : 'success'"
                class="badge-xs">
                {{ article.source === 'finnhub' ? 'F' : 'M' }}
              </c-badge>
            </div>
          </div>
        }
        @if (news.length > maxItems && !showAll) {
          <button
            class="btn btn-link btn-sm p-0 mt-2 text-decoration-none"
            (click)="showAll = true">
            Mostra altre {{ news.length - maxItems }} notizie...
          </button>
        }
      }
    </div>
  `,
  styles: [`
    .news-widget-item {
      padding: 0.5rem 0;

      &:last-child {
        padding-bottom: 0;
      }

      &.border-bottom {
        border-bottom: 1px solid var(--cui-border-color);
      }
    }

    .news-widget-title {
      font-size: var(--mantis-fs-body);
      font-weight: 500;
      line-height: 1.3;
      color: var(--cui-body-color);
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;

      &:hover {
        color: var(--cui-primary);
        text-decoration: underline !important;
      }
    }

    .sentiment-mini {
      font-size: var(--mantis-fs-xs);
      padding: 0.15rem 0.35rem;
      font-weight: 600;
      border: none;
      min-width: 32px;
      text-align: center;
      border-radius: var(--mantis-radius-sm);
    }

    .badge-xs {
      font-size: var(--mantis-fs-xs);
      padding: 0.1rem 0.3rem;
    }

    // Mantis AI theme
    :host-context(.mantis-theme) {
      .news-widget-title:hover {
        color: var(--mantis-neon);
      }
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class NewsWidgetComponent {
  @Input() news: NewsArticle[] = [];
  @Input() maxItems: number = 5;

  showAll = false;

  get displayedNews(): NewsArticle[] {
    return this.showAll ? this.news : this.news.slice(0, this.maxItems);
  }

  getSentimentBadge(sentiment: number): string {
    if (sentiment >= 0.3) return 'success';
    if (sentiment <= -0.3) return 'danger';
    return 'secondary';
  }

  sentimentClass(sentiment: number): string {
    if (sentiment >= 0.6) return 'text-success';
    if (sentiment >= 0.2) return 'text-success';
    if (sentiment >= 0.05) return 'text-success opacity-75';
    if (sentiment > -0.05) return 'text-body-secondary';
    if (sentiment > -0.2) return 'text-warning';
    if (sentiment > -0.6) return 'text-danger opacity-75';
    return 'text-danger';
  }

  getRelativeTime(publishedAt: string): string {
    const date = new Date(publishedAt);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Ora';
    if (diffMins < 60) return `${diffMins}m fa`;
    if (diffHours < 24) return `${diffHours}h fa`;
    if (diffDays < 7) return `${diffDays}g fa`;
    return date.toLocaleDateString('it-IT', { month: 'short', day: 'numeric' });
  }
}
