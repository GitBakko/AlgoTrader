import { TestBed } from '@angular/core/testing';
import { WebSocketService } from './websocket.service';

describe('WebSocketService', () => {
  let service: WebSocketService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(WebSocketService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should have empty prices initially', () => {
    expect(service.prices()).toEqual({});
  });

  it('should have null lastTrade initially', () => {
    expect(service.lastTrade()).toBeNull();
  });

  it('should not be connected initially', () => {
    expect(service.connected()).toBeFalse();
  });

  it('should set connected to false on disconnect', () => {
    service.disconnect();
    expect(service.connected()).toBeFalse();
  });
});
