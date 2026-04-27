import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, ActivatedRoute } from '@angular/router';
import { of, throwError } from 'rxjs';
import { UserProfileComponent } from './user-profile.component';
import { AuthService } from '../../core/services/auth.service';
import { ConfirmDialogService } from '../../shared/services/confirm-dialog.service';
import { ToastService } from '../../shared/services/toast.service';
import { User } from '../../core/models/auth.models';
import { ApiResponse } from '../../core/models';
import { signal } from '@angular/core';

describe('UserProfileComponent', () => {
  let component: UserProfileComponent;
  let fixture: ComponentFixture<UserProfileComponent>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let routerSpy: jasmine.SpyObj<Router>;

  const mockUser: User = {
    id: 1,
    username: 'testuser',
    email: 'test@example.com',
    role_id: 2,
    role_name: 'TRADER',
    is_active: true,
    last_login: '2024-01-01T10:00:00Z',
    permissions: [
      { resource: 'trading', action: 'execute' },
      { resource: 'positions', action: 'read' }
    ]
  };

  const mockUserResponse: ApiResponse<User> = { success: true, data: mockUser };

  beforeEach(async () => {
    const authSpy = jasmine.createSpyObj('AuthService', ['getCurrentUser', 'logout', 'deleteAvatar']);
    const routerSpyObj = jasmine.createSpyObj('Router', ['navigate']);
    const confirmSpy = jasmine.createSpyObj('ConfirmDialogService', ['confirm']);
    const toastSpy = jasmine.createSpyObj('ToastService', ['success', 'error']);

    // Create a signal for currentUser
    (authSpy as any).currentUser = signal(mockUser);

    await TestBed.configureTestingModule({
      imports: [UserProfileComponent],
      providers: [
        { provide: AuthService, useValue: authSpy },
        { provide: Router, useValue: routerSpyObj },
        { provide: ConfirmDialogService, useValue: confirmSpy },
        { provide: ToastService, useValue: toastSpy },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParams: {} }, queryParams: of({}) } }
      ]
    }).compileComponents();

    authServiceSpy = TestBed.inject(AuthService) as jasmine.SpyObj<AuthService>;
    routerSpy = TestBed.inject(Router) as jasmine.SpyObj<Router>;
    // ngOnInit calls refreshProfile() — spy must return an observable by default.
    authServiceSpy.getCurrentUser.and.returnValue(of(mockUserResponse));

    fixture = TestBed.createComponent(UserProfileComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display user information', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement;

    expect(component.user()).toEqual(mockUser);
  });

  it('should refresh profile on init', () => {
    authServiceSpy.getCurrentUser.and.returnValue(of(mockUserResponse));

    component.ngOnInit();

    expect(authServiceSpy.getCurrentUser).toHaveBeenCalled();
  });

  it('should handle refresh profile success', () => {
    authServiceSpy.getCurrentUser.and.returnValue(of(mockUserResponse));

    component.refreshProfile();

    expect(component.loading()).toBe(false);
    expect(authServiceSpy.getCurrentUser).toHaveBeenCalled();
  });

  it('should handle refresh profile error', () => {
    const mockError = { error: { error: 'Failed to fetch user' } };
    authServiceSpy.getCurrentUser.and.returnValue(throwError(() => mockError));

    component.refreshProfile();

    expect(component.loading()).toBe(false);
  });

  it('should logout when logout button is clicked', () => {
    component.logout();

    expect(authServiceSpy.logout).toHaveBeenCalled();
  });

  it('should return correct role badge color', () => {
    expect(component.getRoleBadgeColor('VIEWER')).toBe('info');
    expect(component.getRoleBadgeColor('TRADER')).toBe('success');
    expect(component.getRoleBadgeColor('ADMIN')).toBe('danger');
    expect(component.getRoleBadgeColor(undefined)).toBe('secondary');
    expect(component.getRoleBadgeColor('UNKNOWN_ROLE')).toBe('secondary');
  });

  it('should format date correctly', () => {
    const formatted = component.formatDate('2024-01-01T10:00:00Z');
    expect(formatted).toContain('2024');
  });

  it('should handle null date', () => {
    expect(component.formatDate(null)).toBe('Mai');
    expect(component.formatDate(undefined)).toBe('Mai');
  });
});
