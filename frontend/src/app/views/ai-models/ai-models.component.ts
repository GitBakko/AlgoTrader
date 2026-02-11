import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, TableDirective, BadgeComponent
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { MLModel } from '../../core/models';

@Component({
  selector: 'app-ai-models',
  standalone: true,
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, TableDirective, BadgeComponent
  ],
  template: `
    <c-row>
      <c-col xs="12">
        <c-card class="mb-4">
          <c-card-header><strong>AI Models</strong></c-card-header>
          <c-card-body>
            <table cTable striped hover>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Asset</th>
                  <th>Status</th>
                  <th>Accuracy</th>
                  <th>F1 Score</th>
                  <th>Version</th>
                  <th>Last Trained</th>
                </tr>
              </thead>
              <tbody>
                @for (model of models; track model.id) {
                  <tr>
                    <td><strong>{{ model.name }}</strong></td>
                    <td>{{ model.type }}</td>
                    <td>{{ model.epic }}</td>
                    <td>
                      <c-badge [color]="model.status === 'active' ? 'success' : 'secondary'">
                        {{ model.status }}
                      </c-badge>
                    </td>
                    <td>{{ (model.accuracy * 100) | number:'1.1-1' }}%</td>
                    <td>{{ model.f1_score | number:'1.3-3' }}</td>
                    <td>{{ model.version }}</td>
                    <td>{{ model.last_trained ?? 'Never' }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>
  `
})
export class AiModelsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  models: MLModel[] = [];

  ngOnInit(): void {
    this.trading.listModels().subscribe(data => this.models = data);
  }
}
