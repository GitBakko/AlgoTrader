import { Component, ChangeDetectionStrategy, inject, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent,
  ButtonDirective, FormControlDirective, TooltipDirective,
  FormSelectDirective, TableDirective,
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { NewsService } from '../../core/services/news.service';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';
import { NewsWidgetComponent } from '../../shared/components/news-widget/news-widget.component';
import { PaperSignal } from '../../core/models';
import { SignalAuditService } from '../../core/services/signal-audit.service';

type SortField = 'timestamp' | 'epic' | 'confidence' | 'entry_price';
type SortDir = 'asc' | 'desc';

@Component({
  selector: 'app-trade-journal',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './trade-journal.component.scss',
  imports: [
    CommonModule, FormsModule,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent,
    ButtonDirective, FormControlDirective,
    FormSelectDirective, TableDirective, IconDirective, TooltipDirective,
    PriceFormatPipe,
    EpicLogoComponent,
    NewsWidgetComponent,
  ],
  template: `
    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-3 px-1">
      <h5 class="mb-0 fw-semibold">Trade Journal</h5>
      <div class="d-flex align-items-center gap-2">
        <c-badge color="info">{{ filteredSignals().length }} risultati</c-badge>
        <button cButton color="primary" variant="outline" size="sm"
                [disabled]="filteredSignals().length === 0"
                (click)="exportToCsv()">
          <svg cIcon name="cilCloudDownload" size="sm" class="me-1"></svg>
          Esporta CSV
        </button>
        <button cButton color="secondary" size="sm" (click)="resetFilters()">Reset filtri</button>
      </div>
    </div>

    <!-- Filters -->
    <c-card class="mb-4 border-top border-top-3 border-top-primary">
      <c-card-body class="py-2 px-3">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <select cSelect class="form-select form-select-sm tj-filter-select"
                  [ngModel]="filterEpic()" (ngModelChange)="filterEpic.set($event)">
            <option value="">Tutti gli asset</option>
            @for (e of allEpics(); track e) {
              <option [value]="e">{{ e }}</option>
            }
          </select>
          <select cSelect class="form-select form-select-sm tj-filter-select"
                  [ngModel]="filterDirection()" (ngModelChange)="filterDirection.set($event)">
            <option value="">Tutte le direzioni</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
            <option value="HOLD">HOLD</option>
          </select>
          <select cSelect class="form-select form-select-sm tj-filter-select"
                  [ngModel]="filterStatus()" (ngModelChange)="filterStatus.set($event)">
            <option value="">Tutti gli stati</option>
            <option value="executed">Eseguito</option>
            <option value="rejected">Rifiutato</option>
            <option value="hold">Hold</option>
            <option value="market_closed">Chiuso</option>
            <option value="exec_failed">Fallito</option>
          </select>
          <select cSelect class="form-select form-select-sm tj-filter-select"
                  [ngModel]="filterStrategy()" (ngModelChange)="filterStrategy.set($event)">
            <option value="">Tutte le strategie</option>
            <option value="ml_ensemble">ML</option>
            <option value="squeeze_breakout">Squeeze</option>
            <option value="vwap_reversion">VWAP</option>
          </select>
          <div class="d-flex align-items-center gap-1 tj-filter-conf">
            <span class="text-body-secondary small text-nowrap">Conf. min</span>
            <input cFormControl type="number" min="0" max="100" step="5"
                   class="form-control form-control-sm"
                   style="width: 72px"
                   [ngModel]="filterMinConfidence()" (ngModelChange)="filterMinConfidence.set($event)">
          </div>
        </div>
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
    <c-card class="mb-4 border-top border-top-3 border-top-primary">
      <c-card-header class="py-2">
        <span class="fw-semibold small text-body-secondary">Storico Segnali</span>
      </c-card-header>
      <c-card-body class="p-0">
        @if (filteredSignals().length === 0) {
          <div class="empty-state">
            <div class="empty-state__text">Nessun segnale corrisponde ai filtri selezionati</div>
          </div>
        } @else {
          <div class="tj-scroll-container">
            <div class="table-responsive-mobile">
              <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
                <thead class="tj-sticky-thead">
                <tr>
                  <th class="tj-sortable" (click)="toggleSort('timestamp')">
                    Data/Ora {{ sortIcon('timestamp') }}
                  </th>
                  <th class="tj-sortable" (click)="toggleSort('epic')">
                    Asset {{ sortIcon('epic') }}
                  </th>
                  <th>Dir</th>
                  <th class="d-mobile-none">Strategia</th>
                  <th class="tj-sortable d-mobile-none" (click)="toggleSort('confidence')">
                    Conf {{ sortIcon('confidence') }}
                  </th>
                  <th class="tj-sortable d-mobile-none" (click)="toggleSort('entry_price')">
                    Prezzo {{ sortIcon('entry_price') }}
                  </th>
                  <th>Stato</th>
                  <th class="d-mobile-none">Posizione</th>
                  <th class="d-mobile-none">Dettaglio</th>
                  <th class="text-center d-mobile-none" style="width: 44px;">Note</th>
                </tr>
              </thead>
              <tbody>
                @for (sig of paginatedSignals(); track sig.timestamp + sig.epic) {
                  <tr [class.tj-row-rejected]="sig.status === 'rejected' || sig.status === 'exec_failed'"
                      [class.tj-row-closed]="sig.status === 'market_closed'">
                    <td class="small text-body-secondary text-nowrap">{{ formatDateTime(sig.timestamp) }}</td>
                    <td class="fw-semibold">
                      <div class="d-flex align-items-center gap-2 tj-epic-link" (click)="onEpicClick(sig.epic)">
                        <app-epic-logo [epic]="sig.epic" [size]="20"></app-epic-logo>
                        <span>{{ sig.epic }}</span>
                      </div>
                    </td>
                    <td>
                      <c-badge [color]="directionColor(sig.direction)" class="badge-sm">{{ sig.direction }}</c-badge>
                    </td>
                    <td class="d-mobile-none">
                      @if (sig.strategy_name) {
                        <c-badge [color]="strategyColor(sig.strategy_name)" class="badge-sm">
                          {{ strategyLabel(sig.strategy_name) }}
                        </c-badge>
                      } @else {
                        <span class="text-body-secondary">-</span>
                      }
                    </td>
                    <td class="mantis-mono d-mobile-none">{{ (sig.confidence * 100).toFixed(0) }}%</td>
                    <td class="mantis-mono d-mobile-none">{{ sig.entry_price | priceFormat:sig.epic }}</td>
                    <td>
                      <c-badge [color]="statusColor(sig.status)" class="badge-sm">{{ statusLabel(sig.status) }}</c-badge>
                      @if (sig.sl_cooldown) {
                        <c-badge [color]="sig.sl_cooldown.blocked ? 'danger' : 'warning'" class="badge-sm ms-1"
                                 [cTooltip]="'SL Cooldown: penalty ' + (sig.sl_cooldown.penalty * 100).toFixed(0) + '% (' + sig.sl_cooldown.window_hours + 'h)'">
                          {{ sig.sl_cooldown.sl_count }}/{{ sig.sl_cooldown.max_strikes }} SL
                        </c-badge>
                      }
                    </td>
                    <td class="d-mobile-none">
                      @if (sig.status === 'executed') {
                        @let posInfo = getPositionInfo(sig);
                        @if (posInfo.status === 'open') {
                          <span class="d-inline-flex align-items-center gap-1">
                            <span class="pulse-dot" style="width:6px;height:6px;"></span>
                            <span class="small">Aperta</span>
                            @if (posInfo.pnl !== null) {
                              <span class="mantis-mono small ms-1"
                                    [class.text-success]="posInfo.pnl >= 0"
                                    [class.text-danger]="posInfo.pnl < 0">
                                {{ posInfo.pnl >= 0 ? '+' : '' }}{{ posInfo.pnl.toFixed(2) }}
                              </span>
                            }
                          </span>
                        } @else if (posInfo.status === 'closed') {
                          <span class="d-inline-flex align-items-center gap-1">
                            <span class="small text-body-secondary">Chiusa</span>
                            @if (posInfo.pnl !== null) {
                              <span class="mantis-mono small ms-1"
                                    [class.text-success]="posInfo.pnl >= 0"
                                    [class.text-danger]="posInfo.pnl < 0">
                                {{ posInfo.pnl >= 0 ? '+' : '' }}{{ posInfo.pnl.toFixed(2) }}
                              </span>
                            }
                          </span>
                        }
                      } @else {
                        <span class="text-body-secondary">-</span>
                      }
                    </td>
                    <td class="small tj-detail-cell d-mobile-none">
                      @if (sig.error_detail) {
                        <span class="text-danger" [cTooltip]="errorTooltip(sig.error_detail)">
                          {{ sig.error_detail.summary }}
                          @if (sig.error_detail.details) {
                            <br><span class="text-body-secondary" style="font-size: 0.7rem">{{ sig.error_detail.details }}</span>
                          }
                        </span>
                      } @else if (sig.rejection_reason) {
                        <span class="text-danger">{{ sig.rejection_reason }}</span>
                      } @else if (sig.status === 'executed') {
                        <span class="text-success">OK</span>
                      } @else {
                        <span class="text-body-secondary">-</span>
                      }
                    </td>
                    <td class="text-center d-mobile-none">
                      <button cButton variant="ghost" size="sm" class="p-0"
                              [class.text-success]="hasNote(sig)"
                              [class.text-body-secondary]="!hasNote(sig)"
                              (click)="openNoteEditor(sig); $event.stopPropagation()">
                        <svg cIcon name="cilPencil" size="sm"></svg>
                      </button>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
            </div>
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

    <!-- ═══════ NEWS MODAL ═══════ -->
    @if (showNewsModal() && selectedEpic()) {
      <div class="tj-modal-backdrop" (click)="closeNewsModal()">
        <div class="tj-modal" (click)="$event.stopPropagation()">
          <div class="tj-modal__header">
            <div class="tj-modal__title">
              <app-epic-logo [epic]="selectedEpic()!" [size]="32"></app-epic-logo>
              {{ selectedEpic() }} — Top News
            </div>
            <button class="tj-modal__close" (click)="closeNewsModal()">&times;</button>
          </div>
          <div class="tj-modal__body">
            <app-news-widget [news]="newsService.news()" [maxItems]="10" />
          </div>
        </div>
      </div>
    }

    <!-- ═══════ NOTE MODAL ═══════ -->
    @if (showNoteModal()) {
      <div class="tj-modal-backdrop" (click)="closeNoteModal()">
        <div class="tj-modal" style="max-width: 500px" (click)="$event.stopPropagation()">
          <div class="tj-modal__header">
            <div class="tj-modal__title">
              <svg cIcon name="cilPencil" size="lg" class="me-2"></svg>
              Nota — {{ editingNoteEpic() }}
            </div>
            <button class="tj-modal__close" (click)="closeNoteModal()">&times;</button>
          </div>
          <div class="tj-modal__body">
            <textarea cFormControl rows="5" class="mb-3"
                      [ngModel]="editingNoteText()"
                      (ngModelChange)="editingNoteText.set($event)"
                      placeholder="Scrivi le tue note su questo segnale..."
                      maxlength="2000"></textarea>
            <div class="d-flex justify-content-between align-items-center">
              <span class="text-body-secondary small">{{ editingNoteText().length }}/2000</span>
              <div class="d-flex gap-2">
                <button cButton color="secondary" size="sm" (click)="closeNoteModal()">Annulla</button>
                <button cButton color="primary" size="sm" (click)="saveNote()" [disabled]="savingNote()">
                  {{ savingNote() ? 'Salvataggio...' : 'Salva' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    }
  `,
})
export class TradeJournalComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  readonly newsService = inject(NewsService);
  readonly auditService = inject(SignalAuditService);

  // Map of open positions by epic for quick lookup (includes opened_at for matching)
  readonly openPositionsByEpic = computed(() => {
    const map = new Map<string, { direction: string; size: number; level: number; opened_at: string | null }>();
    for (const pos of this.trading.paperPositions()) {
      map.set(pos.epic, {
        direction: pos.direction, size: pos.size, level: pos.level,
        opened_at: pos.opened_at ?? null,
      });
    }
    return map;
  });

  // Map of closed positions by epic → sorted by closed_at desc for matching
  readonly closedByEpic = computed(() => {
    const map = new Map<string, { pnl: number; opened_at: string; closed_at: string }[]>();
    for (const pos of this.trading.closedPositions()) {
      if (pos.profit_loss == null || !pos.closed_at) continue;
      const list = map.get(pos.epic) ?? [];
      list.push({ pnl: pos.profit_loss, opened_at: pos.opened_at ?? pos.closed_at, closed_at: pos.closed_at });
      map.set(pos.epic, list);
    }
    // Sort each list desc by closed_at
    for (const list of map.values()) {
      list.sort((a, b) => b.closed_at.localeCompare(a.closed_at));
    }
    return map;
  });

  readonly selectedEpic = signal<string | null>(null);
  readonly showNewsModal = signal(false);

  // Note editing
  readonly showNoteModal = signal(false);
  readonly editingNoteKey = signal('');
  readonly editingNoteEpic = signal('');
  readonly editingNoteText = signal('');
  readonly savingNote = signal(false);

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
    this.trading.loadSignalNotes();
    this.trading.loadPaperPositions();
    this.trading.loadClosedPositions({ page_size: 200 });
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

  errorTooltip(detail: any): string {
    if (!detail) return '';
    const parts: string[] = [];
    if (detail.error_type) parts.push(`Tipo: ${detail.error_type}`);
    if (detail.size) parts.push(`Size: ${detail.size}`);
    if (detail.direction) parts.push(`Dir: ${detail.direction}`);
    if (detail.raw && detail.raw !== detail.summary) parts.push(`Raw: ${detail.raw}`);
    return parts.join(' | ') || detail.summary || '';
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

  onEpicClick(epic: string): void {
    this.selectedEpic.set(epic);
    this.showNewsModal.set(true);
    this.newsService.getNews(epic, 10, 7);
  }

  closeNewsModal(): void {
    this.showNewsModal.set(false);
    this.selectedEpic.set(null);
  }

  // ── Note editing ──

  hasNote(sig: PaperSignal): boolean {
    const key = `${sig.epic}|${sig.timestamp}`;
    return !!this.trading.signalNotes()[key];
  }

  openNoteEditor(sig: PaperSignal): void {
    const key = `${sig.epic}|${sig.timestamp}`;
    this.editingNoteKey.set(key);
    this.editingNoteEpic.set(sig.epic);
    this.editingNoteText.set(this.trading.signalNotes()[key] || '');
    this.showNoteModal.set(true);
  }

  closeNoteModal(): void {
    this.showNoteModal.set(false);
  }

  saveNote(): void {
    const key = this.editingNoteKey();
    const [epic, timestamp] = key.split('|');
    const text = this.editingNoteText();
    this.savingNote.set(true);

    this.trading.updateSignalNote(epic, timestamp, text).subscribe({
      next: () => {
        const notes = { ...this.trading.signalNotes() };
        if (text.trim()) {
          notes[key] = text;
        } else {
          delete notes[key];
        }
        this.trading.signalNotes.set(notes);
        this.savingNote.set(false);
        this.closeNoteModal();
      },
      error: () => {
        this.savingNote.set(false);
      },
    });
  }

  // ── CSV Export ──

  exportToCsv(): void {
    const signals = this.filteredSignals();
    if (signals.length === 0) return;

    const headers = ['Data/Ora', 'Asset', 'Direzione', 'Strategia', 'Confidenza %', 'Prezzo', 'Stato', 'Dettaglio', 'Note'];
    const notes = this.trading.signalNotes();
    const rows = signals.map(s => [
      s.timestamp,
      s.epic,
      s.direction,
      s.strategy_name ?? '',
      (s.confidence * 100).toFixed(0),
      s.entry_price,
      s.status,
      s.error_detail?.summary ?? s.rejection_reason ?? '',
      notes[`${s.epic}|${s.timestamp}`] ?? '',
    ]);

    const csvContent = [headers, ...rows]
      .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');

    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
    this.downloadBlob(blob, `mantis_signals_${timestamp}.csv`);
  }

  private downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  /**
   * Get position status for an executed signal.
   * Returns: { status: 'open'|'closed'|null, pnl: number|null }
   */
  getPositionInfo(sig: PaperSignal): { status: string | null; pnl: number | null } {
    if (sig.status !== 'executed') return { status: null, pnl: null };

    const openPos = this.openPositionsByEpic().get(sig.epic);
    if (openPos) {
      // Check if this signal is the one that opened the current position
      // by comparing timestamps (signal must be close to position open time)
      if (openPos.opened_at) {
        const sigTime = this._utc(sig.timestamp);
        const posTime = this._utc(openPos.opened_at);
        // Signal must be within 5 minutes before position open (execution delay)
        const isMatch = sigTime <= posTime && (posTime - sigTime) < 5 * 60_000;
        if (!isMatch) {
          // This signal is for an older position, not the current open one
          return this._findClosedPnl(sig);
        }
      }
      // Position is still open — compute live P&L
      const prices = this.ws.prices();
      const tick = prices[sig.epic];
      if (tick) {
        const current = openPos.direction === 'BUY' ? tick.bid : tick.offer;
        const diff = openPos.direction === 'BUY'
          ? current - openPos.level
          : openPos.level - current;
        return { status: 'open', pnl: Math.round(diff * openPos.size * 100) / 100 };
      }
      return { status: 'open', pnl: null };
    }

    return this._findClosedPnl(sig);
  }

  /** Parse timestamp ensuring UTC (backend sends naive timestamps = UTC) */
  private _utc(ts: string): number {
    // If no timezone info, treat as UTC by appending Z
    if (!ts.includes('+') && !ts.includes('Z') && !ts.endsWith('-00:00')) {
      return new Date(ts + 'Z').getTime();
    }
    return new Date(ts).getTime();
  }

  private _findClosedPnl(sig: PaperSignal): { status: string | null; pnl: number | null } {
    const closedList = this.closedByEpic().get(sig.epic);
    if (closedList?.length) {
      const sigTime = this._utc(sig.timestamp);
      let best: { pnl: number; closed_at: string; opened_at: string } | null = null;
      let bestDist = Infinity;
      for (const c of closedList) {
        const closedTime = this._utc(c.closed_at);
        const openedTime = this._utc(c.opened_at);
        // Signal should be within a reasonable window before close
        if (sigTime <= closedTime + 60_000) {
          const dist = Math.abs(openedTime - sigTime);
          if (dist < bestDist) {
            bestDist = dist;
            best = c;
          }
        }
      }
      if (best) return { status: 'closed', pnl: best.pnl };
    }
    return { status: 'closed', pnl: null };
  }
}
