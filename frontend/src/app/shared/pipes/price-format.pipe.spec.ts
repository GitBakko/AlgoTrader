import { PriceFormatPipe } from './price-format.pipe';

describe('PriceFormatPipe', () => {
  let pipe: PriceFormatPipe;

  beforeEach(() => {
    pipe = new PriceFormatPipe();
  });

  it('should create', () => {
    expect(pipe).toBeTruthy();
  });

  it('should format BTCUSD with 0 decimals', () => {
    const result = pipe.transform(91234.56, 'BTCUSD');
    expect(result).toBe('91,235');
  });

  it('should format XAUUSD with 2 decimals', () => {
    const result = pipe.transform(2934.56, 'XAUUSD');
    expect(result).toBe('2,934.56');
  });

  it('should format EURUSD with 5 decimals', () => {
    const result = pipe.transform(1.07234, 'EURUSD');
    expect(result).toBe('1.07234');
  });

  it('should format XAGUSD with 3 decimals', () => {
    const result = pipe.transform(32.456, 'XAGUSD');
    expect(result).toBe('32.456');
  });

  it('should format US500 with 1 decimal', () => {
    const result = pipe.transform(6012.34, 'US500');
    expect(result).toBe('6,012.3');
  });

  it('should format DE40 with 1 decimal', () => {
    const result = pipe.transform(22145.89, 'DE40');
    expect(result).toBe('22,145.9');
  });

  it('should format NVDA with 2 decimals', () => {
    const result = pipe.transform(134.567, 'NVDA');
    expect(result).toBe('134.57');
  });

  it('should format TSLA with 2 decimals', () => {
    const result = pipe.transform(345.12, 'TSLA');
    expect(result).toBe('345.12');
  });

  it('should format WTIUSD with 2 decimals', () => {
    const result = pipe.transform(72.345, 'WTIUSD');
    expect(result).toBe('72.35');
  });

  it('should return dash for null value', () => {
    expect(pipe.transform(null, 'XAUUSD')).toBe('—');
  });

  it('should return dash for undefined value', () => {
    expect(pipe.transform(undefined, 'XAUUSD')).toBe('—');
  });

  it('should return dash for NaN value', () => {
    expect(pipe.transform(NaN, 'XAUUSD')).toBe('—');
  });

  it('should use 2 decimals as default for unknown epic', () => {
    const result = pipe.transform(123.456, 'UNKNOWN');
    expect(result).toBe('123.46');
  });
});
