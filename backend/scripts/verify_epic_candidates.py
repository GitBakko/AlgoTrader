"""
Verify availability of 12 EPIC candidates on Capital.com demo API.
Tests each candidate asset and retrieves market details.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend src to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import httpx
from loguru import logger
from tabulate import tabulate

# Capital.com demo credentials
API_URL = "https://demo-api-capital.backend-capital.com"
API_KEY = "OLuftJqsVJyFLGsu"
EMAIL = "bakko.posta@gmail.com"
PASSWORD = "PassBakkoCapitalApi1983@"

# 12 EPIC candidates to verify
CANDIDATES = {
    "Crypto": [
        ("SOLUSD", "Solana", ["SOLANA", "SOL/USD", "SOLUSD", "SOL"]),
        ("ETHUSD", "Ethereum", ["ETHEREUM", "ETH/USD", "ETHUSD", "ETH"]),
        ("BNBUSD", "Binance Coin", ["BNB", "BNB/USD", "BNBUSD", "BINANCE"]),
        ("DOGUSD", "Dogecoin", ["DOGECOIN", "DOGE/USD", "DOGUSD", "DOGE"]),
        ("DASHUSD", "Dash", ["DASH", "DASH/USD", "DASHUSD"]),
        ("ICPUSD", "Internet Computer", ["ICP", "ICP/USD", "ICPUSD", "INTERNET COMPUTER"]),
    ],
    "Commodities": [
        ("NATGAS", "Natural Gas", ["NATURAL GAS", "NATGAS", "NG", "GAS"]),
        ("COPPER", "Copper", ["COPPER", "HG", "XCULUSD"]),
        ("PLATINUM", "Platinum", ["PLATINUM", "XPTUSD", "PLATINIUM"]),
    ],
    "Forex": [
        ("GBPUSD", "Cable", ["GBP/USD", "GBPUSD", "CABLE"]),
        ("USDJPY", "Dollar-Yen", ["USD/JPY", "USDJPY"]),
    ],
    "Indices": [
        ("NAS100", "Nasdaq 100", ["NASDAQ 100", "NAS100", "US TECH 100", "NDX"]),
    ],
}


class CapitalAPITester:
    """Test Capital.com API for EPIC availability."""

    def __init__(self):
        self.api_url = API_URL
        self.api_key = API_KEY
        self.email = EMAIL
        self.password = PASSWORD
        self.cst_token = None
        self.security_token = None
        self.client = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(timeout=30.0)
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    async def authenticate(self):
        """Authenticate and get session tokens."""
        logger.info("Authenticating with Capital.com demo API...")

        headers = {
            "X-CAP-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {"identifier": self.email, "password": self.password}

        try:
            response = await self.client.post(
                f"{self.api_url}/api/v1/session", headers=headers, json=payload
            )

            if response.status_code == 200:
                self.cst_token = response.headers.get("CST")
                self.security_token = response.headers.get("X-SECURITY-TOKEN")
                logger.success("Authentication successful!")
                return True
            else:
                logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    def _get_headers(self):
        """Get authenticated request headers."""
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.cst_token,
            "X-SECURITY-TOKEN": self.security_token,
        }

    async def search_market(self, search_term: str) -> list[dict]:
        """
        Search for markets matching search term.

        Args:
            search_term: Term to search (e.g., "SOLANA", "NATURAL GAS")

        Returns:
            List of matching markets
        """
        try:
            response = await self.client.get(
                f"{self.api_url}/api/v1/markets",
                headers=self._get_headers(),
                params={"searchTerm": search_term},
            )

            if response.status_code == 200:
                data = response.json()
                markets = data.get("markets", [])
                logger.debug(f"Found {len(markets)} markets for '{search_term}'")
                return markets
            else:
                logger.warning(
                    f"Search failed for '{search_term}': {response.status_code}"
                )
                return []

        except Exception as e:
            logger.error(f"Search error for '{search_term}': {e}")
            return []

    async def get_market_details(self, epic: str) -> dict | None:
        """
        Get detailed market information.

        Args:
            epic: Market EPIC code

        Returns:
            Market details or None if not found
        """
        try:
            response = await self.client.get(
                f"{self.api_url}/api/v1/markets/{epic}",
                headers=self._get_headers(),
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.debug(f"Market details failed for '{epic}': {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Market details error for '{epic}': {e}")
            return None

    async def verify_epic_candidate(
        self, internal_name: str, display_name: str, search_terms: list[str]
    ) -> dict:
        """
        Verify if an EPIC candidate is available on Capital.com.

        Args:
            internal_name: Internal MANTIS AI name (e.g., "SOLUSD")
            display_name: Human-readable name (e.g., "Solana")
            search_terms: List of possible search terms to try

        Returns:
            Verification result with details
        """
        logger.info(f"Verifying {internal_name} ({display_name})...")

        result = {
            "internal_name": internal_name,
            "display_name": display_name,
            "found": False,
            "epic_code": None,
            "market_name": None,
            "spread": None,
            "min_size": None,
            "available": False,
            "market_status": None,
        }

        # Try each search term
        for term in search_terms:
            markets = await self.search_market(term)

            if not markets:
                continue

            # Take first matching market
            market = markets[0]
            epic_code = market.get("epic")

            if not epic_code:
                continue

            # Get detailed market info
            details = await self.get_market_details(epic_code)

            if details:
                instrument = details.get("instrument", {})
                dealing_rules = details.get("dealingRules", {})
                snapshot = details.get("snapshot", {})

                result.update(
                    {
                        "found": True,
                        "epic_code": epic_code,
                        "market_name": instrument.get("name"),
                        "spread": snapshot.get("scalingFactor"),  # Spread info
                        "min_size": dealing_rules.get("minDealSize", {}).get("value"),
                        "available": snapshot.get("marketStatus") == "TRADEABLE",
                        "market_status": snapshot.get("marketStatus"),
                    }
                )

                logger.success(
                    f"✓ Found {internal_name}: epic={epic_code}, "
                    f"status={result['market_status']}"
                )
                break

        if not result["found"]:
            logger.warning(f"✗ {internal_name} not found on Capital.com")

        return result


async def main():
    """Main verification script."""
    logger.info("=" * 80)
    logger.info("MANTIS AI - Capital.com EPIC Candidates Verification")
    logger.info("=" * 80)

    results_by_category = {}

    async with CapitalAPITester() as tester:
        for category, candidates in CANDIDATES.items():
            logger.info(f"\n📊 Testing {category} assets...")
            results_by_category[category] = []

            for internal_name, display_name, search_terms in candidates:
                result = await tester.verify_epic_candidate(
                    internal_name, display_name, search_terms
                )
                results_by_category[category].append(result)

                # Small delay to respect rate limits
                await asyncio.sleep(0.2)

    # Print summary table by category
    logger.info("\n" + "=" * 80)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 80)

    all_results = []
    for category, results in results_by_category.items():
        logger.info(f"\n{category.upper()}")
        logger.info("-" * 80)

        table_data = []
        for r in results:
            status_icon = "✓" if r["found"] and r["available"] else "✗"
            table_data.append(
                [
                    status_icon,
                    r["internal_name"],
                    r["epic_code"] or "N/A",
                    r["market_name"] or "Not Found",
                    r["market_status"] or "N/A",
                    r["min_size"] or "N/A",
                ]
            )
            all_results.append(r)

        headers = ["Status", "MANTIS Name", "Capital Epic", "Market Name", "Status", "Min Size"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))

    # Final statistics
    total = len(all_results)
    found = sum(1 for r in all_results if r["found"])
    available = sum(1 for r in all_results if r["available"])

    logger.info("\n" + "=" * 80)
    logger.info("FINAL STATISTICS")
    logger.info("=" * 80)
    logger.info(f"Total candidates: {total}")
    logger.info(f"Found on Capital.com: {found} ({found/total*100:.1f}%)")
    logger.info(f"Available for trading: {available} ({available/total*100:.1f}%)")

    # Save results to JSON
    import json
    from datetime import datetime

    output_file = backend_dir / "data" / "epic_verification_results.json"
    output_file.parent.mkdir(exist_ok=True)

    output_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_candidates": total,
        "found": found,
        "available": available,
        "results_by_category": results_by_category,
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.success(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
