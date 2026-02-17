import { Component, ChangeDetectionStrategy, inject, OnInit, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent,
  ProgressComponent, ProgressBarComponent,
  TableDirective,
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { NewsService } from '../../core/services/news.service';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';
import { NewsWidgetComponent } from '../../shared/components/news-widget/news-widget.component';

@Component({
  selector: 'app-ai-models',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './ai-models.component.scss',
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent,
    ProgressComponent, ProgressBarComponent,
    TableDirective,
    EpicLogoComponent,
    NewsWidgetComponent,
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

    <!-- ═══════ NEWS MODAL ═══════ -->
    @if (showNewsModal() && selectedEpic()) {
      <div class="am-modal-backdrop" (click)="closeNewsModal()">
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
export class AiModelsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  readonly newsService = inject(NewsService);
  readonly models = this.trading.models;

  readonly selectedEpic = signal<string | null>(null);
  readonly showNewsModal = signal(false);

  readonly avgF1 = computed(() => {
    const m = this.models();
    if (m.length === 0) return 0;
    return m.reduce((sum, model) => sum + model.f1_score, 0) / m.length;
  });

  ngOnInit(): void {
    this.trading.loadModels();
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

  onEpicClick(epic: string): void {
    this.selectedEpic.set(epic);
    this.showNewsModal.set(true);
    this.newsService.getNews(epic, 10, 7);
  }

  closeNewsModal(): void {
    this.showNewsModal.set(false);
    this.selectedEpic.set(null);
  }
}
