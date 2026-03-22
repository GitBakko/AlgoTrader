import { Component, inject, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ModalComponent, ModalHeaderComponent, ModalBodyComponent,
  ModalFooterComponent, ModalTitleDirective,
  ButtonDirective,
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { ConfirmDialogService } from '../../services/confirm-dialog.service';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, ModalComponent, ModalHeaderComponent, ModalBodyComponent,
    ModalFooterComponent, ModalTitleDirective,
    ButtonDirective, IconDirective,
  ],
  template: `
    <c-modal
      [visible]="dialogService.visible()"
      (visibleChange)="onVisibleChange($event)"
      alignment="center"
      backdrop="static"
      [keyboard]="false"
    >
      <c-modal-header class="confirm-dialog__header">
        <h5 cModalTitle class="confirm-dialog__title">
          @if (dialogService.options().icon) {
            <svg [cIcon]="dialogService.options().icon!" size="lg" class="me-2"></svg>
          }
          {{ dialogService.options().title }}
        </h5>
      </c-modal-header>
      <c-modal-body class="confirm-dialog__body">
        <p class="mb-0">{{ dialogService.options().message }}</p>
      </c-modal-body>
      <c-modal-footer class="confirm-dialog__footer">
        <button cButton color="secondary" variant="outline" size="sm"
                (click)="dialogService.resolve(false)">
          {{ dialogService.options().cancelText }}
        </button>
        <button cButton [color]="dialogService.options().color || 'danger'" size="sm"
                class="mantis-btn-confirm"
                (click)="dialogService.resolve(true)">
          {{ dialogService.options().confirmText }}
        </button>
      </c-modal-footer>
    </c-modal>
  `,
  styles: [`
    :host ::ng-deep .confirm-dialog__header {
      background: var(--mantis-surface-3, #1c2128);
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }

    :host ::ng-deep .confirm-dialog__title {
      font-family: var(--mantis-font-ui);
      font-size: 1rem;
      font-weight: 600;
      color: var(--cui-body-color);
      display: flex;
      align-items: center;
    }

    :host ::ng-deep .confirm-dialog__body {
      background: var(--mantis-surface-2, #161b22);
      font-size: 0.9375rem;
      line-height: 1.5;
      padding: 1.25rem;
    }

    :host ::ng-deep .confirm-dialog__footer {
      background: var(--mantis-surface-3, #1c2128);
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      gap: 0.5rem;
    }

    :host ::ng-deep .mantis-btn-confirm {
      min-width: 100px;
    }

    :host ::ng-deep .modal-content {
      border: 1px solid rgba(255, 255, 255, 0.10);
      border-radius: 8px;
      overflow: hidden;
    }
  `],
})
export class ConfirmDialogComponent {
  readonly dialogService = inject(ConfirmDialogService);

  onVisibleChange(visible: boolean): void {
    if (!visible) {
      this.dialogService.resolve(false);
    }
  }
}
