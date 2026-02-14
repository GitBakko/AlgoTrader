import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { MarketStatusService, MarketStatusResponse } from './market-status.service';
import { environment } from '../../../environments/environment';

describe('MarketStatusService', () => {
  let service: MarketStatusService;
  let httpMock: HttpTestingController;

  const mockStatus: MarketStatusResponse = {
    epic: 'XAUUSD',
    is_open: true,
    status: 'TRADEABLE',
    next_open: null,
    session: { open: '23:00', close: '22:00', timezone: 'UTC' }
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [MarketStatusService]
    });

    service = TestBed.inject(MarketStatusService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    service.clearCache();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should fetch market status from API', async () => {
    const epic = 'XAUUSD';
    const statusPromise = service.getMarketStatus(epic);

    const req = httpMock.expectOne(`${environment.apiUrl}/markets/status/${epic}`);
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: mockStatus });

    const status = await statusPromise;
    expect(status).toEqual(mockStatus);
  });

  it('should use cache for repeated requests within 60s', async () => {
    const epic = 'XAUUSD';

    // First request
    const firstPromise = service.getMarketStatus(epic);
    const req = httpMock.expectOne(`${environment.apiUrl}/markets/status/${epic}`);
    req.flush({ success: true, data: mockStatus });
    await firstPromise;

    // Second request (should use cache)
    const secondPromise = service.getMarketStatus(epic);
    httpMock.expectNone(`${environment.apiUrl}/markets/status/${epic}`);
    const secondStatus = await secondPromise;

    expect(secondStatus).toEqual(mockStatus);
  });

  it('should fallback to open status on API error', async () => {
    const epic = 'BTCUSD';
    const statusPromise = service.getMarketStatus(epic);

    const req = httpMock.expectOne(`${environment.apiUrl}/markets/status/${epic}`);
    req.error(new ProgressEvent('Network error'));

    const status = await statusPromise;
    expect(status.epic).toBe(epic);
    expect(status.is_open).toBe(true);
    expect(status.status).toBe('TRADEABLE');
  });

  it('should track multi-epic status', async () => {
    const epic1 = 'XAUUSD';
    const epic2 = 'BTCUSD';

    // Fetch status for both
    const promise1 = service.getMarketStatus(epic1);
    const req1 = httpMock.expectOne(`${environment.apiUrl}/markets/status/${epic1}`);
    req1.flush({ success: true, data: mockStatus });
    await promise1;

    const promise2 = service.getMarketStatus(epic2);
    const req2 = httpMock.expectOne(`${environment.apiUrl}/markets/status/${epic2}`);
    req2.flush({
      success: true,
      data: { ...mockStatus, epic: epic2, is_open: false, status: 'CLOSED', next_open: Date.now() + 3600000 }
    });
    await promise2;

    // Get multi-status signal
    const multiStatus = service.getMultiStatus([epic1, epic2]);
    const statuses = multiStatus();

    expect(Object.keys(statuses).length).toBe(2);
    expect(statuses[epic1].is_open).toBe(true);
    expect(statuses[epic2].is_open).toBe(false);
  });

  it('should clear cache', async () => {
    const epic = 'XAUUSD';

    // Fetch and cache
    const promise = service.getMarketStatus(epic);
    const req = httpMock.expectOne(`${environment.apiUrl}/markets/status/${epic}`);
    req.flush({ success: true, data: mockStatus });
    await promise;

    const statsBefore = service.getCacheStats();
    expect(statsBefore.size).toBe(1);

    // Clear cache
    service.clearCache();

    const statsAfter = service.getCacheStats();
    expect(statsAfter.size).toBe(0);
  });
});
