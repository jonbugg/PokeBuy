"""Price analysis service for calculating market values"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import statistics

from ..api import EbayClient
from ..models import Card
from .cache import CacheService


class PriceAnalyzer:
    """Analyze market prices for Pokemon cards"""

    def __init__(self, ebay_client: EbayClient, cache_service: CacheService):
        """
        Initialize price analyzer

        Args:
            ebay_client: eBay API client
            cache_service: Cache service for storing market prices
        """
        self.ebay = ebay_client
        self.cache = cache_service

    def get_market_value(
        self,
        search_query: str,
        card: Optional[Card] = None,
        use_cache: bool = True
    ) -> Optional[float]:
        """
        Calculate market value for a card based on sold listings

        Args:
            search_query: Search query for the card
            card: Card object (optional, for cache key generation)
            use_cache: Whether to use cached values

        Returns:
            Market value in USD or None if insufficient data
        """
        # Generate cache key
        cache_key = card.get_search_key() if card else search_query.lower().replace(" ", "_")

        # Check cache first
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                if card:
                    card.market_value = cached["market_value"]
                    card.market_value_source = cached["source"]
                    card.market_value_updated = cached["updated_at"]
                return cached["market_value"]

        # Fetch sold listings
        sold_listings = self.ebay.search_sold_listings(
            query=search_query,
            days=60,
            max_results=100
        )

        if not sold_listings or len(sold_listings) < 3:
            # Insufficient data
            return None

        # Calculate market value
        market_value = self._calculate_market_value(sold_listings)

        # Cache the result
        if market_value is not None:
            self.cache.set(
                search_key=cache_key,
                market_value=market_value,
                source="ebay_sold",
                data={
                    "query": search_query,
                    "sample_size": len(sold_listings),
                    "calculated_at": datetime.now().isoformat()
                }
            )

            # Update card object if provided
            if card:
                card.market_value = market_value
                card.market_value_source = "ebay_sold"
                card.market_value_updated = datetime.now()

        return market_value

    def _calculate_market_value(self, sold_listings: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate market value from sold listings

        Uses weighted average with outlier filtering

        Args:
            sold_listings: List of sold listing dictionaries

        Returns:
            Calculated market value
        """
        if not sold_listings:
            return None

        prices = [item["price"] for item in sold_listings if item.get("price") and item["price"] > 0]

        if len(prices) < 3:
            return None

        # Remove outliers (remove top/bottom 10% if enough data)
        if len(prices) >= 10:
            prices_sorted = sorted(prices)
            # Remove bottom 10%
            bottom_cutoff = max(1, len(prices) // 10)
            # Remove top 10%
            top_cutoff = max(1, len(prices) // 10)
            prices = prices_sorted[bottom_cutoff:-top_cutoff] if top_cutoff > 0 else prices_sorted[bottom_cutoff:]

        # Calculate weighted average (recent sales weighted more)
        # For simplicity, using median which is robust to outliers
        market_value = statistics.median(prices)

        return round(market_value, 2)

    def get_price_trend(self, search_query: str, days: int = 90) -> Dict[str, Any]:
        """
        Analyze price trend for a card

        Args:
            search_query: Search query for the card
            days: Number of days to analyze

        Returns:
            Dictionary with trend information
        """
        sold_listings = self.ebay.search_sold_listings(
            query=search_query,
            days=days,
            max_results=200
        )

        if not sold_listings:
            return {
                "trend": "unknown",
                "average_price": None,
                "min_price": None,
                "max_price": None,
                "sample_size": 0
            }

        prices = [item["price"] for item in sold_listings if item.get("price")]

        if not prices:
            return {
                "trend": "unknown",
                "average_price": None,
                "min_price": None,
                "max_price": None,
                "sample_size": 0
            }

        # Calculate statistics
        avg_price = statistics.mean(prices)
        min_price = min(prices)
        max_price = max(prices)

        # Simple trend analysis: compare first half vs second half
        mid_point = len(prices) // 2
        if mid_point > 0:
            recent_avg = statistics.mean(prices[:mid_point])
            older_avg = statistics.mean(prices[mid_point:])

            if recent_avg > older_avg * 1.1:
                trend = "rising"
            elif recent_avg < older_avg * 0.9:
                trend = "falling"
            else:
                trend = "stable"
        else:
            trend = "unknown"

        return {
            "trend": trend,
            "average_price": round(avg_price, 2),
            "min_price": round(min_price, 2),
            "max_price": round(max_price, 2),
            "sample_size": len(prices)
        }
