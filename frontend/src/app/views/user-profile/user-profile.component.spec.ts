import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { UserProfileComponent } from './user-profile.component';
import { AuthService } from '../../core/services/auth.service';
import { signal } from '@angular/core';

describe('UserProfileComponent', () => {
  let component: UserProfileComponent;
  let fixture: ComponentFixture<UserProfileComponent>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let routerSpy: jasmine.SpyObj<Router>;

  const mockUser = {
    id: 1,
    username: 'testuser',
    email: 'test@example.com',
    role_id: 2,
    is_active: true,
    last_login: '2024-01-01T10:00:00Z',
    permissions: [
      { resource: 'trading', action: 'execute' },
      { resource: 'positions', action: 'read' }
    ]
  };

  beforeEach(async () => {
    const authSpy = jasmine.createSpyObj('AuthService', ['getCurrentUser', 'logout']);
    const routerSpyObj = jasmine.createSpyObj('Router', ['navigate']);

    // Create a signal for currentUser
    (authSpy as any).currentUser = signal(mockUser);

    await TestBed.configureTestingModule({
      imports: [UserProfileComponent],
      providers: [
        { provide: AuthService, useValue: authSpy },
        { provide: Router, useValue: routerSpyObj }
      ]
    }).compileComponents();

    authServiceSpy = TestBed.inject(AuthService) as jasmine.SpyObj<AuthService>;
    routerSpy = TestBed.inject(Router) as jasmine.SpyObj<Router>;

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
    authServiceSpy.getCurrentUser.and.returnValue(of(mockUser));

    component.ngOnInit();

    expect(authServiceSpy.getCurrentUser).toHaveBeenCalled();
  });

  it('should handle refresh profile success', () => {
    authServiceSpy.getCurrentUser.and.returnValue(of(mockUser));

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

  it('should return correct role name', () => {
    expect(component.getRoleName(1)).toBe('Viewer');
    expect(component.getRoleName(2)).toBe('Trader');
    expect(component.getRoleName(3)).toBe('Admin');
    expect(component.getRoleName(999)).toBe('Unknown');
  });

  it('should return correct role badge color', () => {
    expect(component.getRoleBadgeColor(1)).toBe('info');
    expect(component.getRoleBadgeColor(2)).toBe('success');
    expect(component.getRoleBadgeColor(3)).toBe('danger');
    expect(component.getRoleBadgeColor(999)).toBe('secondary');
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
