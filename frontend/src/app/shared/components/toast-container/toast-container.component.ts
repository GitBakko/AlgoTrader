import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ToasterComponent, ToastComponent, ToastBodyComponent, ToastCloseDirective,
} from '@coreui/angular';
import { ToastService } from '../../services/toast.service';

@Component({
  selector: 'app-toast-container',
  standalone: true,
  imports: [
    CommonModule, ToasterComponent, ToastComponent,
    ToastBodyComponent, ToastCloseDirective,
  ],
  template: `
    <c-toaster placement="top-end" class="p-3 mantis-toaster" position="fixed">
      @for (toast of toastService.toasts(); track toast.id) {
        <c-toast #toastEl [color]="toast.color" [visible]="toast.visible"
                 (visibleChange)="onVisibleChange(toast.id, $event)"
                 class="text-white border-0">
          <c-toast-body class="d-flex align-items-center justify-content-between">
            <span>{{ toast.text }}</span>
            <button [cToastClose]="toastEl" type="button"
                    class="btn-close btn-close-white ms-2" aria-label="Close"></button>
          </c-toast-body>
        </c-toast>
      }
    </c-toaster>
  `,
  styles: [`
    /* CoreUI modals reserve 1050; toasters must layer above them. */
    .mantis-toaster { z-index: 1090; }
  `],
})
export class ToastContainerComponent {
  readonly toastService = inject(ToastService);

  onVisibleChange(id: number, visible: boolean): void {
    if (!visible) {
      this.toastService.dismiss(id);
    }
  }
}
