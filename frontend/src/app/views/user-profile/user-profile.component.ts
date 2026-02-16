import { Component, inject, signal, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import {
  ButtonDirective,
  CardBodyComponent,
  CardComponent,
  CardHeaderComponent,
  ColComponent,
  ContainerComponent,
  RowComponent,
  BadgeComponent,
  ListGroupDirective,
  ListGroupItemDirective
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { AuthService } from '../../core/services/auth.service';
import { User } from '../../core/models/auth.models';
import { AvatarComponent } from '../../shared/components/avatar/avatar.component';
import { AvatarUploadComponent } from '../../shared/components/avatar-upload/avatar-upload.component';

/**
 * User Profile Component
 * Display current user information and permissions
 * MANTIS AI - User account management
 */
@Component({
  selector: 'app-user-profile',
  templateUrl: './user-profile.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    ContainerComponent,
    RowComponent,
    ColComponent,
    CardComponent,
    CardHeaderComponent,
    CardBodyComponent,
    ButtonDirective,
    IconDirective,
    BadgeComponent,
    ListGroupDirective,
    ListGroupItemDirective,
    AvatarComponent,
    AvatarUploadComponent
  ]
})
export class UserProfileComponent implements OnInit {
  private readonly authService = inject(AuthService);

  readonly user = this.authService.currentUser;
  readonly loading = signal(false);
  readonly showAvatarUpload = signal(false);
  readonly deletingAvatar = signal(false);

  ngOnInit(): void {
    // Refresh user data on component init
    this.refreshProfile();
  }

  refreshProfile(): void {
    this.loading.set(true);
    this.authService.getCurrentUser().subscribe({
      next: () => {
        this.loading.set(false);
        console.log('[UserProfileComponent] Profile refreshed');
      },
      error: (error) => {
        this.loading.set(false);
        console.error('[UserProfileComponent] Failed to refresh profile', error);
      }
    });
  }

  logout(): void {
    this.authService.logout();
  }

  getRoleBadgeColor(roleName: string | undefined): string {
    switch (roleName) {
      case 'VIEWER': return 'info';
      case 'TRADER': return 'success';
      case 'ADMIN': return 'danger';
      default: return 'secondary';
    }
  }

  formatDate(date: string | null | undefined): string {
    if (!date) return 'Mai';
    return new Date(date).toLocaleString('it-IT');
  }

  toggleAvatarUpload(): void {
    this.showAvatarUpload.update(v => !v);
  }

  onAvatarUploaded(): void {
    console.log('[UserProfileComponent] Avatar uploaded, refreshing profile');
    this.showAvatarUpload.set(false);
    this.refreshProfile();
  }

  deleteAvatar(): void {
    if (!confirm('Sei sicuro di voler eliminare il tuo avatar?')) {
      return;
    }

    this.deletingAvatar.set(true);
    this.authService.deleteAvatar().subscribe({
      next: () => {
        this.deletingAvatar.set(false);
        console.log('[UserProfileComponent] Avatar deleted successfully');
        this.refreshProfile();
      },
      error: (error) => {
        this.deletingAvatar.set(false);
        console.error('[UserProfileComponent] Failed to delete avatar', error);
        alert('Errore durante l\'eliminazione dell\'avatar');
      }
    });
  }
}
