export interface AppNotification {
  id: number;
  alert_type: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO';
  title: string;
  message: string;
  epic?: string;
  emoji: string;
  details: Record<string, any>;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: AppNotification[];
  total: number;
  page: number;
  page_size: number;
}
