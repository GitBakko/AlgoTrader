import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  provideHttpClientTesting,
  HttpTestingController,
} from '@angular/common/http/testing';
import { ApiService } from './api.service';

describe('ApiService', () => {
  let service: ApiService;
  let ctrl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(ApiService);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    ctrl.verify();
  });

  it('throws when envelope reports success:false at HTTP 200', () => {
    let caught: unknown;
    service.get<unknown>('/test').subscribe({
      error: (e) => (caught = e),
    });

    const req = ctrl.expectOne((r) => r.url.endsWith('/test'));
    req.flush({ success: false, data: null, error: 'backend says no' });

    expect(caught).toBeInstanceOf(Error);
    expect((caught as Error).message).toContain('backend says no');
  });

  it('unwraps data when success:true', () => {
    let value: unknown;
    service.get<{ x: number }>('/test').subscribe({ next: (v) => (value = v) });

    const req = ctrl.expectOne((r) => r.url.endsWith('/test'));
    req.flush({ success: true, data: { x: 1 } });

    expect(value).toEqual({ x: 1 });
  });
});
