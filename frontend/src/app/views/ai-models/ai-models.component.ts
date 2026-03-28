import { Component, ChangeDetectionStrategy, inject, OnInit, OnDestroy, computed, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent,
  ProgressComponent, ProgressBarComponent,
  TableDirective, NavModule, ButtonDirective,
} from '@coreui/angular';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TradingService } from '../../core/services/trading.service';
import { NewsService } from '../../core/services/news.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { TrainingJobInfo } from '../../core/models';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';
import { NewsWidgetComponent } from '../../shared/components/news-widget/news-widget.component';
import { LoadingButtonComponent } from '../../shared/components/loading-button/loading-button.component';

@Component({
  selector: 'app-ai-models',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './ai-models.component.scss',
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent,
    ProgressComponent, ProgressBarComponent,
    TableDirective, NavModule, ButtonDirective,
    EpicLogoComponent,
    NewsWidgetComponent,
    LoadingButtonComponent,
    FormsModule,
  ],
  template: `
    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-3 px-1">
      <div class="d-flex align-items-center gap-2">
        <h5 class="mb-0 fw-semibold">Modelli AI</h5>
        <c-badge color="primary">{{ models().length }} modelli</c-badge>
      </div>
      <div class="d-flex gap-2 text-body-secondary small">
        @if (avgF1() > 0) {
          <span>F1 medio: <strong class="text-success">{{ avgF1() | number:'1.3-3' }}</strong></span>
          <span>|</span>
        }
        <span>Tipo: XGBoost 3-classi</span>
      </div>
    </div>

    <!-- Tab Navigation -->
    <c-nav variant="tabs" class="mb-3">
      <c-nav-item>
        <a cNavLink [active]="activeTab() === 'models'" (click)="activeTab.set('models')" role="tab">
          Modelli
        </a>
      </c-nav-item>
      <c-nav-item>
        <a cNavLink [active]="activeTab() === 'training'" (click)="switchToTraining()" role="tab">
          Training
          @if (trainingRunning()) {
            <c-badge color="info" class="ms-1">In corso</c-badge>
          }
        </a>
      </c-nav-item>
    </c-nav>

    <!-- ═══════ MODELS TAB ═══════ -->
    @if (activeTab() === 'models') {
      <!-- Model Cards Grid -->
      @if (models().length > 0) {
        <c-row class="mb-4">
          @for (model of models(); track model.id) {
            <c-col sm="6" xl="4" class="mb-3">
              <c-card class="h-100 border-top border-top-3"
                      [class.border-top-success]="model.f1_score >= 0.5"
                      [class.border-top-warning]="model.f1_score >= 0.3 && model.f1_score < 0.5"
                      [class.border-top-danger]="model.f1_score < 0.3">
                <c-card-header class="d-flex align-items-center justify-content-between py-2">
                  <div class="d-flex align-items-center gap-2">
                    <div class="d-flex align-items-center gap-2 am-epic-link" (click)="onEpicClick(model.epic)">
                      <app-epic-logo [epic]="model.epic" [size]="28"></app-epic-logo>
                      <strong>{{ model.epic }}</strong>
                    </div>
                    <c-badge [color]="model.status === 'active' ? 'success' : 'secondary'" class="badge-sm">
                      {{ model.status === 'active' ? 'Attivo' : model.status }}
                    </c-badge>
                  </div>
                  <c-badge color="primary" class="badge-sm">{{ model.type }}</c-badge>
                </c-card-header>
                <c-card-body>
                  <!-- F1 Score (primary metric) -->
                  <div class="mb-3">
                    <div class="d-flex justify-content-between mb-1">
                      <span class="text-body-secondary small">F1 Macro</span>
                      <strong class="mantis-mono"
                              [class.text-success]="model.f1_score >= 0.5"
                              [class.text-warning]="model.f1_score >= 0.3 && model.f1_score < 0.5"
                              [class.text-danger]="model.f1_score < 0.3">
                        {{ model.f1_score | number:'1.3-3' }}
                      </strong>
                    </div>
                    <c-progress class="am-progress-sm">
                      <c-progress-bar
                        [value]="model.f1_score * 100"
                        [color]="model.f1_score >= 0.5 ? 'success' : model.f1_score >= 0.3 ? 'warning' : 'danger'">
                      </c-progress-bar>
                    </c-progress>
                  </div>

                  <!-- Accuracy -->
                  <div class="mb-3">
                    <div class="d-flex justify-content-between mb-1">
                      <span class="text-body-secondary small">Accuracy</span>
                      <span class="mantis-mono small">{{ (model.accuracy * 100) | number:'1.1-1' }}%</span>
                    </div>
                    <c-progress class="am-progress-xs">
                      <c-progress-bar [value]="model.accuracy * 100" color="info"></c-progress-bar>
                    </c-progress>
                  </div>

                  <!-- Meta info -->
                  <div class="d-flex justify-content-between text-body-secondary small border-top pt-2 mt-2">
                    <span>v{{ model.version }}</span>
                    <span>{{ formatDate(model.last_trained) }}</span>
                  </div>
                </c-card-body>
              </c-card>
            </c-col>
          }
        </c-row>
      } @else {
        <c-card class="border-top border-top-3 border-top-primary">
          <c-card-body>
            <div class="empty-state">
              <div class="empty-state__text">Nessun modello disponibile</div>
              <div class="empty-state__hint">Avvia il training per creare i modelli.</div>
            </div>
          </c-card-body>
        </c-card>
      }

      <!-- Summary Table -->
      @if (models().length > 0) {
        <c-card class="border-top border-top-3 border-top-primary">
          <c-card-header class="py-2"><span class="fw-semibold small text-body-secondary">Riepilogo Modelli</span></c-card-header>
          <c-card-body class="p-0">
            <div class="table-responsive-mobile">
              <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Tipo</th>
                    <th>Status</th>
                    <th class="text-end">F1 Macro</th>
                    <th class="text-end">Accuracy</th>
                    <th class="d-mobile-none">Versione</th>
                    <th class="d-mobile-none">Ultimo Training</th>
                  </tr>
                </thead>
              <tbody>
                @for (model of models(); track model.id) {
                  <tr>
                    <td class="fw-semibold">
                      <div class="d-flex align-items-center gap-2 am-epic-link" (click)="onEpicClick(model.epic)">
                        <app-epic-logo [epic]="model.epic" [size]="24"></app-epic-logo>
                        <span>{{ model.epic }}</span>
                      </div>
                    </td>
                    <td><c-badge color="primary" class="badge-sm">{{ model.type }}</c-badge></td>
                    <td>
                      <c-badge [color]="model.status === 'active' ? 'success' : 'secondary'" class="badge-sm">
                        {{ model.status === 'active' ? 'Attivo' : model.status }}
                      </c-badge>
                    </td>
                    <td class="text-end mantis-mono fw-semibold"
                        [class.text-success]="model.f1_score >= 0.5"
                        [class.text-warning]="model.f1_score >= 0.3 && model.f1_score < 0.5"
                        [class.text-danger]="model.f1_score < 0.3">
                      {{ model.f1_score | number:'1.3-3' }}
                    </td>
                    <td class="text-end mantis-mono">{{ (model.accuracy * 100) | number:'1.1-1' }}%</td>
                    <td class="d-mobile-none">{{ model.version }}</td>
                    <td class="text-body-secondary small d-mobile-none">{{ formatDate(model.last_trained) }}</td>
                  </tr>
                }
              </tbody>
            </table>
            </div>
          </c-card-body>
        </c-card>
      }
    }

    <!-- ═══════ TRAINING TAB ═══════ -->
    @if (activeTab() === 'training') {
      <!-- Status Banner + Action -->
      <c-card class="border-top border-top-3 border-top-primary mb-3">
        <c-card-body class="p-3">
          <div class="d-flex align-items-center justify-content-between">
            <div>
              @if (trainingRunning()) {
                <span class="fw-semibold">
                  <span class="pulse-dot me-2"></span>
                  Training in corso:
                  <span class="mantis-mono">{{ trainingCompletedCount() }}/{{ trainingTotalJobs() }}</span>
                  completati
                </span>
                @if (trainingFailedCount() > 0) {
                  <c-badge color="danger" class="ms-2">{{ trainingFailedCount() }} falliti</c-badge>
                }
              } @else {
                <span class="text-body-secondary">Nessun training attivo</span>
              }
            </div>
            <app-loading-button color="primary" size="sm" [loading]="retrainStarting()" (clicked)="onRetrainAll()">
              Retrain All
            </app-loading-button>
          </div>

          <!-- Advanced config toggle -->
          <div class="mt-2">
            <button class="btn btn-sm btn-ghost-secondary p-0 small text-body-secondary"
                    (click)="showAdvanced.set(!showAdvanced())">
              {{ showAdvanced() ? 'Nascondi configurazione \u25B2' : 'Configurazione avanzata \u25BC' }}
            </button>
          </div>

          @if (showAdvanced()) {
            <div class="advanced-config mt-3 p-3 rounded">
              <c-row class="g-3">
                <!-- Timeframe -->
                <c-col sm="6" xl="3">
                  <label class="form-label small text-body-secondary mb-1">Timeframe</label>
                  <select class="form-select form-select-sm"
                          [ngModel]="configTimeframe()"
                          (ngModelChange)="configTimeframe.set($event)">
                    <option value="15min">15 min</option>
                    <option value="1h">1 ora</option>
                    <option value="4h">4 ore</option>
                  </select>
                </c-col>

                <!-- Extended data toggle -->
                <c-col sm="6" xl="3">
                  <label class="form-label small text-body-secondary mb-1">Dati estesi</label>
                  <div class="form-check form-switch mt-1">
                    <input class="form-check-input" type="checkbox" role="switch" id="extDataToggle"
                           [ngModel]="configExtendedData()"
                           (ngModelChange)="configExtendedData.set($event)">
                    <label class="form-check-label small" for="extDataToggle">
                      {{ configExtendedData() ? 'Attivo' : 'Disattivo' }}
                    </label>
                  </div>
                </c-col>

                <!-- Days back (conditional) -->
                @if (configExtendedData()) {
                  <c-col sm="6" xl="3">
                    <label class="form-label small text-body-secondary mb-1">Giorni indietro</label>
                    <select class="form-select form-select-sm"
                            [ngModel]="configDaysBack()"
                            (ngModelChange)="configDaysBack.set(+$event)">
                      <option [value]="365">1 anno (365)</option>
                      <option [value]="730">2 anni (730)</option>
                      <option [value]="1095">3 anni (1095)</option>
                    </select>
                  </c-col>
                }

                <!-- Epic selection -->
                <c-col xs="12">
                  <label class="form-label small text-body-secondary mb-1">
                    Asset da allenare
                    <span class="text-body-secondary ms-1">({{ configSelectedEpics().length === 0 ? 'tutti' : configSelectedEpics().length + ' selezionati' }})</span>
                  </label>
                  <div class="epic-grid">
                    @for (epic of allEpics; track epic) {
                      <label class="epic-chip" [class.epic-chip--selected]="isEpicSelected(epic)">
                        <input type="checkbox" class="d-none"
                               [checked]="isEpicSelected(epic)"
                               (change)="toggleEpic(epic)">
                        <app-epic-logo [epic]="epic" [size]="16"></app-epic-logo>
                        <span class="small">{{ epic }}</span>
                      </label>
                    }
                  </div>
                </c-col>
              </c-row>
            </div>
          }
        </c-card-body>
      </c-card>

      <!-- P&L per Epic (always visible) -->
      @if (pnlByEpic().length > 0) {
        <c-card class="border-top border-top-3 border-top-primary mb-3">
          <c-card-header class="d-flex align-items-center justify-content-between py-2">
            <span class="fw-semibold small text-body-secondary">P&amp;L per Asset</span>
            <span class="small text-body-secondary">ordinato dal peggiore</span>
          </c-card-header>
          <c-card-body class="p-0">
            <div class="table-responsive-mobile">
              <table cTable [small]="true" [hover]="true" class="mb-0">
                <thead>
                  <tr class="text-body-secondary">
                    <th class="fw-semibold small">Asset</th>
                    <th class="fw-semibold small text-end">P&amp;L</th>
                    <th class="fw-semibold small text-end" style="width: 100px;">Azione</th>
                  </tr>
                </thead>
                <tbody>
                  @for (item of pnlByEpic(); track item.epic) {
                    <tr>
                      <td>
                        <div class="d-flex align-items-center gap-2">
                          <app-epic-logo [epic]="item.epic" [size]="20"></app-epic-logo>
                          <span class="fw-semibold small">{{ item.epic }}</span>
                        </div>
                      </td>
                      <td class="text-end mantis-mono fw-bold"
                          [class.text-success]="item.pnl >= 0"
                          [class.text-danger]="item.pnl < 0">
                        {{ item.pnl >= 0 ? '+' : '' }}{{ item.pnl | number:'1.2-2' }}
                      </td>
                      <td class="text-end">
                        <button cButton color="primary" variant="ghost" size="sm"
                                [disabled]="trainingRunning()"
                                (click)="retrainSingle(item.epic)">
                          Retrain
                        </button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </c-card-body>
        </c-card>
      }

      <!-- Training Job Cards Grid -->
      @if (trainingJobs().length > 0) {
        <c-row>
          @for (job of trainingJobs(); track job.epic) {
            <c-col sm="6" xl="4" class="mb-3">
              <div class="training-job-card training-job-card--{{ job.status }}">
                <div class="d-flex align-items-center justify-content-between mb-2">
                  <div class="d-flex align-items-center gap-2">
                    <app-epic-logo [epic]="job.epic" [size]="24"></app-epic-logo>
                    <strong class="small">{{ job.epic }}</strong>
                  </div>
                  <c-badge [color]="jobStatusColor(job.status)" class="badge-sm">
                    {{ jobStatusLabel(job.status) }}
                  </c-badge>
                </div>

                <!-- Progress -->
                <div class="text-body-secondary small mb-1">{{ job.progress }}</div>

                <!-- Metrics (completed) -->
                @if (job.status === 'completed' && job.metrics) {
                  <div class="d-flex gap-3 mt-2 small">
                    <span>
                      F1: <strong class="mantis-mono text-success">{{ job.metrics.f1_macro | number:'1.3-3' }}</strong>
                    </span>
                    <span>
                      Acc: <strong class="mantis-mono">{{ (job.metrics.accuracy * 100) | number:'1.1-1' }}%</strong>
                    </span>
                    <span>
                      Features: <span class="mantis-mono">{{ job.metrics.num_features }}</span>
                    </span>
                  </div>
                }

                <!-- Duration -->
                @if (job.duration_seconds != null) {
                  <div class="text-body-secondary small mt-1">
                    Durata: <span class="mantis-mono">{{ formatDuration(job.duration_seconds) }}</span>
                  </div>
                }

                <!-- Backtest button for completed jobs -->
                @if (job.status === 'completed') {
                  <button cButton color="primary" variant="outline" size="sm" class="mt-2"
                          (click)="launchBacktest(job.epic); $event.stopPropagation()">
                    Backtest
                  </button>
                }

                <!-- Error -->
                @if (job.status === 'failed' && job.error) {
                  <div class="text-danger small mt-2" style="word-break: break-word;">
                    {{ job.error }}
                  </div>
                }
              </div>
            </c-col>
          }
        </c-row>
      } @else if (!trainingRunning()) {
        <c-card class="border-top border-top-3 border-top-primary">
          <c-card-body>
            <div class="empty-state">
              <div class="empty-state__text">Nessun job di training</div>
              <div class="empty-state__hint">Premi "Retrain All" per avviare il training di tutti i modelli.</div>
            </div>
          </c-card-body>
        </c-card>
      }
    }

    <!-- ═══════ NEWS MODAL ═══════ -->
    @if (showNewsModal() && selectedEpic()) {
      <div class="am-modal-backdrop" (click)="closeNewsModal()" role="dialog" aria-modal="true" aria-label="News">
        <div class="am-modal" (click)="$event.stopPropagation()">
          <div class="am-modal__header">
            <div class="am-modal__title">
              <app-epic-logo [epic]="selectedEpic()!" [size]="32"></app-epic-logo>
              {{ selectedEpic() }} — Top News
            </div>
            <button class="am-modal__close" (click)="closeNewsModal()">&times;</button>
          </div>
          <div class="am-modal__body">
            <app-news-widget [news]="newsService.news()" [maxItems]="10" />
          </div>
        </div>
      </div>
    }
  `
})
export class AiModelsComponent implements OnInit, OnDestroy {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  private readonly router = inject(Router);
  readonly newsService = inject(NewsService);
  readonly models = this.trading.models;

  constructor() {
    this.ws.connectTraining();
    effect(() => {
      const update = this.ws.trainingUpdate();
      if (update) {
        this.trading.trainingStatus.set(update);
      }
    });
  }

  readonly activeTab = signal<'models' | 'training'>('models');
  readonly selectedEpic = signal<string | null>(null);
  readonly showNewsModal = signal(false);
  readonly retrainStarting = signal(false);

  // Advanced training config
  readonly showAdvanced = signal(false);
  readonly configTimeframe = signal<string>('1h');
  readonly configExtendedData = signal(false);
  readonly configDaysBack = signal(730);
  readonly configSelectedEpics = signal<string[]>([]);

  readonly allEpics: string[] = [
    'XAUUSD', 'BTCUSD', 'US500', 'WTIUSD', 'EURUSD', 'NVDA', 'TSLA',
    'XAGUSD', 'DE40', 'SOLUSD', 'ETHUSD', 'BNBUSD', 'DOGUSD', 'DASHUSD',
    'ICPUSD', 'NATGAS', 'COPPER', 'PLATINUM', 'GBPUSD', 'USDJPY', 'NAS100',
  ];

  private pollingId: ReturnType<typeof setInterval> | null = null;

  // Models computed
  readonly avgF1 = computed(() => {
    const m = this.models();
    if (m.length === 0) return 0;
    return m.reduce((sum, model) => sum + model.f1_score, 0) / m.length;
  });

  // Training computed
  readonly trainingRunning = computed(() => this.trading.trainingStatus()?.running ?? false);
  readonly trainingCompletedCount = computed(() => this.trading.trainingStatus()?.completed_count ?? 0);
  readonly trainingFailedCount = computed(() => this.trading.trainingStatus()?.failed_count ?? 0);
  readonly trainingTotalJobs = computed(() => {
    const status = this.trading.trainingStatus();
    return status ? Object.keys(status.jobs).length : 0;
  });
  readonly trainingJobs = computed((): TrainingJobInfo[] => {
    const status = this.trading.trainingStatus();
    if (!status) return [];
    return Object.values(status.jobs);
  });

  // P&L per epic from performance data, sorted worst to best
  readonly pnlByEpic = computed(() => {
    const perf = this.trading.performance();
    if (!perf?.pnl_by_epic) return [];
    return Object.entries(perf.pnl_by_epic)
      .map(([epic, pnl]) => ({ epic, pnl }))
      .sort((a, b) => a.pnl - b.pnl);
  });

  ngOnInit(): void {
    this.trading.loadModels();
    this.trading.loadTrainingStatus();
    this.trading.loadPerformance();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  switchToTraining(): void {
    this.activeTab.set('training');
    this.trading.loadTrainingStatus();
    this.startPolling();
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollingId = setInterval(() => {
      this.trading.loadTrainingStatus();
    }, 5000);
  }

  private stopPolling(): void {
    if (this.pollingId !== null) {
      clearInterval(this.pollingId);
      this.pollingId = null;
    }
  }

  onRetrainAll(): void {
    this.retrainStarting.set(true);
    if (this.showAdvanced()) {
      this.startRetrainWithConfig();
    } else {
      this.trading.startTraining();
    }
    this.startPolling();
    setTimeout(() => this.retrainStarting.set(false), 2000);
  }

  retrainSingle(epic: string): void {
    this.trading.startTrainingSingle(epic);
    this.activeTab.set('training');
    this.startPolling();
  }

  startRetrainWithConfig(): void {
    const epics = this.configSelectedEpics().length > 0 ? this.configSelectedEpics() : undefined;
    const config: Record<string, unknown> = {};
    if (this.configExtendedData()) {
      config['use_extended_data'] = true;
      config['days_back'] = this.configDaysBack();
    }
    const body: Record<string, unknown> = {};
    if (epics) body['epics'] = epics;
    body['timeframe'] = this.configTimeframe();
    body['config'] = config;
    this.trading.startTrainingFull(body);
  }

  isEpicSelected(epic: string): boolean {
    return this.configSelectedEpics().includes(epic);
  }

  toggleEpic(epic: string): void {
    const current = this.configSelectedEpics();
    if (current.includes(epic)) {
      this.configSelectedEpics.set(current.filter(e => e !== epic));
    } else {
      this.configSelectedEpics.set([...current, epic]);
    }
  }

  formatDate(iso: string | null): string {
    if (!iso) return 'Mai';
    try {
      return new Date(iso).toLocaleDateString('it-IT', {
        day: '2-digit', month: '2-digit', year: '2-digit',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso; }
  }

  formatDuration(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}m ${secs}s`;
  }

  jobStatusColor(status: string): string {
    switch (status) {
      case 'queued': return 'secondary';
      case 'running': return 'info';
      case 'completed': return 'success';
      case 'failed': return 'danger';
      default: return 'secondary';
    }
  }

  jobStatusLabel(status: string): string {
    switch (status) {
      case 'queued': return 'In coda';
      case 'running': return 'In corso';
      case 'completed': return 'Completato';
      case 'failed': return 'Fallito';
      default: return status;
    }
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

  launchBacktest(epic: string): void {
    this.router.navigate(['/backtest'], { queryParams: { epic } });
  }
}
