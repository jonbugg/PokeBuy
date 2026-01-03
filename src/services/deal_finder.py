"""Deal finder service for identifying good deals"""

from typing import List, Optional

from ..api import EbayClient
from ..models import Card, Listing, Deal
from .price_analyzer import PriceAnalyzer
from .card_parser import CardParser
from .cache import CacheService


class DealFinder:
    """Find and analyze Pokemon card deals"""

    def __init__(
        self,
        ebay_client: EbayClient,
        price_analyzer: PriceAnalyzer,
        cache_service: CacheService
    ):
        """
        Initialize deal finder

        Args:
            ebay_client: eBay API client
            price_analyzer: Price analysis service
            cache_service: Cache service
        """
        self.ebay = ebay_client
        self.price_analyzer = price_analyzer
        self.cache = cache_service
        self.card_parser = CardParser()

    def find_deals(
        self,
        search_query: str,
        discount_threshold: float = 50.0,
        max_results: int = 50,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        listing_type: Optional[str] = None
    ) -> List[Deal]:
        """
        Find Pokemon card deals on eBay

        Args:
            search_query: Search query (e.g., "Charizard PSA 10")
            discount_threshold: Minimum discount percentage to consider a deal
            max_results: Maximum number of results to return
            min_price: Minimum price filter
            max_price: Maximum price filter
            listing_type: "Auction" or "FixedPrice"

        Returns:
            List of Deal objects sorted by deal score
        """
        # Step 1: Get market value
        market_value = self.price_analyzer.get_market_value(search_query)

        if market_value is None:
            print(f"Warning: Could not determine market value for '{search_query}'")
            print("This may be because there are insufficient sold listings.")
            return []

        print(f"Market value for '{search_query}': ${market_value:.2f}")

        # Step 2: Search active listings
        max_price_filter = max_price or (market_value * (100 - discount_threshold) / 100)

        listings = self.ebay.search_active_listings(
            query=search_query,
            max_results=max_results * 2,  # Get extra to filter
            min_price=min_price,
            max_price=max_price_filter,
            listing_type=listing_type
        )

        if not listings:
            print(f"No active listings found for '{search_query}'")
            return []

        print(f"Found {len(listings)} active listings")

        # Step 3: Analyze each listing for deals
        deals = []

        for listing in listings:
            # Parse card info from listing
            card = self.card_parser.parse_listing_title(listing.title, search_query)
            card.market_value = market_value
            card.market_value_source = "ebay_sold"

            # Calculate deal metrics
            listing_price = listing.get_total_cost()
            discount_amount = market_value - listing_price
            discount_percent = (discount_amount / market_value) * 100

            # Only include if meets threshold
            if discount_percent >= discount_threshold:
                deal = Deal(
                    card=card,
                    listing=listing,
                    market_value=market_value,
                    listing_price=listing_price,
                    discount_amount=discount_amount,
                    discount_percent=discount_percent
                )
                deals.append(deal)

        # Step 4: Sort by deal score (highest first)
        deals.sort(key=lambda d: d.deal_score, reverse=True)

        print(f"Found {len(deals)} deals meeting {discount_threshold}% discount threshold")

        return deals[:max_results]

    def analyze_deal(self, listing: Listing, market_value: float) -> Optional[Deal]:
        """
        Analyze a single listing to determine if it's a deal

        Args:
            listing: eBay listing
            market_value: Known market value for the card

        Returns:
            Deal object or None if not a deal
        """
        # Parse card info
        card = self.card_parser.parse_listing_title(listing.title)
        card.market_value = market_value

        # Calculate metrics
        listing_price = listing.get_total_cost()
        discount_amount = market_value - listing_price
        discount_percent = (discount_amount / market_value) * 100

        if discount_percent <= 0:
            return None

        return Deal(
            card=card,
            listing=listing,
            market_value=market_value,
            listing_price=listing_price,
            discount_amount=discount_amount,
            discount_percent=discount_percent
        )
