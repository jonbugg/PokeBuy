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

@app.after_request
def after_request(response):
    """Add CORS headers to fix browser 403 errors"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

@app.route('/')
def index():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎴 PokeBuy V2 - AI-Powered Pokemon Card Deal Finder</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }

        .header p {
            font-size: 1.1em;
            opacity: 0.9;
        }

        .search-card {
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }

        .search-input-group {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }

        .search-input {
            flex: 1;
            padding: 15px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 16px;
            transition: all 0.3s;
        }

        .search-input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102,126,234,0.1);
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102,126,234,0.4);
        }

        .btn-secondary {
            background: #f5f5f5;
            color: #333;
        }

        .btn-secondary:hover {
            background: #e0e0e0;
        }

        .quick-searches {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }

        .quick-search-btn {
            padding: 10px 16px;
            background: #f8f9fa;
            border: 2px solid #e0e0e0;
            border-radius: 20px;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s;
        }

        .quick-search-btn:hover {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }

        .filters {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
        }

        .filter-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .filter-group label {
            font-size: 14px;
            font-weight: 600;
            color: #666;
        }

        .filter-group input,
        .filter-group select {
            padding: 10px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
        }

        .loading {
            display: none;
            text-align: center;
            padding: 40px;
            color: white;
        }

        .loading.active {
            display: block;
        }

        .spinner {
            border: 4px solid rgba(255,255,255,0.3);
            border-top: 4px solid white;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .results {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }

        .deal-card {
            background: white;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            transition: all 0.3s;
        }

        .deal-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.2);
        }

        .deal-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 700;
            color: white;
            z-index: 1;
        }

        .badge-hot { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
        .badge-star { background: linear-gradient(135deg, #ffd89b 0%, #19547b 100%); }
        .badge-good { background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); color: #333; }

        .card-image-container {
            position: relative;
            aspect-ratio: 5/7;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .card-image {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }

        .deal-info {
            padding: 20px;
        }

        .card-name {
            font-size: 16px;
            font-weight: 700;
            color: #333;
            margin-bottom: 8px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .card-set {
            font-size: 13px;
            color: #666;
            margin-bottom: 15px;
        }

        .price-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e0e0e0;
        }

        .price-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .price-label {
            font-size: 11px;
            text-transform: uppercase;
            color: #999;
            font-weight: 600;
        }

        .price-value {
            font-size: 18px;
            font-weight: 700;
            color: #333;
        }

        .market-price { color: #666; }
        .listing-price { color: #667eea; }

        .savings {
            background: #f0f9ff;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 15px;
        }

        .savings-amount {
            font-size: 20px;
            font-weight: 700;
            color: #10b981;
        }

        .discount-percent {
            font-size: 14px;
            color: #666;
            margin-top: 4px;
        }

        .deal-meta {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: #999;
            margin-bottom: 15px;
        }

        .confidence-score {
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .confidence-bar {
            width: 50px;
            height: 4px;
            background: #e0e0e0;
            border-radius: 2px;
            overflow: hidden;
        }

        .confidence-fill {
            height: 100%;
            background: linear-gradient(90deg, #10b981 0%, #059669 100%);
            transition: width 0.3s;
        }

        .view-listing-btn {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }

        .view-listing-btn:hover {
            transform: scale(1.02);
            box-shadow: 0 4px 12px rgba(102,126,234,0.4);
        }

        .no-results {
            text-align: center;
            padding: 60px 20px;
            color: white;
        }

        .no-results h2 {
            font-size: 2em;
            margin-bottom: 10px;
        }

        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.8em;
            }

            .search-input-group {
                flex-direction: column;
            }

            .results {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎴 PokeBuy V2</h1>
            <p>AI-Powered Pokemon Card Deal Finder</p>
        </div>

        <div class="search-card">
            <div class="search-input-group">
                <input
                    type="text"
                    id="searchInput"
                    class="search-input"
                    placeholder="Search for Pokemon cards... (e.g., 'Charizard PSA 10', 'vintage Pikachu')"
                    onkeypress="if(event.key === 'Enter') search()"
                >
                <button class="btn btn-primary" onclick="search()">
                    🔍 Search
                </button>
            </div>

            <div class="quick-searches">
                <button class="quick-search-btn" onclick="quickSearch('Charizard PSA 10')">🔥 Charizard PSA 10</button>
                <button class="quick-search-btn" onclick="quickSearch('Pikachu')">⚡ Pikachu</button>
                <button class="quick-search-btn" onclick="quickSearch('Umbreon alt art')">🌙 Umbreon Alt Art</button>
                <button class="quick-search-btn" onclick="quickSearch('Base Set holo')">✨ Base Set Holo</button>
                <button class="quick-search-btn" onclick="quickSearch('Eeveelution')">💎 Eeveelution</button>
            </div>

            <details>
                <summary style="cursor: pointer; font-weight: 600; margin-bottom: 10px;">⚙️ Advanced Filters</summary>
                <div class="filters">
                    <div class="filter-group">
                        <label for="minDiscount">Min Discount %</label>
                        <input type="number" id="minDiscount" value="50" min="0" max="100">
                    </div>
                    <div class="filter-group">
                        <label for="maxResults">Max Results</label>
                        <input type="number" id="maxResults" value="20" min="1" max="50">
                    </div>
                </div>
            </details>
        </div>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <h2>Finding deals...</h2>
            <p>Claude AI is analyzing Pokemon cards and eBay listings</p>
        </div>

        <div id="results" class="results"></div>

        <div id="noResults" class="no-results" style="display: none;">
            <h2>😔 No deals found</h2>
            <p>Try lowering the discount threshold or searching for different cards</p>
        </div>
    </div>

    <script>
        function quickSearch(query) {
            document.getElementById('searchInput').value = query;
            search();
        }

        async function search() {
            const query = document.getElementById('searchInput').value.trim();
            if (!query) {
                alert('Please enter a search term');
                return;
            }

            const minDiscount = parseFloat(document.getElementById('minDiscount').value) || 50;
            const maxResults = parseInt(document.getElementById('maxResults').value) || 20;

            // Show loading
            document.getElementById('loading').classList.add('active');
            document.getElementById('results').innerHTML = '';
            document.getElementById('noResults').style.display = 'none';

            try {
                const response = await fetch('/api/search', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        query: query,
                        min_discount: minDiscount,
                        max_results: maxResults
                    })
                });

                const data = await response.json();

                // Hide loading
                document.getElementById('loading').classList.remove('active');

                if (data.success && data.deals.length > 0) {
                    displayResults(data.deals);
                } else {
                    document.getElementById('noResults').style.display = 'block';
                }
            } catch (error) {
                console.error('Search error:', error);
                document.getElementById('loading').classList.remove('active');
                alert('Error searching for deals. Please check the console for details.');
            }
        }

        function displayResults(deals) {
            const resultsContainer = document.getElementById('results');
            resultsContainer.innerHTML = deals.map(deal => {
                const dealQuality = getDealQuality(deal.discount_percent);
                const confidencePercent = deal.confidence || 0;

                return `
                    <div class="deal-card">
                        <div class="card-image-container">
                            <div class="deal-badge badge-${dealQuality.class}">${dealQuality.emoji} ${dealQuality.label}</div>
                            ${deal.card.image ?
                                `<img src="${deal.card.image}" alt="${deal.card.name}" class="card-image">` :
                                `<div style="color: white; font-size: 48px;">🎴</div>`
                            }
                        </div>
                        <div class="deal-info">
                            <div class="card-name">${deal.listing.title}</div>
                            <div class="card-set">${deal.card.name} • ${deal.card.set} #${deal.card.number}</div>

                            <div class="price-grid">
                                <div class="price-item">
                                    <span class="price-label">Market Value</span>
                                    <span class="price-value market-price">$${deal.market_price.toFixed(2)}</span>
                                </div>
                                <div class="price-item">
                                    <span class="price-label">Current Price</span>
                                    <span class="price-value listing-price">$${deal.listing.price.toFixed(2)}</span>
                                </div>
                            </div>

                            <div class="savings">
                                <div class="savings-amount">💰 Save $${deal.savings.toFixed(2)}</div>
                                <div class="discount-percent">${deal.discount_percent.toFixed(0)}% off market price</div>
                            </div>

                            <div class="deal-meta">
                                <div class="confidence-score">
                                    <span>🎯 ${confidencePercent}% match</span>
                                    <div class="confidence-bar">
                                        <div class="confidence-fill" style="width: ${confidencePercent}%"></div>
                                    </div>
                                </div>
                            </div>

                            <button class="view-listing-btn" onclick="window.open('${deal.listing.url}', '_blank')">
                                View on eBay →
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function getDealQuality(discountPercent) {
            if (discountPercent >= 70) {
                return { emoji: '🔥', label: 'HOT DEAL', class: 'hot' };
            } else if (discountPercent >= 60) {
                return { emoji: '⭐', label: 'STAR DEAL', class: 'star' };
            } else {
                return { emoji: '💎', label: 'GOOD DEAL', class: 'good' };
            }
        }
    </script>
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
