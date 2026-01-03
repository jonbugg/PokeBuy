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

# ============================================================================
# CONFIGURATION
# ============================================================================

EBAY_APP_ID = os.environ.get("EBAY_APP_ID", "")
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
            response = requests.get(self.finding_api_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(data)
        except Exception as e:
            print(f"Error searching eBay: {e}")
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
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            sold_items = []

            items = soup.find_all('div', class_='s-item__info')
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

            return sold_items
        except Exception as e:
            print(f"Error fetching sold listings: {e}")
            return []

# ============================================================================
# DEAL FINDER
# ============================================================================

class DealFinder:
    def __init__(self, ebay_client: EbayClient):
        self.ebay = ebay_client

    def find_deals(self, query: str, discount_threshold: float = 50,
                   max_results: int = 20) -> List[Deal]:
        # Get market value
        market_value = self._get_market_value(query)
        if not market_value:
            return []

        print(f"Market value: ${market_value:.2f}")

        # Search active listings
        max_price_filter = market_value * (100 - discount_threshold) / 100
        listings = self.ebay.search_active_listings(
            query=query,
            max_results=max_results * 3,
            max_price=max_price_filter
        )

        if not listings:
            return []

        # Find deals
        deals = []
        for listing in listings:
            listing_price = listing.get_total_cost()
            discount_amount = market_value - listing_price
            discount_percent = (discount_amount / market_value) * 100

            if discount_percent >= discount_threshold:
                deal = Deal(
                    listing=listing,
                    market_value=market_value,
                    discount_amount=discount_amount,
                    discount_percent=discount_percent
                )
                deals.append(deal)

        # Sort by deal score
        deals.sort(key=lambda d: d.deal_score, reverse=True)
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

                card.innerHTML = `
                    ${img}
                    <div class="deal-content">
                        <div class="deal-emoji">${deal.emoji}</div>
                        <h3 class="deal-title">${truncate(deal.card_name, 80)}</h3>
                        <div class="deal-prices">
                            <div>
                                <div style="font-size: 0.8rem; color: #666;">Market</div>
                                <div class="market-value">$${deal.market_value.toFixed(2)}</div>
                            </div>
                            <div>
                                <div style="font-size: 0.8rem; color: #666;">Price</div>
                                <div class="listing-price">$${deal.listing_price.toFixed(2)}</div>
                            </div>
                        </div>
                        <div class="deal-stats">
                            <div class="stat">
                                <div class="stat-label">Save</div>
                                <div class="stat-value" style="color: #dc3545;">$${deal.discount_amount.toFixed(2)}</div>
                            </div>
                            <div class="stat">
                                <div class="stat-label">Discount</div>
                                <div class="stat-value" style="color: #dc3545;">${deal.discount_percent.toFixed(1)}%</div>
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
        finder = DealFinder(ebay)
        deals = finder.find_deals(query, discount, max_results)

        deals_json = []
        for deal in deals:
            deals_json.append({
                'card_name': deal.listing.title,
                'market_value': deal.market_value,
                'listing_price': deal.listing.get_total_cost(),
                'discount_amount': deal.discount_amount,
                'discount_percent': deal.discount_percent,
                'deal_score': deal.deal_score,
                'emoji': deal.get_emoji(),
                'is_hot_deal': deal.is_hot_deal,
                'is_star_deal': deal.is_star_deal,
                'url': deal.listing.url,
                'image_url': deal.listing.image_url,
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
