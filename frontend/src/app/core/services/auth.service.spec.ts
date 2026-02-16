import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { AuthService } from './auth.service';
import { environment } from '../../../environments/environment';

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;
  let routerSpy: jasmine.SpyObj<Router>;

  beforeEach(() => {
    const routerSpyObj = jasmine.createSpyObj('Router', ['navigate']);

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        AuthService,
        { provide: Router, useValue: routerSpyObj }
      ]
    });

    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
    routerSpy = TestBed.inject(Router) as jasmine.SpyObj<Router>;

    // Clear localStorage before each test
    localStorage.clear();
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should initialize with no authentication', () => {
    expect(service.isAuthenticated()).toBe(false);
    expect(service.currentUser()).toBeNull();
    expect(service.token()).toBeNull();
  });

  it('should login successfully and store token', (done) => {
    const mockResponse = {
      success: true,
      data: {
        access_token: 'test-token-123',
        token_type: 'Bearer',
        expires_in: 3600,
        user: {
          id: 1,
          username: 'testuser',
          email: 'test@example.com',
          role_id: 2,
          is_active: true,
          last_login: '2024-01-01T00:00:00Z',
          permissions: []
        }
      }
    };

    service.login('testuser', 'password123').subscribe({
      next: (response) => {
        expect(service.isAuthenticated()).toBe(true);
        expect(service.currentUser()?.username).toBe('testuser');
        expect(service.token()).toBe('test-token-123');
        expect(localStorage.getItem('mantis_auth_token')).toBe('test-token-123');
        done();
      }
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/auth/login`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ username: 'testuser', password: 'password123' });
    req.flush(mockResponse);
  });

  it('should handle login failure', (done) => {
    const mockError = {
      success: false,
      error: 'Invalid credentials'
    };

    service.login('testuser', 'wrongpassword').subscribe({
      error: (error) => {
        expect(service.isAuthenticated()).toBe(false);
        expect(service.token()).toBeNull();
        done();
      }
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/auth/login`);
    req.flush(mockError, { status: 401, statusText: 'Unauthorized' });
  });

  it('should register successfully', (done) => {
    const mockResponse = {
      success: true,
      data: {
        user: {
          id: 2,
          username: 'newuser',
          email: 'new@example.com',
          role_id: 1,
          is_active: true,
          last_login: null,
          permissions: []
        }
      }
    };

    service.register('newuser', 'new@example.com', 'password123', 1).subscribe({
      next: (response) => {
        expect(response.user.username).toBe('newuser');
        done();
      }
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/auth/register`);
    expect(req.request.method).toBe('POST');
    req.flush(mockResponse);
  });

  it('should logout and clear state', () => {
    // Set up authenticated state
    localStorage.setItem('mantis_auth_token', 'test-token');
    localStorage.setItem('mantis_current_user', JSON.stringify({
      id: 1,
      username: 'testuser',
      email: 'test@example.com',
      role_id: 2,
      is_active: true,
      last_login: null
    }));

    service.logout();

    expect(service.isAuthenticated()).toBe(false);
    expect(service.token()).toBeNull();
    expect(localStorage.getItem('mantis_auth_token')).toBeNull();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/login']);
  });

  it('should check permissions correctly', () => {
    // Mock authenticated user with permissions
    const mockUser = {
      id: 1,
      username: 'testuser',
      email: 'test@example.com',
      role_id: 2,
      is_active: true,
      last_login: null,
      permissions: [
        { resource: 'trading', action: 'execute' },
        { resource: 'positions', action: 'read' }
      ]
    };

    // Manually set auth state for testing
    service['authState'].set({
      isAuthenticated: true,
      currentUser: mockUser,
      token: 'test-token'
    });

    expect(service.hasPermission('trading', 'execute')).toBe(true);
    expect(service.hasPermission('positions', 'read')).toBe(true);
    expect(service.hasPermission('settings', 'write')).toBe(false);
  });

  it('should load stored authentication on init', () => {
    // Set up stored auth data
    const mockUser = {
      id: 1,
      username: 'testuser',
      email: 'test@example.com',
      role_id: 2,
      is_active: true,
      last_login: null
    };

    localStorage.setItem('mantis_auth_token', 'stored-token');
    localStorage.setItem('mantis_current_user', JSON.stringify(mockUser));

    // Create new service instance to trigger initialization
    const newService = TestBed.inject(AuthService);

    expect(newService.isAuthenticated()).toBe(true);
    expect(newService.token()).toBe('stored-token');
    expect(newService.currentUser()?.username).toBe('testuser');
  });
});
