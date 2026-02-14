/**
 * News and sentiment data models.
 * Maps to backend API responses from /api/news endpoints.
 */

export interface NewsArticle {
  title: string;
  description: string;
  url: string;
  published_at: string;
  sentiment: number;  // -1.0 to 1.0
  entities: string[];
  source: 'marketaux' | 'finnhub';  // News provider
}

export interface InsiderSentiment {
  epic: string;
  mspr: number;  // -100 to +100 (Monthly Share Purchase Ratio)
  change: number;
  period: string;  // "YYYY-MM" format
}

export interface AnalystConsensus {
  epic: string;
  buy: number;
  hold: number;
  sell: number;
  consensus: string;  // "BUY" | "HOLD" | "SELL"
  target_price: number;
}

export interface SentimentSummary {
  epic: string;
  sentiment: number;  // -1.0 to 1.0
  article_count: number;
  period_days: number;
}
