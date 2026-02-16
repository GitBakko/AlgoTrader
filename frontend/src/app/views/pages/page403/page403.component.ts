import { Component, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  ButtonDirective,
  CardBodyComponent,
  CardComponent,
  ColComponent,
  ContainerComponent,
  RowComponent
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';

/**
 * 403 Forbidden Component
 * Displayed when user lacks required permissions
 * MANTIS AI - Access denied page
 */
@Component({
  selector: 'app-page403',
  templateUrl: './page403.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ContainerComponent,
    RowComponent,
    ColComponent,
    CardComponent,
    CardBodyComponent,
    ButtonDirective,
    IconDirective,
    RouterLink
  ]
})
export class Page403Component {}
