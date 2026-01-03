"""eBay API client for searching listings and sold items"""

import re
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from ..config import (
    EBAY_APP_ID,
    POKEMON_CATEGORY_ID,
    MAX_RESULTS,
    GRADING_COMPANIES
)
from ..models import Listing


class EbayClient:
    """Client for interacting with eBay Finding and Browse APIs"""

    def __init__(self, app_id: Optional[str] = None):
        """
        Initialize eBay client

        Args:
            app_id: eBay Application ID (defaults to config)
        """
        self.app_id = app_id or EBAY_APP_ID
        self.finding_api_url = "https://svcs.ebay.com/services/search/FindingService/v1"

        if not self.app_id:
            raise ValueError(
                "eBay App ID not configured. "
                "Set EBAY_APP_ID in .env file or pass app_id parameter"
            )

    def search_active_listings(
        self,
        query: str,
        max_results: int = MAX_RESULTS,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        condition: Optional[str] = None,
        listing_type: Optional[str] = None,
    ) -> List[Listing]:
        """
        Search for active Pokemon card listings on eBay

        Args:
            query: Search query (e.g., "Charizard PSA 10")
            max_results: Maximum number of results to return
            min_price: Minimum price filter
            max_price: Maximum price filter
            condition: Condition filter (e.g., "New", "Used")
            listing_type: "Auction" or "FixedPrice"

        Returns:
            List of Listing objects
        """
        params = {
            "OPERATION-NAME": "findItemsAdvanced",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": self.app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "",
            "keywords": query,
            "categoryId": POKEMON_CATEGORY_ID,
            "paginationInput.entriesPerPage": str(min(max_results, 100)),
            "sortOrder": "PricePlusShippingLowest",
        }

        # Build item filters
        filter_index = 0

        if min_price is not None:
            params[f"itemFilter({filter_index}).name"] = "MinPrice"
            params[f"itemFilter({filter_index}).value"] = str(min_price)
            filter_index += 1

        if max_price is not None:
            params[f"itemFilter({filter_index}).name"] = "MaxPrice"
            params[f"itemFilter({filter_index}).value"] = str(max_price)
            filter_index += 1

        if condition:
            params[f"itemFilter({filter_index}).name"] = "Condition"
            params[f"itemFilter({filter_index}).value"] = condition
            filter_index += 1

        if listing_type:
            params[f"itemFilter({filter_index}).name"] = "ListingType"
            params[f"itemFilter({filter_index}).value"] = listing_type
            filter_index += 1

        try:
            response = requests.get(self.finding_api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            return self._parse_finding_response(data)

        except requests.RequestException as e:
            print(f"Error searching eBay: {e}")
            return []

    def search_sold_listings(
        self,
        query: str,
        days: int = 60,
        max_results: int = MAX_RESULTS
    ) -> List[Dict[str, Any]]:
        """
        Search for sold/completed Pokemon card listings on eBay

        Note: This uses web scraping as the official API has limited sold data access

        Args:
            query: Search query
            days: Number of days to look back
            max_results: Maximum number of results

        Returns:
            List of sold listing dictionaries with price and sold date
        """
        # Build eBay search URL for sold/completed items
        encoded_query = quote_plus(query)
        url = (
            f"https://www.ebay.com/sch/i.html?"
            f"_nkw={encoded_query}"
            f"&_sacat={POKEMON_CATEGORY_ID}"
            f"&LH_Sold=1"
            f"&LH_Complete=1"
            f"&_ipg=200"
        )

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            sold_items = []

            # Find all listing items
            items = soup.find_all('div', class_='s-item__info')

            for item in items[:max_results]:
                try:
                    # Extract price
                    price_elem = item.find('span', class_='s-item__price')
                    if not price_elem:
                        continue

                    price_text = price_elem.text.strip()
                    price = self._extract_price(price_text)
                    if price is None:
                        continue

                    # Extract sold date
                    sold_date_elem = item.find('span', class_='POSITIVE')
                    sold_date = None
                    if sold_date_elem:
                        sold_date_text = sold_date_elem.text.strip()
                        sold_date = self._parse_sold_date(sold_date_text)

                    # Check if within date range
                    if sold_date and days > 0:
                        cutoff_date = datetime.now() - timedelta(days=days)
                        if sold_date < cutoff_date:
                            continue

                    sold_items.append({
                        "price": price,
                        "sold_date": sold_date,
                        "currency": "USD"
                    })

                except Exception as e:
                    continue

            return sold_items

        except requests.RequestException as e:
            print(f"Error fetching sold listings: {e}")
            return []

    def _parse_finding_response(self, data: Dict[str, Any]) -> List[Listing]:
        """Parse eBay Finding API response into Listing objects"""
        listings = []

        try:
            search_result = data.get("findItemsAdvancedResponse", [{}])[0]
            items = search_result.get("searchResult", [{}])[0].get("item", [])

            for item in items:
                try:
                    listing = self._parse_item(item)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    continue

        except Exception as e:
            print(f"Error parsing eBay response: {e}")

        return listings

    def _parse_item(self, item: Dict[str, Any]) -> Optional[Listing]:
        """Parse a single eBay item into a Listing object"""
        try:
            item_id = item.get("itemId", [""])[0]
            title = item.get("title", [""])[0]

            # Price
            price_info = item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0]
            price = float(price_info.get("__value__", 0))
            currency = price_info.get("@currencyId", "USD")

            # Listing type
            listing_info = item.get("listingInfo", [{}])[0]
            listing_type = listing_info.get("listingType", ["FixedPrice"])[0]

            # URL
            url = item.get("viewItemURL", [""])[0]

            # Image
            image_url = item.get("galleryURL", [""])[0]

            # Shipping
            shipping_info = item.get("shippingInfo", [{}])[0]
            shipping_cost_info = shipping_info.get("shippingServiceCost", [{}])[0]
            shipping_cost = float(shipping_cost_info.get("__value__", 0))
            free_shipping = shipping_cost == 0

            # End time (for auctions)
            end_time_str = listing_info.get("endTime", [""])[0]
            end_time = None
            if end_time_str:
                try:
                    end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                except:
                    pass

            # Condition
            condition_info = item.get("condition", [{}])[0]
            condition = condition_info.get("conditionDisplayName", [""])[0]

            # Seller
            seller_info = item.get("sellerInfo", [{}])[0]
            seller_name = seller_info.get("sellerUserName", [""])[0]
            seller_feedback_score = int(seller_info.get("feedbackScore", [0])[0])
            seller_feedback_percent = float(seller_info.get("positiveFeedbackPercent", [0])[0])

            # Location
            location = item.get("location", [""])[0]

            return Listing(
                item_id=item_id,
                title=title,
                price=price,
                currency=currency,
                listing_type=listing_type,
                url=url,
                image_url=image_url if image_url else None,
                shipping_cost=shipping_cost if shipping_cost > 0 else None,
                free_shipping=free_shipping,
                end_time=end_time,
                condition=condition if condition else None,
                seller_name=seller_name if seller_name else None,
                seller_feedback_score=seller_feedback_score if seller_feedback_score else None,
                seller_feedback_percent=seller_feedback_percent if seller_feedback_percent else None,
                location=location if location else None,
            )

        except Exception as e:
            return None

    def _extract_price(self, price_text: str) -> Optional[float]:
        """Extract numeric price from price text"""
        try:
            # Remove currency symbols and commas
            cleaned = re.sub(r'[^\d.]', '', price_text)
            return float(cleaned)
        except:
            return None

    def _parse_sold_date(self, date_text: str) -> Optional[datetime]:
        """Parse sold date from eBay's format (e.g., 'Sold Dec 15, 2023')"""
        try:
            # Extract date part (e.g., "Dec 15, 2023" from "Sold Dec 15, 2023")
            match = re.search(r'([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})', date_text)
            if match:
                month_str, day, year = match.groups()
                date_str = f"{month_str} {day}, {year}"
                return datetime.strptime(date_str, "%b %d, %Y")
        except:
            pass
        return None
