import {
  Component,
  input,
  output,
  inject,
  signal,
  computed,
  effect,
  ChangeDetectionStrategy
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { CardModule, BadgeModule } from '@coreui/angular';

// Interface for news article
export interface NewsArticle {
  title: string;
  description: string;
  url: string;
  published_at: string;
  sentiment: number;
  entities: string[];
  source: string;
  thumbnail?: string | null;
}

@Component({
  selector: 'app-news-widget',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, CardModule, BadgeModule],
  templateUrl: './news-widget.component.html',
  styleUrl: './news-widget.component.scss'
})
export class NewsWidgetComponent {
  epic = input<string | null>(null);
  maxItems = input<number>(10);
  news = input<NewsArticle[]>([]);
  articleClick = output<NewsArticle>();

  filteredNews = computed(() => {
    const allNews = this.news();
    const currentEpic = this.epic();
    const limit = this.maxItems();

    let filtered = currentEpic
      ? allNews.filter(n => n.entities.includes(currentEpic))
      : allNews;

    return filtered.slice(0, limit);
  });

  onImageError(event: Event): void {
    // Fallback to placeholder on image load error
    (event.target as HTMLImageElement).src = 'assets/img/placeholder-news.png';
  }

  getSentimentColor(sentiment: number): string {
    if (sentiment > 0.3) return 'success';
    if (sentiment < -0.3) return 'danger';
    return 'secondary';
  }

  getSentimentLabel(sentiment: number): string {
    if (sentiment > 0.3) return 'Positive';
    if (sentiment < -0.3) return 'Negative';
    return 'Neutral';
  }

  onArticleClick(article: NewsArticle): void {
    this.articleClick.emit(article);
    window.open(article.url, '_blank');
  }

  formatDate(dateString: string): string {
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
}
