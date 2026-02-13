import { Injectable, signal } from '@angular/core';

export interface ToastMessage {
  id: number;
  text: string;
  color: 'success' | 'danger' | 'warning' | 'info' | 'primary';
  delay: number;
  visible: boolean;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<ToastMessage[]>([]);
  private nextId = 0;

  success(text: string, delay = 4000): void {
    this.add(text, 'success', delay);
  }

  error(text: string, delay = 6000): void {
    this.add(text, 'danger', delay);
  }

  warning(text: string, delay = 5000): void {
    this.add(text, 'warning', delay);
  }

  info(text: string, delay = 4000): void {
    this.add(text, 'info', delay);
  }

  dismiss(id: number): void {
    this.toasts.update(list => list.filter(t => t.id !== id));
  }

  private add(text: string, color: ToastMessage['color'], delay: number): void {
    const id = ++this.nextId;
    const toast: ToastMessage = { id, text, color, delay, visible: true };
    this.toasts.update(list => [...list, toast]);

    setTimeout(() => this.dismiss(id), delay);
  }
}
