"""Test if MarketauxClient is in app state."""
import httpx

# Test the actual endpoint
response = httpx.get("http://127.0.0.1:8000/api/news/NVDA?limit=3&days=7")
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# Check if we get an error about service not available
if response.json().get("success") and not response.json().get("data"):
    print("\n❌ Getting empty data - client might be returning empty list")
elif not response.json().get("success"):
    print(f"\n❌ Error: {response.json().get('error')}")
else:
    print("\n✅ Got data!")
