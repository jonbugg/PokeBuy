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
        # Step 1: Search active listings first
        listings = self.ebay.search_active_listings(
            query=search_query,
            max_results=max_results * 2,  # Get extra to filter
            min_price=min_price,
            max_price=max_price,
            listing_type=listing_type
        )

        if not listings:
            print(f"No active listings found for '{search_query}'")
            return []

        print(f"Found {len(listings)} active listings")

        # Step 2: For each listing, look up its individual market value
        deals = []
        price_cache = {}  # Cache prices for similar titles to avoid duplicate lookups
        
        # Limit lookups to avoid long wait times (each lookup takes 1-3 seconds)
        max_lookups = min(len(listings), 15)
        print(f"Looking up market prices (checking up to {max_lookups} unique cards)...")

        for i, listing in enumerate(listings):
            # Parse card info from listing title
            card = self.card_parser.parse_listing_title(listing.title, search_query)
            
            # Create a simplified search key from the listing title
            # Extract key terms for price lookup
            price_lookup_key = self._create_price_lookup_key(listing.title)
            
            # Check if we've already looked up this price
            if price_lookup_key in price_cache:
                market_value = price_cache[price_lookup_key]
            elif len(price_cache) < max_lookups:
                # Look up market value for this specific card
                print(f"  [{len(price_cache)+1}/{max_lookups}] Looking up: {listing.title[:50]}...")
                tcg_result = self.ebay.get_tcg_market_price(listing.title)
                if tcg_result:
                    market_value = tcg_result['market_value']
                    card.market_value_source = f"pricecharting ({tcg_result.get('card_name', '')[:30]})"
                    print(f"         -> ${market_value:.2f}")
                else:
                    market_value = None
                    card.market_value_source = "unknown"
                    print(f"         -> No price found")
                
                # Cache the result
                price_cache[price_lookup_key] = market_value
            else:
                # Hit max lookups, skip price lookup
                market_value = None
                card.market_value_source = "not looked up"

            card.market_value = market_value

            # Calculate deal metrics
            listing_price = listing.get_total_cost()
            
            if market_value and market_value > 0:
                discount_amount = market_value - listing_price
                discount_percent = (discount_amount / market_value) * 100
            else:
                discount_amount = 0.0
                discount_percent = 0.0
                market_value = 0.0

            deal = Deal(
                card=card,
                listing=listing,
                market_value=market_value,
                listing_price=listing_price,
                discount_amount=discount_amount,
                discount_percent=discount_percent
            )
            deals.append(deal)

        # Step 3: Sort by discount percentage (best deals first)
        deals.sort(key=lambda d: d.discount_percent, reverse=True)
        
        # Count deals meeting threshold
        deals_meeting_threshold = len([d for d in deals if d.discount_percent >= discount_threshold])
        deals_with_price = len([d for d in deals if d.market_value > 0])
        
        print(f"Found prices for {deals_with_price}/{len(deals)} listings")
        print(f"{deals_meeting_threshold} listings meet {discount_threshold}% discount threshold")

        return deals[:max_results]

    def _create_price_lookup_key(self, title: str) -> str:
        """
        Create a simplified key for caching price lookups.
        Extracts the most important terms from a listing title.
        """
        import re
        
        # Lowercase and clean
        key = title.lower()
        
        # Remove common filler words
        filler_words = ['pokemon', 'tcg', 'card', 'cards', 'the', 'a', 'an', 'and', 'or', 'for',
                       'lot', 'bundle', 'set', 'collection', 'pick', 'choose', 'your',
                       'nm', 'mint', 'near', 'excellent', 'good', 'played', 'lp', 'mp', 'hp',
                       'free', 'shipping', 'fast', 'same', 'day', 'new', 'sealed']
        
        words = key.split()
        key_words = [w for w in words if w not in filler_words and len(w) > 2]
        
        # Take first 5 significant words
        return ' '.join(key_words[:5])

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
