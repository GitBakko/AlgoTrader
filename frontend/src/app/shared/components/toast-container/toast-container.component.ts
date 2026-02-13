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
    <c-toaster placement="top-end" class="p-3" position="fixed" style="z-index: 1090;">
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
})
export class ToastContainerComponent {
  readonly toastService = inject(ToastService);

  onVisibleChange(id: number, visible: boolean): void {
    if (!visible) {
      this.toastService.dismiss(id);
    }
  }
}
