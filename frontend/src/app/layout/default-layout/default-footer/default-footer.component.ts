import { ChangeDetectionStrategy, Component } from '@angular/core';
import { FooterComponent } from '@coreui/angular';

@Component({
  selector: 'app-default-footer',
  templateUrl: './default-footer.component.html',
  styleUrls: ['./default-footer.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DefaultFooterComponent extends FooterComponent {
  constructor() {
    super();
  }
}
