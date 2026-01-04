#!/usr/bin/env python3
"""
PokeBuy V2 - AI-Powered Pokemon Card Deal Finder
Built with Pokemon TCG API + Claude AI for accuracy
"""

import os
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

import requests
from anthropic import Anthropic
from flask import Flask, render_template_string, jsonify, request

# ============================================================================
# CONFIGURATION
# ============================================================================

EBAY_APP_ID = os.environ.get("EBAY_APP_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
POKEMON_TCG_API_KEY = os.environ.get("POKEMON_TCG_API_KEY", "")  # Optional but recommended
POKEMON_CATEGORY_ID = "183454"

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class PokemonCard:
    """Represents a specific Pokemon card from the TCG database"""
    id: str
    name: str
    set_name: str
    set_id: str
    number: str
    rarity: Optional[str] = None
    image_url: Optional[str] = None
    tcg_market_price: Optional[float] = None  # From Pokemon TCG API

    def get_full_name(self) -> str:
        return f"{self.name} {self.set_name} {self.number}"

@dataclass
class EbayListing:
    """eBay listing data"""
    item_id: str
    title: str
    price: float
    url: str
    image_url: Optional[str] = None
    condition: Optional[str] = None
    seller_feedback: Optional[float] = None
    shipping_cost: Optional[float] = None
    is_auction: bool = False

@dataclass
class CardDeal:
    """A matched deal between eBay listing and Pokemon card"""
    card: PokemonCard
    listing: EbayListing
    market_price: float
    discount_percent: float
    savings: float
    confidence_score: float  # How confident are we in the match?
    ai_insight: str = ""

# ============================================================================
# POKEMON TCG API CLIENT
# ============================================================================

class PokemonTCGClient:
    """Client for Pokemon TCG API - the source of truth for cards"""

    def __init__(self, api_key: Optional[str] = None):
        self.base_url = "https://api.pokemontcg.io/v2"
        self.headers = {"X-Api-Key": api_key} if api_key else {}

    def search_cards(self, query: str, max_results: int = 20) -> List[PokemonCard]:
        """
        Search for Pokemon cards in the TCG database

        Query examples:
        - "Charizard"
        - "name:Charizard set.name:Base"
        - "name:Pikachu rarity:Rare"
        """
        try:
            url = f"{self.base_url}/cards"
            params = {
                "q": query,
                "pageSize": max_results,
                "orderBy": "-set.releaseDate"  # Newest first
            }

            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            cards = []
            for card_data in data.get("data", []):
                card = self._parse_card(card_data)
                if card:
                    cards.append(card)

            print(f"Found {len(cards)} cards in Pokemon TCG database")
            return cards

        except Exception as e:
            print(f"Pokemon TCG API error: {e}")
            return []

    def _parse_card(self, data: Dict) -> Optional[PokemonCard]:
        """Parse card data from API response"""
        try:
            # Get market price from tcgplayer if available
            market_price = None
            if "tcgplayer" in data and "prices" in data["tcgplayer"]:
                prices = data["tcgplayer"]["prices"]
                # Try to get the most relevant price tier
                for tier in ["holofoil", "reverseHolofoil", "normal", "1stEditionHolofoil"]:
                    if tier in prices and "market" in prices[tier]:
                        market_price = prices[tier]["market"]
                        break

            return PokemonCard(
                id=data["id"],
                name=data["name"],
                set_name=data["set"]["name"],
                set_id=data["set"]["id"],
                number=data["number"],
                rarity=data.get("rarity"),
                image_url=data.get("images", {}).get("small"),
                tcg_market_price=market_price
            )
        except Exception as e:
            print(f"Error parsing card: {e}")
            return None

# ============================================================================
# EBAY CLIENT (Simplified)
# ============================================================================

class EbayClient:
    """eBay Finding API client"""

    def __init__(self, app_id: str):
        self.app_id = app_id
        self.api_url = "https://svcs.ebay.com/services/search/FindingService/v1"

    def search(self, query: str, max_results: int = 50) -> List[EbayListing]:
        """Search eBay for listings"""
        params = {
            "OPERATION-NAME": "findItemsAdvanced",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": self.app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "keywords": query,
            "categoryId": POKEMON_CATEGORY_ID,
            "paginationInput.entriesPerPage": str(min(max_results, 100)),
            "sortOrder": "PricePlusShippingLowest",
        }

        try:
            response = requests.get(self.api_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            listings = []
            items = data.get("findItemsAdvancedResponse", [{}])[0] \
                       .get("searchResult", [{}])[0] \
                       .get("item", [])

            for item in items:
                listing = self._parse_listing(item)
                if listing:
                    listings.append(listing)

            print(f"Found {len(listings)} eBay listings for '{query}'")
            return listings

        except Exception as e:
            print(f"eBay API error: {e}")
            return []

    def _parse_listing(self, item: Dict) -> Optional[EbayListing]:
        """Parse eBay listing from API response"""
        try:
            price_info = item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0]
            price = float(price_info.get("__value__", 0))

            shipping_info = item.get("shippingInfo", [{}])[0]
            shipping_cost_info = shipping_info.get("shippingServiceCost", [{}])[0]
            shipping_cost = float(shipping_cost_info.get("__value__", 0))

            seller_info = item.get("sellerInfo", [{}])[0]
            seller_feedback = float(seller_info.get("positiveFeedbackPercent", [0])[0])

            listing_type = item.get("listingInfo", [{}])[0].get("listingType", [""])[0]

            return EbayListing(
                item_id=item.get("itemId", [""])[0],
                title=item.get("title", [""])[0],
                price=price,
                url=item.get("viewItemURL", [""])[0],
                image_url=item.get("galleryURL", [""])[0] or None,
                condition=item.get("condition", [{}])[0].get("conditionDisplayName", [""])[0] or None,
                seller_feedback=seller_feedback if seller_feedback > 0 else None,
                shipping_cost=shipping_cost if shipping_cost > 0 else None,
                is_auction=listing_type.lower() in ["auction", "chinese"]
            )
        except:
            return None

# ============================================================================
# CLAUDE AI SERVICE (Enhanced)
# ============================================================================

class ClaudeAI:
    """Claude AI for intelligent card matching and analysis"""

    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key) if api_key else None

    def identify_cards_from_query(self, user_query: str) -> List[str]:
        """
        Convert natural language query into specific Pokemon TCG API search queries

        Example:
        "graded vintage Charizard" → ["name:Charizard set.name:Base", "name:Charizard set.name:Jungle"]
        """
        if not self.client:
            return [user_query]  # Fallback

        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": f"""You are a Pokemon card expert. Convert this user query into Pokemon TCG API search queries.

User query: "{user_query}"

Generate 1-3 specific search queries for the Pokemon TCG API. Use this syntax:
- name:CardName - Search by card name
- set.name:SetName - Search by set (Base, Jungle, Fossil, etc.)
- rarity:Rare - Search by rarity
- types:Fire - Search by type

Examples:
"vintage Charizard" → ["name:Charizard set.name:Base", "name:Charizard set.name:Jungle"]
"graded Pikachu PSA 10" → ["name:Pikachu"]
"modern Umbreon alt art" → ["name:Umbreon rarity:\"Rare Holo\""]

Return ONLY a JSON array of search queries, nothing else.

Queries:"""
                }]
            )

            response_text = message.content[0].text.strip()
            # Parse JSON array
            queries = json.loads(response_text)
            print(f"Claude identified {len(queries)} card searches from '{user_query}'")
            return queries if isinstance(queries, list) else [user_query]

        except Exception as e:
            print(f"Claude card identification error: {e}")
            return [user_query]

    def match_listing_to_card(self, listing_title: str, cards: List[PokemonCard]) -> Optional[tuple[PokemonCard, float]]:
        """
        Match an eBay listing to the correct Pokemon card from candidates

        Returns: (matched_card, confidence_score) or None
        """
        if not self.client or not cards:
            return None

        try:
            card_options = "\n".join([
                f"{i}: {c.get_full_name()} - {c.rarity}"
                for i, c in enumerate(cards[:10])  # Max 10 to avoid token limits
            ])

            message = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"""Match this eBay listing to the correct Pokemon card.

eBay Listing: "{listing_title}"

Card Options:
{card_options}

Which card does this listing match? Consider:
- Exact card name
- Set name
- Card number if mentioned
- Grading (PSA/BGS/CGC) doesn't change the base card

Return JSON: {{"card_index": N, "confidence": 0-100}}
If no good match, return {{"card_index": -1, "confidence": 0}}

Response:"""
                }]
            )

            response = json.loads(message.content[0].text.strip())
            card_index = response.get("card_index", -1)
            confidence = response.get("confidence", 0) / 100.0

            if card_index >= 0 and card_index < len(cards) and confidence > 0.5:
                return (cards[card_index], confidence)

            return None

        except Exception as e:
            print(f"Claude matching error: {e}")
            return None

    def generate_ebay_search_queries(self, card: PokemonCard) -> List[str]:
        """Generate optimized eBay search queries for a specific card"""
        queries = [
            f"{card.name} {card.set_name} {card.number}",
            f"{card.name} {card.set_name}",
            f"{card.name} {card.number}",
        ]
        return queries[:2]  # Return top 2

# ============================================================================
# DEAL FINDER V2
# ============================================================================

class DealFinderV2:
    """New intelligent deal finder using Pokemon TCG API + Claude"""

    def __init__(self, ebay: EbayClient, tcg: PokemonTCGClient, claude: ClaudeAI):
        self.ebay = ebay
        self.tcg = tcg
        self.claude = claude

    def find_deals(self, user_query: str, min_discount: float = 50, max_results: int = 20) -> List[CardDeal]:
        """
        Find Pokemon card deals using intelligent matching

        Process:
        1. Claude identifies specific cards from user query
        2. Pokemon TCG API gets card data + market prices
        3. Generate targeted eBay searches
        4. Claude matches listings to exact cards
        5. Calculate true deals
        """
        print(f"\n🔍 Searching for: {user_query}")

        # Step 1: Claude identifies what cards to search for
        tcg_queries = self.claude.identify_cards_from_query(user_query)

        # Step 2: Get cards from Pokemon TCG database
        all_cards = []
        for query in tcg_queries[:3]:  # Limit to 3 queries
            cards = self.tcg.search_cards(query, max_results=10)
            all_cards.extend(cards)

        if not all_cards:
            print("❌ No cards found in Pokemon TCG database")
            return []

        print(f"✅ Found {len(all_cards)} cards in database")

        # Step 3: Search eBay for each card
        all_listings = []
        for card in all_cards[:5]:  # Limit to top 5 cards
            queries = self.claude.generate_ebay_search_queries(card)
            for ebay_query in queries[:1]:  # 1 query per card
                listings = self.ebay.search(ebay_query, max_results=20)
                all_listings.extend([(card, listing) for listing in listings])

        print(f"✅ Found {len(all_listings)} eBay listings")

        # Step 4: Match listings to cards and calculate deals
        deals = []
        for card, listing in all_listings:
            # Use Claude to verify this listing matches this card
            match_result = self.claude.match_listing_to_card(listing.title, [card])

            if not match_result:
                continue  # Not a match

            matched_card, confidence = match_result

            # Get market price (prefer TCG API, fallback to 0)
            market_price = matched_card.tcg_market_price or 0

            if market_price == 0:
                continue  # Can't calculate deal without market price

            # Calculate deal
            total_price = listing.price + (listing.shipping_cost or 0)
            discount_percent = ((market_price - total_price) / market_price) * 100

            if discount_percent >= min_discount:
                deal = CardDeal(
                    card=matched_card,
                    listing=listing,
                    market_price=market_price,
                    discount_percent=discount_percent,
                    savings=market_price - total_price,
                    confidence_score=confidence
                )
                deals.append(deal)

        # Sort by savings (highest first)
        deals.sort(key=lambda d: d.savings, reverse=True)

        print(f"✅ Found {len(deals)} deals with {min_discount}%+ discount")
        return deals[:max_results]

# ============================================================================
# FLASK WEB APP
# ============================================================================

app = Flask(__name__)

@app.route('/')
def index():
    return """
    <html>
    <body style="font-family: sans-serif; max-width: 800px; margin: 50px auto;">
        <h1>🎴 PokeBuy V2 - AI-Powered Deal Finder</h1>
        <p>Test the API:</p>
        <pre>
POST /api/search
{
  "query": "vintage Charizard",
  "min_discount": 50,
  "max_results": 10
}
        </pre>
    </body>
    </html>
    """

@app.route('/api/search', methods=['POST'])
def search():
    data = request.json
    query = data.get('query', '')
    min_discount = float(data.get('min_discount', 50))
    max_results = int(data.get('max_results', 20))

    if not query:
        return jsonify({'error': 'Query required'}), 400

    if not EBAY_APP_ID or not ANTHROPIC_API_KEY:
        return jsonify({'error': 'API keys not configured'}), 500

    # Initialize services
    ebay = EbayClient(EBAY_APP_ID)
    tcg = PokemonTCGClient(POKEMON_TCG_API_KEY)
    claude = ClaudeAI(ANTHROPIC_API_KEY)
    finder = DealFinderV2(ebay, tcg, claude)

    # Find deals
    deals = finder.find_deals(query, min_discount, max_results)

    # Convert to JSON
    deals_json = [
        {
            'card': {
                'name': d.card.name,
                'set': d.card.set_name,
                'number': d.card.number,
                'image': d.card.image_url
            },
            'listing': {
                'title': d.listing.title,
                'price': d.listing.price,
                'url': d.listing.url,
                'image': d.listing.image_url
            },
            'market_price': d.market_price,
            'discount_percent': round(d.discount_percent, 1),
            'savings': round(d.savings, 2),
            'confidence': round(d.confidence_score * 100)
        }
        for d in deals
    ]

    return jsonify({
        'success': True,
        'query': query,
        'deals': deals_json,
        'count': len(deals_json)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
