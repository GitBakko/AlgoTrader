import { Component, ChangeDetectionStrategy, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent,
  TableDirective, BadgeComponent,
  ProgressComponent, ProgressBarComponent
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';

@Component({
  selector: 'app-ai-models',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, CardComponent, CardBodyComponent,
    TableDirective, BadgeComponent,
    ProgressComponent, ProgressBarComponent
  ],
  template: `
    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-3 px-1">
      <div class="d-flex align-items-center gap-2">
        <h5 class="mb-0 fw-semibold">Modelli AI</h5>
        <c-badge color="primary">{{ models().length }}</c-badge>
      </div>
    </div>

    <c-card class="mb-4">
      <c-card-body class="p-0">
        @if (models().length > 0) {
          <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
            <thead>
              <tr>
                <th>Nome</th>
                <th>Tipo</th>
                <th>Asset</th>
                <th>Status</th>
                <th>Accuracy</th>
                <th>F1 Score</th>
                <th>Versione</th>
                <th>Ultimo Training</th>
              </tr>
            </thead>
            <tbody>
              @for (model of models(); track model.id) {
                <tr>
                  <td class="fw-semibold">{{ model.name }}</td>
                  <td><c-badge color="primary" class="badge-sm">{{ model.type }}</c-badge></td>
                  <td>{{ model.epic }}</td>
                  <td>
                    <c-badge [color]="model.status === 'active' ? 'success' : 'secondary'" class="badge-sm">
                      {{ model.status === 'active' ? 'Attivo' : model.status }}
                    </c-badge>
                  </td>
                  <td>
                    <div class="d-flex align-items-center gap-1">
                      <c-progress class="flex-grow-1" style="height: 4px; min-width: 40px;">
                        <c-progress-bar
                          [value]="model.accuracy * 100"
                          [color]="model.accuracy >= 0.6 ? 'success' : model.accuracy >= 0.4 ? 'warning' : 'danger'">
                        </c-progress-bar>
                      </c-progress>
                      <small class="font-monospace">{{ (model.accuracy * 100) | number:'1.1-1' }}%</small>
                    </div>
                  </td>
                  <td class="font-monospace fw-semibold"
                      [class.text-success]="model.f1_score >= 0.5"
                      [class.text-warning]="model.f1_score >= 0.3 && model.f1_score < 0.5"
                      [class.text-danger]="model.f1_score < 0.3">
                    {{ model.f1_score | number:'1.3-3' }}
                  </td>
                  <td>{{ model.version }}</td>
                  <td class="text-body-secondary small">{{ formatDate(model.last_trained) }}</td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <div class="text-center py-5 text-body-secondary small">
            Nessun modello disponibile. Avvia il training per creare i modelli.
          </div>
        }
      </c-card-body>
    </c-card>
  `
})
export class AiModelsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  readonly models = this.trading.models;

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
}
