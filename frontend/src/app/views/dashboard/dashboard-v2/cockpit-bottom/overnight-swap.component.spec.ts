import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { signal } from '@angular/core';
import { OvernightSwapComponent } from './overnight-swap.component';
import { TradingService } from '../../../../core/services/trading.service';

describe('OvernightSwapComponent', () => {
  const tradingStub = {
    overnightSwap: signal<Record<string, any>>({}),
    loadOvernightSwap: jasmine.createSpy('loadOvernightSwap'),
  };

  beforeEach(async () => {
    tradingStub.overnightSwap.set({});
    tradingStub.loadOvernightSwap.calls.reset();
    await TestBed.configureTestingModule({
      imports: [OvernightSwapComponent],
      providers: [
        provideHttpClient(),
        { provide: TradingService, useValue: tradingStub },
      ],
    }).compileComponents();
  });

  it('triggers loadOvernightSwap for the input epic', () => {
    const fixture = TestBed.createComponent(OvernightSwapComponent);
    fixture.componentRef.setInput('epic', 'BTCUSD');
    fixture.detectChanges();
    expect(tradingStub.loadOvernightSwap).toHaveBeenCalledWith('BTCUSD');
  });

  it('exposes the signal value for the current epic', () => {
    const fixture = TestBed.createComponent(OvernightSwapComponent);
    fixture.componentRef.setInput('epic', 'XAUUSD');
    tradingStub.overnightSwap.set({
      XAUUSD: {
        epic: 'XAUUSD',
        currency: 'USD',
        long_rate_daily: -0.000015,
        short_rate_daily: -0.00001,
        long_rate_pct: -0.0015,
        short_rate_pct: -0.001,
        weekend_multiplier: 3,
        next_charge_utc: new Date(Date.now() + 3600_000).toISOString(),
        source: 'broker',
      },
    });
    fixture.detectChanges();
    const comp = fixture.componentInstance;
    expect(comp.swap()?.source).toBe('broker');
    expect(comp.nextChargeCountdown()).toMatch(/\d+h \d+m/);
  });
});
