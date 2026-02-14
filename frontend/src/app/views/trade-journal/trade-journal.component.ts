import { Component, ChangeDetectionStrategy, inject, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent,
  ButtonDirective, FormControlDirective, FormLabelDirective,
  TableDirective,
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { PaperSignal } from '../../core/models';

type SortField = 'timestamp' | 'epic' | 'confidence' | 'entry_price';
type SortDir = 'asc' | 'desc';

@Component({
  selector: 'app-trade-journal',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent,
    ButtonDirective, FormControlDirective, FormLabelDirective,
    TableDirective,
    PriceFormatPipe,
  ],
  template: `
    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-3 px-1">
      <h5 class="mb-0 fw-semibold">Trade Journal</h5>
      <div class="d-flex align-items-center gap-2">
        <c-badge color="info">{{ filteredSignals().length }} risultati</c-badge>
        <button cButton color="secondary" size="sm" (click)="resetFilters()">Reset filtri</button>
      </div>
    </div>

    <!-- Filters -->
    <c-card class="mb-4">
      <c-card-body class="py-2">
        <c-row class="g-2 align-items-end">
          <c-col sm="3" lg="2">
            <label cLabel class="small text-body-secondary mb-1">Asset</label>
            <select cFormSelect [ngModel]="filterEpic()" (ngModelChange)="filterEpic.set($event)" class="form-select-sm">
              <option value="">Tutti</option>
              @for (e of allEpics(); track e) {
                <option [value]="e">{{ e }}</option>
              }
            </select>
          </c-col>
          <c-col sm="3" lg="2">
            <label cLabel class="small text-body-secondary mb-1">Direzione</label>
            <select cFormSelect [ngModel]="filterDirection()" (ngModelChange)="filterDirection.set($event)" class="form-select-sm">
              <option value="">Tutte</option>
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
              <option value="HOLD">HOLD</option>
            </select>
          </c-col>
          <c-col sm="3" lg="2">
            <label cLabel class="small text-body-secondary mb-1">Stato</label>
            <select cFormSelect [ngModel]="filterStatus()" (ngModelChange)="filterStatus.set($event)" class="form-select-sm">
              <option value="">Tutti</option>
              <option value="executed">Eseguito</option>
              <option value="rejected">Rifiutato</option>
              <option value="hold">Hold</option>
              <option value="market_closed">Chiuso</option>
              <option value="exec_failed">Fallito</option>
            </select>
          </c-col>
          <c-col sm="3" lg="2">
            <label cLabel class="small text-body-secondary mb-1">Strategia</label>
            <select cFormSelect [ngModel]="filterStrategy()" (ngModelChange)="filterStrategy.set($event)" class="form-select-sm">
              <option value="">Tutte</option>
              <option value="ml_ensemble">ML</option>
              <option value="squeeze_breakout">Squeeze</option>
              <option value="vwap_reversion">VWAP</option>
            </select>
          </c-col>
          <c-col sm="6" lg="2">
            <label cLabel class="small text-body-secondary mb-1">Conf. min</label>
            <input cFormControl type="number" min="0" max="100" step="5" class="form-control-sm"
                   [ngModel]="filterMinConfidence()" (ngModelChange)="filterMinConfidence.set($event)">
          </c-col>
        </c-row>
      </c-card-body>
    </c-card>

    <!-- Stats Summary -->
    <c-row class="mb-4">
      <c-col sm="6" xl="3">
        <c-card class="border-top border-top-3 border-top-primary">
          <c-card-body class="py-2">
            <div class="text-body-secondary small">Totale Segnali</div>
            <div class="fs-5 fw-bold">{{ filteredSignals().length }}</div>
          </c-card-body>
        </c-card>
      </c-col>
      <c-col sm="6" xl="3">
        <c-card class="border-top border-top-3 border-top-success">
          <c-card-body class="py-2">
            <div class="text-body-secondary small">Eseguiti</div>
            <div class="fs-5 fw-bold text-success">{{ executedCount() }}</div>
          </c-card-body>
        </c-card>
      </c-col>
      <c-col sm="6" xl="3">
        <c-card class="border-top border-top-3 border-top-danger">
          <c-card-body class="py-2">
            <div class="text-body-secondary small">Rifiutati</div>
            <div class="fs-5 fw-bold text-danger">{{ rejectedCount() }}</div>
          </c-card-body>
        </c-card>
      </c-col>
      <c-col sm="6" xl="3">
        <c-card class="border-top border-top-3 border-top-info">
          <c-card-body class="py-2">
            <div class="text-body-secondary small">Conf. Media</div>
            <div class="fs-5 fw-bold">{{ avgConfidence() }}%</div>
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>

    <!-- Trade Table -->
    <c-card class="mb-4">
      <c-card-header class="py-2">
        <strong>Storico Segnali</strong>
      </c-card-header>
      <c-card-body class="p-0">
        @if (filteredSignals().length === 0) {
          <div class="text-center py-5 text-body-secondary small">
            Nessun segnale corrisponde ai filtri selezionati.
          </div>
        } @else {
          <div style="max-height: 600px; overflow-y: auto;">
            <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
              <thead class="position-sticky top-0" style="z-index: 1;">
                <tr>
                  <th class="cursor-pointer" (click)="toggleSort('timestamp')">
                    Data/Ora {{ sortIcon('timestamp') }}
                  </th>
                  <th class="cursor-pointer" (click)="toggleSort('epic')">
                    Asset {{ sortIcon('epic') }}
                  </th>
                  <th>Dir</th>
                  <th>Strategia</th>
                  <th class="cursor-pointer" (click)="toggleSort('confidence')">
                    Conf {{ sortIcon('confidence') }}
                  </th>
                  <th class="cursor-pointer" (click)="toggleSort('entry_price')">
                    Prezzo {{ sortIcon('entry_price') }}
                  </th>
                  <th>Stato</th>
                  <th>Dettaglio</th>
                </tr>
              </thead>
              <tbody>
                @for (sig of paginatedSignals(); track sig.timestamp + sig.epic) {
                  <tr [class.table-danger]="sig.status === 'rejected' || sig.status === 'exec_failed'"
                      [class.table-secondary]="sig.status === 'market_closed'">
                    <td class="small text-body-secondary text-nowrap">{{ formatDateTime(sig.timestamp) }}</td>
                    <td class="fw-semibold">{{ sig.epic }}</td>
                    <td>
                      <c-badge [color]="directionColor(sig.direction)" class="badge-sm">{{ sig.direction }}</c-badge>
                    </td>
                    <td>
                      @if (sig.strategy_name) {
                        <c-badge [color]="strategyColor(sig.strategy_name)" class="badge-sm">
                          {{ strategyLabel(sig.strategy_name) }}
                        </c-badge>
                      } @else {
                        <span class="text-body-secondary">-</span>
                      }
                    </td>
                    <td class="font-monospace">{{ (sig.confidence * 100).toFixed(0) }}%</td>
                    <td class="font-monospace">{{ sig.entry_price | priceFormat:sig.epic }}</td>
                    <td>
                      <c-badge [color]="statusColor(sig.status)" class="badge-sm">{{ statusLabel(sig.status) }}</c-badge>
                    </td>
                    <td class="small" style="max-width: 200px;">
                      @if (sig.error_detail) {
                        <span class="text-danger">{{ sig.error_detail.summary }}</span>
                      } @else if (sig.rejection_reason) {
                        <span class="text-danger">{{ sig.rejection_reason }}</span>
                      } @else if (sig.status === 'executed') {
                        <span class="text-success">OK</span>
                      } @else {
                        <span class="text-body-secondary">-</span>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          @if (totalPages() > 1) {
            <div class="d-flex justify-content-between align-items-center px-3 py-2 border-top">
              <span class="text-body-secondary small">
                Pagina {{ currentPage() }} di {{ totalPages() }}
              </span>
              <div class="d-flex gap-1">
                <button cButton color="secondary" size="sm" [disabled]="currentPage() <= 1" (click)="currentPage.set(currentPage() - 1)">
                  &laquo; Prec
                </button>
                <button cButton color="secondary" size="sm" [disabled]="currentPage() >= totalPages()" (click)="currentPage.set(currentPage() + 1)">
                  Succ &raquo;
                </button>
              </div>
            </div>
          }
        }
      </c-card-body>
    </c-card>
  `,
  styles: [`
    .cursor-pointer { cursor: pointer; user-select: none; }
    .cursor-pointer:hover { color: var(--cui-primary); }
  `]
})
export class TradeJournalComponent implements OnInit {
  private readonly trading = inject(TradingService);

  // Filter signals
  readonly filterEpic = signal('');
  readonly filterDirection = signal('');
  readonly filterStatus = signal('');
  readonly filterStrategy = signal('');
  readonly filterMinConfidence = signal(0);

  // Sort
  readonly sortField = signal<SortField>('timestamp');
  readonly sortDir = signal<SortDir>('desc');

  // Pagination
  readonly currentPage = signal(1);
  readonly pageSize = 50;

  // All signals from API
  readonly allSignals = this.trading.paperSignals;

  // Unique epics for filter dropdown
  readonly allEpics = computed(() => {
    const epics = new Set(this.allSignals().map(s => s.epic));
    return [...epics].sort();
  });

  // Filtered + sorted
  readonly filteredSignals = computed(() => {
    let result = this.allSignals();

    const epic = this.filterEpic();
    if (epic) result = result.filter(s => s.epic === epic);

    const dir = this.filterDirection();
    if (dir) result = result.filter(s => s.direction === dir);

    const status = this.filterStatus();
    if (status) result = result.filter(s => s.status === status);

    const strat = this.filterStrategy();
    if (strat) result = result.filter(s => s.strategy_name === strat);

    const minConf = this.filterMinConfidence();
    if (minConf > 0) result = result.filter(s => s.confidence * 100 >= minConf);

    // Sort
    const field = this.sortField();
    const dir2 = this.sortDir() === 'asc' ? 1 : -1;
    result = [...result].sort((a, b) => {
      const va = (a as any)[field] ?? '';
      const vb = (b as any)[field] ?? '';
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir2;
      return String(va).localeCompare(String(vb)) * dir2;
    });

    return result;
  });

  // Stats
  readonly executedCount = computed(() => this.filteredSignals().filter(s => s.status === 'executed').length);
  readonly rejectedCount = computed(() => this.filteredSignals().filter(s => s.status === 'rejected' || s.status === 'exec_failed').length);
  readonly avgConfidence = computed(() => {
    const sigs = this.filteredSignals();
    if (sigs.length === 0) return '0';
    const avg = sigs.reduce((sum, s) => sum + s.confidence, 0) / sigs.length;
    return (avg * 100).toFixed(0);
  });

  // Pagination
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.filteredSignals().length / this.pageSize)));
  readonly paginatedSignals = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize;
    return this.filteredSignals().slice(start, start + this.pageSize);
  });

  ngOnInit(): void {
    this.trading.loadPaperSignals();
  }

  resetFilters(): void {
    this.filterEpic.set('');
    this.filterDirection.set('');
    this.filterStatus.set('');
    this.filterStrategy.set('');
    this.filterMinConfidence.set(0);
    this.currentPage.set(1);
  }

  toggleSort(field: SortField): void {
    if (this.sortField() === field) {
      this.sortDir.set(this.sortDir() === 'asc' ? 'desc' : 'asc');
    } else {
      this.sortField.set(field);
      this.sortDir.set('desc');
    }
    this.currentPage.set(1);
  }

  sortIcon(field: SortField): string {
    if (this.sortField() !== field) return '';
    return this.sortDir() === 'asc' ? '\u25B2' : '\u25BC';
  }

  directionColor(dir: string): string {
    return dir === 'BUY' ? 'success' : dir === 'SELL' ? 'danger' : 'secondary';
  }

  statusColor(status: string): string {
    switch (status) {
      case 'executed': return 'success';
      case 'rejected': case 'exec_failed': return 'danger';
      case 'hold': return 'warning';
      case 'market_closed': return 'dark';
      default: return 'secondary';
    }
  }

  statusLabel(status: string): string {
    switch (status) {
      case 'executed': return 'Eseguito';
      case 'rejected': return 'Rifiutato';
      case 'exec_failed': return 'Fallito';
      case 'hold': return 'Hold';
      case 'market_closed': return 'Chiuso';
      default: return status;
    }
  }

  strategyColor(name: string): string {
    switch (name) {
      case 'ml_ensemble': return 'primary';
      case 'squeeze_breakout': return 'warning';
      case 'vwap_reversion': return 'info';
      default: return 'secondary';
    }
  }

  strategyLabel(name: string): string {
    switch (name) {
      case 'ml_ensemble': return 'ML';
      case 'squeeze_breakout': return 'Squeeze';
      case 'vwap_reversion': return 'VWAP';
      default: return name;
    }
  }

  formatDateTime(iso: string): string {
    if (!iso) return '-';
    try {
      return new Date(iso).toLocaleString('it-IT', {
        day: '2-digit', month: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
    } catch { return iso; }
  }
}
