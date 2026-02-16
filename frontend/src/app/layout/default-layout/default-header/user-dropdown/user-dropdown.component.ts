import { Component, computed, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  BadgeComponent,
  DropdownComponent,
  DropdownDividerDirective,
  DropdownHeaderDirective,
  DropdownItemDirective,
  DropdownMenuDirective,
  DropdownToggleDirective
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { AuthService } from '../../../../core/services/auth.service';
import { AvatarComponent as MantisAvatarComponent } from '../../../../shared/components/avatar/avatar.component';

/**
 * User dropdown component for header
 * Displays user info, navigation links, and logout
 */
@Component({
  selector: 'app-user-dropdown',
  standalone: true,
  imports: [
    BadgeComponent,
    DropdownComponent,
    DropdownToggleDirective,
    DropdownMenuDirective,
    DropdownHeaderDirective,
    DropdownItemDirective,
    DropdownDividerDirective,
    IconDirective,
    RouterLink,
    MantisAvatarComponent
  ],
  templateUrl: './user-dropdown.component.html',
  styleUrls: ['./user-dropdown.component.scss']
})
export class UserDropdownComponent {
  readonly #authService = inject(AuthService);
  readonly #router = inject(Router);

  /**
   * Current authenticated user from AuthService
   */
  readonly user = this.#authService.currentUser;

  /**
   * Check if user is authenticated
   */
  readonly isAuthenticated = this.#authService.isAuthenticated;

  /**
   * User initials for avatar (e.g., "JD" for John Doe)
   */
  readonly userInitials = computed(() => {
    const currentUser = this.user();
    if (!currentUser) return '?';

    // Get first letter of username
    return currentUser.username.charAt(0).toUpperCase();
  });

  /**
   * Badge color based on role
   */
  readonly roleBadgeColor = computed(() => {
    const currentUser = this.user();
    if (!currentUser) return 'secondary';

    const role = currentUser.role_name.toUpperCase();
    switch (role) {
      case 'GOD':
        return 'danger'; // Red for supreme admin
      case 'ADMIN':
        return 'warning'; // Orange for admin
      case 'TRADER':
        return 'success'; // Green for trader
      case 'VIEWER':
        return 'info'; // Blue for viewer
      default:
        return 'secondary';
    }
  });

  /**
   * Role display text with icon
   */
  readonly roleDisplay = computed(() => {
    const currentUser = this.user();
    if (!currentUser) return { icon: 'cilUser', text: 'Unknown' };

    const role = currentUser.role_name.toUpperCase();
    switch (role) {
      case 'GOD':
        return { icon: 'cilShieldAlt', text: 'GOD' };
      case 'ADMIN':
        return { icon: 'cilSettings', text: 'Admin' };
      case 'TRADER':
        return { icon: 'cilChart', text: 'Trader' };
      case 'VIEWER':
        return { icon: 'cilSpectrum', text: 'Viewer' };
      default:
        return { icon: 'cilUser', text: role };
    }
  });

  /**
   * Shortened email for display (e.g., "john...@example.com")
   */
  readonly displayEmail = computed(() => {
    const currentUser = this.user();
    if (!currentUser?.email) return '';

    const email = currentUser.email;
    if (email.length <= 25) return email;

    // Shorten long emails: "verylongemail@example.com" -> "verylong...@example.com"
    const [localPart, domain] = email.split('@');
    if (localPart.length > 15) {
      return `${localPart.substring(0, 12)}...@${domain}`;
    }
    return email;
  });

  /**
   * Handle logout action
   */
  onLogout(): void {
    this.#authService.logout();
    this.#router.navigate(['/login']);
  }
}
