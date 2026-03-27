import { Injectable, inject, signal } from '@angular/core';
import { ApiService } from './api.service';
import { SignalAudit, SignalHistoryItem } from '../models';
import { ToastService } from '../../shared/services/toast.service';

@Injectable({ providedIn: 'root' })
export class SignalAuditService {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly isOpen = signal(false);
  readonly currentAudit = signal<SignalAudit | null>(null);
  readonly relatedSignals = signal<SignalHistoryItem[]>([]);
  readonly loading = signal(false);

  open(signalId: number): void {
    this.loading.set(true);
    this.isOpen.set(true);

    this.api.get<SignalAudit>(`/api/signals/audit/${signalId}`)
      .subscribe({
        next: (data) => {
          if (data) {
            this.currentAudit.set(data);
            this._loadHistory(data.epic);
          } else {
            this.toast.warning('Nessun dato audit disponibile');
            this.close();
          }
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.toast.warning('Audit non disponibile per questo segnale');
          this.close();
        },
      });
  }

  openByDealId(dealId: string, epic?: string): void {
    this.loading.set(true);
    this.isOpen.set(true);

    const params: Record<string, string> = {};
    if (epic) params['epic'] = epic;
    this.api.get<SignalAudit | null>(`/api/signals/audit/position/${dealId}`, params)
      .subscribe({
        next: (data) => {
          if (data) {
            this.currentAudit.set(data);
            this._loadHistory(data.epic);
          } else {
            this.toast.warning('Audit non disponibile per questa posizione');
            this.close();
          }
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.toast.warning('Audit non disponibile per questa posizione');
          this.close();
        },
      });
  }

  close(): void {
    this.isOpen.set(false);
    this.currentAudit.set(null);
    this.relatedSignals.set([]);
  }

  navigateToSignal(signalId: number): void {
    this.open(signalId);
  }

  openLatestByEpic(epic: string): void {
    this.loading.set(true);
    this.isOpen.set(true);

    this.api.get<{ items: SignalHistoryItem[] }>(
      `/api/signals/audit/history/${epic}`, { limit: 1 }
    ).subscribe({
      next: (data) => {
        const latest = data?.items?.[0];
        if (latest?.id) {
          this.open(latest.id);
        } else {
          this.loading.set(false);
          this.toast.warning('Nessun audit disponibile per ' + epic);
          this.close();
        }
      },
      error: () => {
        this.loading.set(false);
        this.toast.warning('Audit non disponibile per ' + epic);
        this.close();
      },
    });
  }

  private _loadHistory(epic: string): void {
    this.api.get<{ items: SignalHistoryItem[] }>(
      `/api/signals/audit/history/${epic}`, { limit: 10 }
    ).subscribe({
      next: (data) => this.relatedSignals.set(data?.items ?? []),
      error: () => {},
    });
  }
}
