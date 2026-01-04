#!/usr/bin/env python3
"""
PokeBuy - Pokemon Card Deal Finder (Standalone Version)
Single-file version for easy deployment to Replit, Railway, etc.

Just copy this entire file and you're ready to go!
"""

import os
import re
import sqlite3
import json
import statistics
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, jsonify, request
from anthropic import Anthropic

# ============================================================================
# CONFIGURATION
# ============================================================================

EBAY_APP_ID = os.environ.get("EBAY_APP_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
POKEMON_CATEGORY_ID = "183454"
CACHE_EXPIRY_HOURS = 48
DEFAULT_DISCOUNT_THRESHOLD = 50

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Listing:
    item_id: str
    title: str
    price: float
    currency: str = "USD"
    listing_type: str = "FixedPrice"
    url: str = ""
    image_url: Optional[str] = None
    shipping_cost: Optional[float] = None
    free_shipping: bool = False
    seller_feedback_percent: Optional[float] = None
    condition: Optional[str] = None

    def get_total_cost(self) -> float:
        shipping = self.shipping_cost if self.shipping_cost and not self.free_shipping else 0
        return self.price + shipping

@dataclass
class Deal:
    listing: Listing
    market_value: float
    discount_percent: float
    discount_amount: float
    deal_score: float = 0.0
    is_hot_deal: bool = False
    is_star_deal: bool = False

    def __post_init__(self):
        if self.discount_percent >= 60:
            self.is_hot_deal = True
        elif self.discount_percent >= 50:
            self.is_star_deal = True
        self.deal_score = self._calculate_score()

    def _calculate_score(self) -> float:
        score = 0.0
        score += min(40, (self.discount_percent / 100) * 40)
        score += min(30, (self.discount_amount / 200) * 30)
        if self.listing.seller_feedback_percent and self.listing.seller_feedback_percent >= 98:
            score += 10
        if self.listing.free_shipping or (self.listing.shipping_cost and self.listing.shipping_cost < 5):
            score += 5
        if self.listing.listing_type != "Auction":
            score += 5
        if self.market_value >= 500:
            score += 10
        elif self.market_value >= 200:
            score += 7
        return round(score, 2)

    def get_emoji(self) -> str:
        if self.is_hot_deal:
            return "🔥"
        elif self.is_star_deal:
            return "⭐"
        elif self.discount_percent >= 40:
            return "💎"
        return "📦"

# ============================================================================
# EBAY API CLIENT
# ============================================================================

class EbayClient:
    def __init__(self, app_id: str):
        self.app_id = app_id
        self.finding_api_url = "https://svcs.ebay.com/services/search/FindingService/v1"

    def search_active_listings(self, query: str, max_results: int = 50,
                               max_price: Optional[float] = None) -> List[Listing]:
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

        if max_price:
            params["itemFilter(0).name"] = "MaxPrice"
            params["itemFilter(0).value"] = str(max_price)

        try:
            print(f"Searching eBay for: {query}")
            response = requests.get(self.finding_api_url, params=params, timeout=45)
            response.raise_for_status()
            data = response.json()
            listings = self._parse_response(data)
            print(f"eBay API returned {len(listings)} listings")
            return listings
        except Exception as e:
            print(f"Error searching eBay: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _parse_response(self, data: Dict) -> List[Listing]:
        listings = []
        try:
            search_result = data.get("findItemsAdvancedResponse", [{}])[0]
            items = search_result.get("searchResult", [{}])[0].get("item", [])

            for item in items:
                try:
                    item_id = item.get("itemId", [""])[0]
                    title = item.get("title", [""])[0]

                    price_info = item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0]
                    price = float(price_info.get("__value__", 0))

                    listing_info = item.get("listingInfo", [{}])[0]
                    listing_type = listing_info.get("listingType", ["FixedPrice"])[0]

                    url = item.get("viewItemURL", [""])[0]
                    image_url = item.get("galleryURL", [""])[0]

                    shipping_info = item.get("shippingInfo", [{}])[0]
                    shipping_cost_info = shipping_info.get("shippingServiceCost", [{}])[0]
                    shipping_cost = float(shipping_cost_info.get("__value__", 0))

                    condition_info = item.get("condition", [{}])[0]
                    condition = condition_info.get("conditionDisplayName", [""])[0]

                    seller_info = item.get("sellerInfo", [{}])[0]
                    seller_feedback_percent = float(seller_info.get("positiveFeedbackPercent", [0])[0])

                    listings.append(Listing(
                        item_id=item_id,
                        title=title,
                        price=price,
                        listing_type=listing_type,
                        url=url,
                        image_url=image_url if image_url else None,
                        shipping_cost=shipping_cost if shipping_cost > 0 else None,
                        free_shipping=shipping_cost == 0,
                        condition=condition if condition else None,
                        seller_feedback_percent=seller_feedback_percent if seller_feedback_percent else None,
                    ))
                except:
                    continue
        except:
            pass
        return listings

    def search_sold_listings(self, query: str, max_results: int = 100) -> List[Dict]:
        encoded_query = quote_plus(query)
        url = f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}&_sacat={POKEMON_CATEGORY_ID}&LH_Sold=1&LH_Complete=1&_ipg=200"

        try:
            print(f"Fetching sold listings for market value...")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=45)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            sold_items = []

            items = soup.find_all('div', class_='s-item__info')
            print(f"Found {len(items)} sold listing elements")

            for item in items[:max_results]:
                try:
                    price_elem = item.find('span', class_='s-item__price')
                    if not price_elem:
                        continue

                    price_text = price_elem.text.strip()
                    price = float(re.sub(r'[^\d.]', '', price_text))

                    if price > 0:
                        sold_items.append({"price": price})
                except:
                    continue

            print(f"Extracted {len(sold_items)} valid sold prices")
            return sold_items
        except Exception as e:
            print(f"Error fetching sold listings: {e}")
            import traceback
            traceback.print_exc()
            return []

# ============================================================================
# CLAUDE AI SERVICE
# ============================================================================

class ClaudeService:
    """Service for integrating Claude AI to improve search and analysis"""

    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key) if api_key else None

    def enhance_search_query(self, user_query: str) -> str:
        """
        Use Claude to enhance a natural language query into better eBay search terms

        Example: "I want a vintage Charizard graded PSA 9"
              -> "Charizard Base Set PSA 9"
        """
        if not self.client:
            return user_query

        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"""You are a Pokemon card expert helping optimize eBay searches.

User wants to search for: "{user_query}"

Convert this into optimal eBay search terms. Focus on:
- Card name
- Set name (if vintage: Base Set, Jungle, Fossil, etc.)
- Grading info (PSA, BGS, CGC if mentioned)
- Condition keywords

Return ONLY the optimized search query, nothing else. Be concise - max 6 words.

Examples:
"I want a Charizard that's graded well" -> "Charizard PSA"
"vintage Pikachu in good condition" -> "Pikachu Base Set"
"modern umbreon alternate art" -> "Umbreon Alt Art"

Optimized search:"""
                }]
            )
            enhanced = message.content[0].text.strip()
            print(f"Claude enhanced query: '{user_query}' -> '{enhanced}'")
            return enhanced
        except Exception as e:
            print(f"Claude query enhancement failed: {e}")
            return user_query

    def analyze_listings(self, listings: List[Dict], query: str) -> List[Dict]:
        """
        Use Claude to analyze and filter listings for relevance

        Filters out:
        - Bulk lots when user wants single cards
        - Wrong cards (e.g., "Charizard EX" when searching for "Charizard Base Set")
        - Damaged/poor condition cards
        - Irrelevant listings
        """
        if not self.client or not listings:
            return listings

        try:
            # Prepare listing summaries
            listing_summaries = []
            for i, listing in enumerate(listings[:20]):  # Analyze first 20
                listing_summaries.append(f"{i}: {listing['title']} - ${listing['price']}")

            summaries_text = "\n".join(listing_summaries)

            message = self.client.messages.create(
                model="claude-3-5-haiku-20241022",  # Use Haiku for speed
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": f"""You are filtering Pokemon card listings for relevance.

User searched for: "{query}"

Here are the listings (ID: Title - Price):
{summaries_text}

Identify which listings are RELEVANT to what the user wants. Filter OUT:
- Bulk lots (unless user explicitly wants them)
- Wrong cards or sets
- Damaged/poor condition (unless user wants them)
- Completely unrelated items
- Obvious fakes or reproductions

Return ONLY the IDs of RELEVANT listings as a comma-separated list.
Example: 0,2,5,7,9

Relevant listing IDs:"""
                }]
            )

            # Parse response
            relevant_ids_text = message.content[0].text.strip()
            relevant_ids = {int(x.strip()) for x in relevant_ids_text.split(',') if x.strip().isdigit()}

            # Filter listings
            filtered = [listing for i, listing in enumerate(listings) if i in relevant_ids or i >= 20]
            print(f"Claude filtered {len(listings)} -> {len(filtered)} relevant listings")
            return filtered

        except Exception as e:
            print(f"Claude filtering failed: {e}")
            return listings

    def generate_deal_insights(self, deal: Dict, market_value: Optional[float]) -> str:
        """
        Generate AI insights about why a deal is good or concerns to watch for
        """
        if not self.client or not market_value:
            return ""

        try:
            message = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": f"""Analyze this Pokemon card deal:

Card: {deal['card_name']}
Listing Price: ${deal['listing_price']:.2f}
Market Value: ${market_value:.2f}
Discount: {deal.get('discount_percent', 0):.1f}%
Seller Feedback: {deal.get('seller_feedback_percent', 0):.1f}%
Condition: {deal.get('condition', 'Unknown')}

In 1-2 sentences, explain:
1. Why this is a good deal, OR
2. What to watch out for

Be concise and practical. Focus on value.

Insight:"""
                }]
            )
            return message.content[0].text.strip()
        except:
            return ""

# ============================================================================
# DEAL FINDER
# ============================================================================

class DealFinder:
    def __init__(self, ebay_client: EbayClient, claude_service: Optional['ClaudeService'] = None):
        self.ebay = ebay_client
        self.claude = claude_service

    def find_deals(self, query: str, discount_threshold: float = 0,
                   max_results: int = 20) -> List[Deal]:
        # Use Claude to enhance the search query
        enhanced_query = query
        if self.claude:
            enhanced_query = self.claude.enhance_search_query(query)

        # Get market value (but don't require it)
        market_value = self._get_market_value(enhanced_query)
        if market_value:
            print(f"Market value found: ${market_value:.2f}")
        else:
            print(f"Could not determine market value (insufficient sold listings)")
            market_value = None  # Will show all listings without market comparison

        # Search active listings (no price filter if no market value)
        max_price_filter = None
        if market_value and discount_threshold > 0:
            max_price_filter = market_value * (100 - discount_threshold) / 100

        listings = self.ebay.search_active_listings(
            query=enhanced_query,
            max_results=max_results * 3,  # Get extra for Claude filtering
            max_price=max_price_filter
        )

        if not listings:
            print("No active listings found")
            return []

        print(f"Found {len(listings)} active listings")

        # Use Claude to filter relevant listings
        if self.claude:
            listing_dicts = [
                {"title": l.title, "price": l.price}
                for l in listings
            ]
            filtered_dicts = self.claude.analyze_listings(listing_dicts, query)
            filtered_titles = {d["title"] for d in filtered_dicts}
            listings = [l for l in listings if l.title in filtered_titles]
            print(f"After Claude filtering: {len(listings)} relevant listings")

        # Create deals from all listings
        deals = []
        for listing in listings:
            listing_price = listing.get_total_cost()

            if market_value:
                discount_amount = market_value - listing_price
                discount_percent = (discount_amount / market_value) * 100
            else:
                # No market data - show listing anyway with N/A for discount
                discount_amount = 0
                discount_percent = 0

            deal = Deal(
                listing=listing,
                market_value=market_value if market_value else listing_price,  # Use listing price as fallback
                discount_amount=discount_amount,
                discount_percent=discount_percent
            )
            deals.append(deal)

        # Sort by price (lowest first) if no market data, otherwise by deal score
        if market_value:
            deals.sort(key=lambda d: d.deal_score, reverse=True)
        else:
            deals.sort(key=lambda d: d.listing.get_total_cost())

        return deals[:max_results]

    def _get_market_value(self, query: str) -> Optional[float]:
        sold_listings = self.ebay.search_sold_listings(query, max_results=100)

        if len(sold_listings) < 3:
            return None

        prices = [item["price"] for item in sold_listings]

        # Remove outliers
        if len(prices) >= 10:
            prices_sorted = sorted(prices)
            bottom_cutoff = max(1, len(prices) // 10)
            top_cutoff = max(1, len(prices) // 10)
            prices = prices_sorted[bottom_cutoff:-top_cutoff] if top_cutoff > 0 else prices_sorted[bottom_cutoff:]

        return round(statistics.median(prices), 2)

# ============================================================================
# FLASK WEB APP
# ============================================================================

app = Flask(__name__)

# Add CORS headers to fix 403 errors
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎴 PokeBuy - Pokemon Card Deal Finder</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 10px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        header {
            text-align: center;
            padding: 20px;
            background: white;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        h1 { font-size: 2rem; color: #e3350d; margin-bottom: 5px; }
        .subtitle { color: #666; font-size: 0.9rem; }
        .search-section {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .search-box { display: flex; gap: 10px; margin-bottom: 15px; }
        .search-box input {
            flex: 1;
            padding: 12px 15px;
            border: 2px solid #dee2e6;
            border-radius: 10px;
            font-size: 1rem;
        }
        .search-box button {
            padding: 12px 20px;
            background: #e3350d;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: bold;
            cursor: pointer;
        }
        .search-box button:active { transform: scale(0.98); }
        .quick-searches {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        .quick-btn {
            padding: 10px;
            background: #ffcb05;
            border: none;
            border-radius: 10px;
            font-weight: bold;
            cursor: pointer;
        }
        .loading {
            text-align: center;
            padding: 40px;
            background: white;
            border-radius: 15px;
            display: none;
        }
        .spinner {
            width: 50px;
            height: 50px;
            border: 5px solid #f8f9fa;
            border-top-color: #e3350d;
            border-radius: 50%;
            margin: 0 auto 15px;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .error {
            background: #fff3cd;
            border: 1px solid #ffc107;
            color: #856404;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: none;
        }
        .results-summary {
            background: white;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
            font-weight: bold;
            display: none;
        }
        .deals-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 15px;
        }
        .deal-card {
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .deal-card.hot { border: 3px solid #dc3545; }
        .deal-card.star { border: 3px solid #ffcb05; }
        .deal-image {
            width: 100%;
            height: 200px;
            object-fit: cover;
            background: #f8f9fa;
        }
        .deal-content { padding: 15px; }
        .deal-emoji { font-size: 1.5rem; margin-bottom: 5px; }
        .deal-title {
            font-weight: bold;
            margin-bottom: 10px;
            font-size: 0.95rem;
            line-height: 1.3;
        }
        .deal-prices {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        .market-value { color: #666; text-decoration: line-through; }
        .listing-price {
            color: #28a745;
            font-weight: bold;
            font-size: 1.2rem;
        }
        .deal-stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 15px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .stat { text-align: center; }
        .stat-label { font-size: 0.75rem; color: #666; }
        .stat-value { font-weight: bold; font-size: 1.1rem; }
        .deal-link {
            display: block;
            width: 100%;
            padding: 12px;
            background: #e3350d;
            color: white;
            text-align: center;
            text-decoration: none;
            border-radius: 10px;
            font-weight: bold;
        }
        footer {
            text-align: center;
            padding: 20px;
            color: white;
            margin-top: 20px;
        }
        @media (min-width: 768px) {
            .quick-searches { grid-template-columns: repeat(4, 1fr); }
            .deals-grid { grid-template-columns: repeat(2, 1fr); }
        }
        @media (min-width: 1024px) {
            .deals-grid { grid-template-columns: repeat(3, 1fr); }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎴 PokeBuy</h1>
            <p class="subtitle">Find Pokemon Cards at 50%+ Off Market Value</p>
        </header>

        <main>
            <div class="search-section">
                <div class="search-box">
                    <input type="text" id="searchQuery" placeholder="Search (e.g., Charizard PSA 10)">
                    <button onclick="searchDeals()">🔍 Search</button>
                </div>
                <div class="quick-searches">
                    <button class="quick-btn" onclick="quickSearch('Charizard PSA 10')">🔥 Charizard</button>
                    <button class="quick-btn" onclick="quickSearch('Pikachu')">⚡ Pikachu</button>
                    <button class="quick-btn" onclick="quickSearch('Umbreon')">🌙 Umbreon</button>
                    <button class="quick-btn" onclick="quickSearch('Base Set Holo')">✨ Base Set</button>
                </div>
            </div>

            <div id="loading" class="loading">
                <div class="spinner"></div>
                <p>Searching for deals...</p>
            </div>

            <div id="error" class="error"></div>
            <div id="resultsSummary" class="results-summary"></div>
            <div id="dealsContainer" class="deals-grid"></div>
        </main>

        <footer>
            <p>Made with ❤️ for Pokemon card collectors</p>
        </footer>
    </div>

    <script>
        function quickSearch(query) {
            document.getElementById('searchQuery').value = query;
            searchDeals();
        }

        async function searchDeals() {
            const query = document.getElementById('searchQuery').value.trim();
            if (!query) {
                showError('Please enter a search query');
                return;
            }

            document.getElementById('loading').style.display = 'block';
            document.getElementById('error').style.display = 'none';
            document.getElementById('resultsSummary').style.display = 'none';
            document.getElementById('dealsContainer').innerHTML = '';

            try {
                const response = await fetch('/api/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, discount: 50, max_results: 20 })
                });

                const data = await response.json();
                document.getElementById('loading').style.display = 'none';

                if (!response.ok || !data.success) {
                    showError(data.error || 'Search failed');
                    return;
                }

                displayResults(data);
            } catch (error) {
                document.getElementById('loading').style.display = 'none';
                showError('Network error. Please try again.');
            }
        }

        function displayResults(data) {
            const container = document.getElementById('dealsContainer');
            const summary = document.getElementById('resultsSummary');

            if (data.deals.length === 0) {
                summary.style.display = 'block';
                summary.innerHTML = '<p style="color: #856404;">No deals found. Try lowering the discount threshold.</p>';
                return;
            }

            summary.style.display = 'block';
            summary.innerHTML = `<p>Found <strong>${data.count}</strong> deals for "${data.query}"</p>`;

            data.deals.forEach(deal => {
                const card = document.createElement('div');
                card.className = 'deal-card';
                if (deal.is_hot_deal) card.classList.add('hot');
                else if (deal.is_star_deal) card.classList.add('star');

                const img = deal.image_url ? `<img src="${deal.image_url}" class="deal-image">` : '';

                const hasMarket = deal.has_market_data && deal.market_value;
                const marketDisplay = hasMarket
                    ? `$${deal.market_value.toFixed(2)}`
                    : '<span style="color: #999;">N/A</span>';
                const discountDisplay = hasMarket && deal.discount_percent !== null
                    ? `${deal.discount_percent.toFixed(1)}%`
                    : '<span style="color: #999;">N/A</span>';
                const saveDisplay = hasMarket && deal.discount_amount !== null
                    ? `$${deal.discount_amount.toFixed(2)}`
                    : '<span style="color: #999;">N/A</span>';

                card.innerHTML = `
                    ${img}
                    <div class="deal-content">
                        ${hasMarket ? `<div class="deal-emoji">${deal.emoji}</div>` : ''}
                        <h3 class="deal-title">${truncate(deal.card_name, 80)}</h3>
                        <div class="deal-prices">
                            <div>
                                <div style="font-size: 0.8rem; color: #666;">Market Value</div>
                                <div class="market-value">${marketDisplay}</div>
                            </div>
                            <div>
                                <div style="font-size: 0.8rem; color: #666;">Current Price</div>
                                <div class="listing-price">$${deal.listing_price.toFixed(2)}</div>
                            </div>
                        </div>
                        <div class="deal-stats">
                            <div class="stat">
                                <div class="stat-label">You Save</div>
                                <div class="stat-value" style="color: #dc3545;">${saveDisplay}</div>
                            </div>
                            <div class="stat">
                                <div class="stat-label">Discount</div>
                                <div class="stat-value" style="color: #dc3545;">${discountDisplay}</div>
                            </div>
                        </div>
                        <a href="${deal.url}" target="_blank" class="deal-link">View on eBay →</a>
                    </div>
                `;
                container.appendChild(card);
            });
        }

        function truncate(str, max) {
            return str.length <= max ? str : str.substring(0, max - 3) + '...';
        }

        function showError(msg) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = msg;
            errorDiv.style.display = 'block';
        }

        document.getElementById('searchQuery').addEventListener('keypress', e => {
            if (e.key === 'Enter') searchDeals();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/search', methods=['POST'])
def search():
    try:
        data = request.json
        query = data.get('query', '')
        discount = float(data.get('discount', DEFAULT_DISCOUNT_THRESHOLD))
        max_results = int(data.get('max_results', 20))

        if not query:
            return jsonify({'error': 'Query is required', 'success': False}), 400

        if not EBAY_APP_ID:
            return jsonify({'error': 'eBay API key not configured', 'success': False}), 500

        ebay = EbayClient(EBAY_APP_ID)
        claude = ClaudeService(ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
        finder = DealFinder(ebay, claude)
        deals = finder.find_deals(query, discount, max_results)

        deals_json = []
        for deal in deals:
            # Check if market value is real or just a fallback
            has_market_data = deal.market_value != deal.listing.get_total_cost()

            deals_json.append({
                'card_name': deal.listing.title,
                'market_value': deal.market_value if has_market_data else None,
                'listing_price': deal.listing.get_total_cost(),
                'discount_amount': deal.discount_amount if has_market_data else None,
                'discount_percent': deal.discount_percent if has_market_data else None,
                'deal_score': deal.deal_score if has_market_data else 0,
                'emoji': deal.get_emoji() if has_market_data else '📦',
                'is_hot_deal': deal.is_hot_deal if has_market_data else False,
                'is_star_deal': deal.is_star_deal if has_market_data else False,
                'url': deal.listing.url,
                'image_url': deal.listing.image_url,
                'has_market_data': has_market_data,
            })

        return jsonify({
            'success': True,
            'query': query,
            'deals': deals_json,
            'count': len(deals_json)
        })

    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
