import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NewsWidgetComponent, NewsArticle } from './news-widget.component';

describe('NewsWidgetComponent', () => {
  let component: NewsWidgetComponent;
  let fixture: ComponentFixture<NewsWidgetComponent>;

  const mockArticles: NewsArticle[] = [
    {
      title: 'Tesla stock soars on earnings beat',
      description: 'Tesla reported strong quarterly earnings',
      url: 'https://example.com/tesla',
      published_at: new Date().toISOString(),
      sentiment: 0.8,
      entities: ['TSLA'],
      source: 'finnhub',
      thumbnail: 'https://example.com/image.jpg'
    },
    {
      title: 'Gold prices decline amid strong dollar',
      description: 'Gold fell 2% as dollar strengthened',
      url: 'https://example.com/gold',
      published_at: new Date(Date.now() - 3600000).toISOString(),
      sentiment: -0.6,
      entities: ['XAUUSD'],
      source: 'marketaux',
      thumbnail: null
    }
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NewsWidgetComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(NewsWidgetComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display all articles when no epic filter', () => {
    fixture.componentRef.setInput('news', mockArticles);
    fixture.detectChanges();

    const articles = component.filteredNews();
    expect(articles.length).toBe(2);
  });

  it('should filter articles by epic', () => {
    fixture.componentRef.setInput('news', mockArticles);
    fixture.componentRef.setInput('epic', 'TSLA');
    fixture.detectChanges();

    const articles = component.filteredNews();
    expect(articles.length).toBe(1);
    expect(articles[0].entities).toContain('TSLA');
  });

  it('should limit articles to maxItems', () => {
    fixture.componentRef.setInput('news', mockArticles);
    fixture.componentRef.setInput('maxItems', 1);
    fixture.detectChanges();

    const articles = component.filteredNews();
    expect(articles.length).toBe(1);
  });

  it('should get correct sentiment color', () => {
    expect(component.getSentimentColor(0.5)).toBe('success');
    expect(component.getSentimentColor(-0.5)).toBe('danger');
    expect(component.getSentimentColor(0.1)).toBe('secondary');
  });

  it('should get correct sentiment label', () => {
    expect(component.getSentimentLabel(0.5)).toBe('Positive');
    expect(component.getSentimentLabel(-0.5)).toBe('Negative');
    expect(component.getSentimentLabel(0.1)).toBe('Neutral');
  });

  it('should format date correctly', () => {
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 3600000);
    const oneDayAgo = new Date(now.getTime() - 86400000);

    expect(component.formatDate(oneHourAgo.toISOString())).toContain('ago');
    expect(component.formatDate(oneDayAgo.toISOString())).toContain('ago');
  });

  it('should emit articleClick on click', () => {
    spyOn(component.articleClick, 'emit');
    spyOn(window, 'open');

    component.onArticleClick(mockArticles[0]);

    expect(component.articleClick.emit).toHaveBeenCalledWith(mockArticles[0]);
    expect(window.open).toHaveBeenCalledWith(mockArticles[0].url, '_blank');
  });

  it('should handle image load error', () => {
    const event = {
      target: {
        src: 'old-url'
      }
    } as unknown as Event;

    component.onImageError(event);

    expect((event.target as HTMLImageElement).src).toBe('assets/img/placeholder-news.png');
  });
});
