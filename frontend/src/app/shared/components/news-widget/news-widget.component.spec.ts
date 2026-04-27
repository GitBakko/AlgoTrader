import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NewsWidgetComponent } from './news-widget.component';
import { NewsArticle } from '../../../core/models/news.model';

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
      thumbnail: 'https://example.com/image.jpg',
    },
    {
      title: 'Gold prices decline amid strong dollar',
      description: 'Gold fell 2% as dollar strengthened',
      url: 'https://example.com/gold',
      published_at: new Date(Date.now() - 3_600_000).toISOString(),
      sentiment: -0.6,
      entities: ['XAUUSD'],
      source: 'marketaux',
      thumbnail: null,
    },
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NewsWidgetComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(NewsWidgetComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('returns empty displayedNews when no input given', () => {
    expect(component.displayedNews).toEqual([]);
  });

  it('limits displayedNews to maxItems by default', () => {
    component.news = mockArticles;
    component.maxItems = 1;
    expect(component.displayedNews.length).toBe(1);
  });

  it('shows all articles when showAll is toggled on', () => {
    component.news = mockArticles;
    component.maxItems = 1;
    component.showAll = true;
    expect(component.displayedNews.length).toBe(2);
  });

  it('classifies sentiment via getSentimentBadge', () => {
    expect(component.getSentimentBadge(0.5)).toBe('success');
    expect(component.getSentimentBadge(-0.5)).toBe('danger');
    expect(component.getSentimentBadge(0)).toBe('secondary');
  });

  it('sentimentClass returns danger tone for strong negative', () => {
    expect(component.sentimentClass(-0.7)).toContain('text-danger');
    expect(component.sentimentClass(0.7)).toContain('text-success');
  });

  it('produces relative time labels', () => {
    const now = new Date().toISOString();
    const oneHourAgo = new Date(Date.now() - 3_600_000).toISOString();
    expect(component.getRelativeTime(now)).toMatch(/Ora|m fa/);
    expect(component.getRelativeTime(oneHourAgo)).toContain('fa');
  });
});
