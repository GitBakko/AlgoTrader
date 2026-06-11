import { TestBed } from '@angular/core/testing';
import {
  provideHttpClient,
  withInterceptors,
  HttpClient,
} from '@angular/common/http';
import {
  provideHttpClientTesting,
  HttpTestingController,
} from '@angular/common/http/testing';
import { ToastService } from '../../shared/services/toast.service';
import { errorInterceptor } from './error.interceptor';

describe('errorInterceptor', () => {
  let http: HttpClient;
  let ctrl: HttpTestingController;
  let toastStub: { error: ReturnType<typeof vi.fn>; warning: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    toastStub = { error: vi.fn(), warning: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
        { provide: ToastService, useValue: toastStub },
      ],
    });

    http = TestBed.inject(HttpClient);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    // verify() can throw (stray pending retry — exactly what this suite
    // exists to catch); restore real timers regardless so a single failure
    // doesn't cascade fake timers into subsequent tests.
    try {
      ctrl.verify();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does NOT retry a POST on retryable status', () => {
    let error: unknown;
    http.post('/api/test', {}).subscribe({ error: (e) => (error = e) });

    const req = ctrl.expectOne('/api/test');
    expect(req.request.method).toBe('POST');
    req.flush('Service Unavailable', { status: 503, statusText: 'Service Unavailable' });

    // Only one request should have been made — no retry on POST.
    // ctrl.verify() in afterEach will catch any extra requests.
    expect(error).toBeDefined();
  });

  it('retries a GET on retryable status', async () => {
    vi.useFakeTimers();

    let value: unknown;
    let error: unknown;
    http.get<{ ok: boolean }>('/api/test').subscribe({
      next: (v) => (value = v),
      error: (e) => (error = e),
    });

    // First request — flush 503 to trigger retry
    const req1 = ctrl.expectOne('/api/test');
    expect(req1.request.method).toBe('GET');
    req1.flush('Service Unavailable', { status: 503, statusText: 'Service Unavailable' });

    // Advance past the backoff delay (2^0 * 1000 = 1000 ms)
    await vi.advanceTimersByTimeAsync(1100);

    // Second request — flush success
    const req2 = ctrl.expectOne('/api/test');
    req2.flush({ ok: true });

    expect(value).toEqual({ ok: true });
    expect(error).toBeUndefined();
  });

  it('does not retry non-retryable status on GET', () => {
    let error: unknown;
    http.get('/api/test').subscribe({ error: (e) => (error = e) });

    const req = ctrl.expectOne('/api/test');
    req.flush('Bad Request', { status: 400, statusText: 'Bad Request' });

    // ctrl.verify() in afterEach confirms no extra requests
    expect(error).toBeDefined();
  });
});
