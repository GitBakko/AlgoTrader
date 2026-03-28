import { Component, OnInit, OnDestroy, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CardComponent, CardBodyComponent, CardHeaderComponent, BadgeComponent, RowComponent, ColComponent } from '@coreui/angular';
import { NewsService } from '../../core/services/news.service';

@Component({
  selector: 'app-news',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent, BadgeComponent, RowComponent, ColComponent],
  templateUrl: './news.component.html',
  styleUrls: ['./news.component.scss']
})
export class NewsComponent implements OnInit, OnDestroy {
  private readonly newsService = inject(NewsService);

  readonly news = this.newsService.news;
  readonly sentimentScore = this.newsService.sentimentScore;
  readonly isLoading = this.newsService.isLoading;
  readonly error = this.newsService.error;
  readonly selectedEpic = signal<string>('NVDA');

  readonly assets = [
    'NVDA', 'TSLA', 'XAUUSD', 'BTCUSD', 'US500', 'WTIUSD', 'EURUSD', 'XAGUSD', 'DE40',
    'SOLUSD', 'ETHUSD', 'BNBUSD', 'DOGUSD', 'DASHUSD', 'ICPUSD',
    'NATGAS', 'COPPER', 'PLATINUM', 'GBPUSD', 'USDJPY', 'NAS100'
  ];

  private pollTimer: any;

  ngOnInit(): void {
    this.loadNews();
    // Poll every 30 seconds
    this.pollTimer = setInterval(() => this.loadNews(), 30_000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
    }
  }

  loadNews(): void {
    const epic = this.selectedEpic();
    this.newsService.getNews(epic, 20, 7);
    this.newsService.getSentiment(epic, 7).subscribe();
  }

  onEpicChange(epic: string): void {
    this.selectedEpic.set(epic);
    this.newsService.clearData();
    this.loadNews();
  }

  getSentimentClass(score: number): string {
    if (score > 0.3) return 'text-success';
    if (score < -0.3) return 'text-danger';
    return 'text-body-secondary';
  }

  getSentimentBadge(score: number): string {
    if (score > 0.3) return 'success';
    if (score < -0.3) return 'danger';
    return 'secondary';
  }

  getSentimentLabel(score: number): string {
    if (score > 0.3) return 'Positive';
    if (score < -0.3) return 'Negative';
    return 'Neutral';
  }

  getRelativeTime(dateString: string): string {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  }

  /**
   * Handle image load errors by hiding broken thumbnails
   */
  onImageError(event: Event): void {
    const img = event.target as HTMLImageElement;
    if (img && img.parentElement) {
      img.parentElement.style.display = 'none';
    }
  }
}
