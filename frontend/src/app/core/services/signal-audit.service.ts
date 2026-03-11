import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { SignalAudit, SignalHistoryItem } from '../models';
import { ToastService } from '../../shared/services/toast.service';

@Injectable({ providedIn: 'root' })
export class SignalAuditService {
  private readonly http = inject(HttpClient);
  private readonly toast = inject(ToastService);

  readonly isOpen = signal(false);
  readonly currentAudit = signal<SignalAudit | null>(null);
  readonly relatedSignals = signal<SignalHistoryItem[]>([]);
  readonly loading = signal(false);

  open(signalId: number): void {
    this.loading.set(true);
    this.isOpen.set(true);

    this.http.get<{ success: boolean; data: SignalAudit }>(`/api/signals/audit/${signalId}`)
      .subscribe({
        next: (resp) => {
          if (resp.success && resp.data) {
            this.currentAudit.set(resp.data);
            this._loadHistory(resp.data.epic);
          } else {
            this.toast.warning('Nessun dato audit disponibile');
            this.close();
          }
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.toast.error('Impossibile caricare i dati del segnale');
          this.close();
        },
      });
  }

  openByDealId(dealId: string): void {
    this.loading.set(true);
    this.isOpen.set(true);

    this.http.get<{ success: boolean; data: SignalAudit | null }>(`/api/signals/audit/position/${dealId}`)
      .subscribe({
        next: (resp) => {
          if (resp.success && resp.data) {
            this.currentAudit.set(resp.data);
            this._loadHistory(resp.data.epic);
          } else {
            this.toast.warning('Audit non disponibile per questa posizione');
            this.close();
          }
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.toast.error('Impossibile caricare i dati del segnale');
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

  private _loadHistory(epic: string): void {
    this.http.get<{ success: boolean; data: { items: SignalHistoryItem[] } }>(
      `/api/signals/audit/history/${epic}?limit=10`
    ).subscribe({
      next: (resp) => this.relatedSignals.set(resp.data?.items ?? []),
      error: () => {},
    });
  }
}
