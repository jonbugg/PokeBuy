#!/usr/bin/env python3
"""
PokeBuy Web Interface - Mobile-friendly web app
"""

from flask import Flask, render_template, request, jsonify, send_file
from datetime import datetime
import os
import csv
import io

from src.api import EbayClient
from src.services import CacheService, PriceAnalyzer, DealFinder
from src.config import EBAY_APP_ID, DEFAULT_DISCOUNT_THRESHOLD

app = Flask(__name__)


@app.route('/')
def index():
    """Main search page"""
    return render_template('index.html')


@app.route('/api/search', methods=['POST'])
def search():
    """Search for deals API endpoint"""
    try:
        data = request.json
        query = data.get('query', '')
        discount = float(data.get('discount', DEFAULT_DISCOUNT_THRESHOLD))
        max_results = int(data.get('max_results', 20))
        min_price = float(data['min_price']) if data.get('min_price') else None
        max_price = float(data['max_price']) if data.get('max_price') else None
        listing_type = data.get('listing_type')

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        # Initialize services
        ebay = EbayClient()
        cache = CacheService()
        price_analyzer = PriceAnalyzer(ebay, cache)
        deal_finder = DealFinder(ebay, price_analyzer, cache)

        # Find deals
        deals = deal_finder.find_deals(
            search_query=query,
            discount_threshold=discount,
            max_results=max_results,
            min_price=min_price,
            max_price=max_price,
            listing_type=listing_type
        )

        # Convert deals to JSON
        deals_json = []
        for deal in deals:
            deals_json.append({
                'card_name': deal.listing.title,
                'market_value': deal.market_value,
                'listing_price': deal.listing_price,
                'discount_amount': deal.discount_amount,
                'discount_percent': deal.discount_percent,
                'deal_score': deal.deal_score,
                'emoji': deal.get_emoji(),
                'is_hot_deal': deal.is_hot_deal,
                'is_star_deal': deal.is_star_deal,
                'url': deal.listing.url,
                'image_url': deal.listing.image_url,
                'listing_type': deal.listing.listing_type,
                'seller_name': deal.listing.seller_name,
                'seller_feedback_percent': deal.listing.seller_feedback_percent,
                'condition': deal.listing.condition,
                'shipping_cost': deal.listing.shipping_cost,
                'free_shipping': deal.listing.free_shipping,
            })

        return jsonify({
            'success': True,
            'query': query,
            'discount_threshold': discount,
            'deals': deals_json,
            'count': len(deals_json)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trend', methods=['POST'])
def trend():
    """Price trend analysis API endpoint"""
    try:
        data = request.json
        query = data.get('query', '')

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        # Initialize services
        ebay = EbayClient()
        cache = CacheService()
        price_analyzer = PriceAnalyzer(ebay, cache)

        # Get trend data
        trend_data = price_analyzer.get_price_trend(query, days=90)

        trend_emoji = {
            "rising": "📈",
            "falling": "📉",
            "stable": "➡️",
            "unknown": "❓"
        }

        return jsonify({
            'success': True,
            'query': query,
            'trend': trend_data['trend'],
            'trend_emoji': trend_emoji[trend_data['trend']],
            'average_price': trend_data['average_price'],
            'min_price': trend_data['min_price'],
            'max_price': trend_data['max_price'],
            'sample_size': trend_data['sample_size']
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['GET'])
def config():
    """Get configuration"""
    return jsonify({
        'ebay_configured': bool(EBAY_APP_ID),
        'default_discount': DEFAULT_DISCOUNT_THRESHOLD
    })


if __name__ == '__main__':
    # Run on all interfaces so it's accessible from mobile on same network
    app.run(host='0.0.0.0', port=5000, debug=True)
