/**
 * Visual symbols/icons for each EPIC to improve recognition.
 * Uses Unicode emoji and special characters for lightweight implementation.
 */
export const EPIC_SYMBOLS: Record<string, string> = {
  // Crypto (₿ ⟠ ⬡ etc.)
  BTCUSD: '₿',      // Bitcoin official symbol
  SOLUSD: '◎',      // Solana (circle with dot)
  ETHUSD: 'Ξ',      // Ethereum official symbol
  BNBUSD: '⬡',      // Binance (hexagon)
  DOGUSD: 'Ð',      // Dogecoin (D with stroke)
  DASHUSD: 'Đ',     // Dash (D with stroke)
  ICPUSD: '∞',      // Internet Computer (infinity)

  // Commodities
  XAUUSD: '🥇',     // Gold medal
  XAGUSD: '🥈',     // Silver medal
  WTIUSD: '🛢️',     // Oil barrel
  NATGAS: '🔥',     // Natural gas (fire)
  COPPER: '🔶',     // Copper (orange diamond)
  PLATINUM: '💎',   // Platinum (gem)

  // Forex
  GBPUSD: '£',      // Pound sterling
  USDJPY: '¥',      // Yen
  EURUSD: '€',      // Euro

  // Stocks
  NVDA: '🎮',       // NVIDIA (gaming/GPU)
  TSLA: '🚗',       // Tesla (car)

  // Indices
  US500: '📊',      // S&P 500 (chart)
  DE40: '🇩🇪',      // DAX (German flag)
  NAS100: '📈',     // NASDAQ 100 (chart trending up)
};

/**
 * Get symbol for an EPIC, with fallback to first letter
 */
export function getEpicSymbol(epic: string): string {
  return EPIC_SYMBOLS[epic] ?? epic.charAt(0);
}

/**
 * Get full display name with symbol
 */
export function getEpicDisplayName(epic: string): string {
  const symbol = getEpicSymbol(epic);
  return `${symbol} ${epic}`;
}
