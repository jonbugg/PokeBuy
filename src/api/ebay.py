"""eBay API client for searching listings and sold items"""

import re
import base64
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import requests
import httpx
from bs4 import BeautifulSoup

from ..config import (
    EBAY_APP_ID,
    EBAY_CERT_ID,
    EBAY_USER_TOKEN,
    POKEMON_CATEGORY_ID,
    MAX_RESULTS,
    GRADING_COMPANIES,
    POKEMON_TCG_API_KEY
)
from ..models import Listing


class EbayClient:
    """Client for interacting with eBay Finding and Browse APIs"""

    def __init__(self, app_id: Optional[str] = None, cert_id: Optional[str] = None, user_token: Optional[str] = None):
        """
        Initialize eBay client

        Args:
            app_id: eBay Application ID (defaults to config)
            cert_id: eBay Cert ID / Client Secret (defaults to config)
            user_token: eBay OAuth User Token (defaults to config)
        """
        self.app_id = app_id or EBAY_APP_ID
        self.cert_id = cert_id or EBAY_CERT_ID
        self.user_token = user_token or EBAY_USER_TOKEN
        self._oauth_token = None
        self._oauth_token_expiry = None
        self._httpx_client = None
        self.finding_api_url = "https://svcs.ebay.com/services/search/FindingService/v1"
        self.browse_api_url = "https://api.ebay.com/buy/browse/v1"

        if not self.app_id:
            raise ValueError(
                "eBay App ID not configured. "
                "Set EBAY_APP_ID in .env file"
            )

    def _get_httpx_client(self) -> httpx.Client:
        """Get an httpx client for web scraping (works better than requests for eBay)"""
        if self._httpx_client is None:
            self._httpx_client = httpx.Client(
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    # Note: Not including Accept-Encoding to avoid compressed responses that need decompression
                },
                timeout=60.0
            )
        return self._httpx_client

    def _get_oauth_token(self) -> Optional[str]:
        """Get OAuth token using client credentials flow"""
        # Return cached token if still valid
        if self._oauth_token and self._oauth_token_expiry and datetime.now() < self._oauth_token_expiry:
            return self._oauth_token

        if not self.app_id or not self.cert_id:
            return None

        try:
            auth_url = "https://api.ebay.com/identity/v1/oauth2/token"
            credentials = base64.b64encode(f"{self.app_id}:{self.cert_id}".encode()).decode()

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}"
            }
            data = {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope"
            }

            response = requests.post(auth_url, headers=headers, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            self._oauth_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 7200)
            self._oauth_token_expiry = datetime.now() + timedelta(seconds=expires_in - 60)

            return self._oauth_token

        except requests.RequestException as e:
            print(f"Error getting OAuth token: {e}")
            return None

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
        # Try Browse API with OAuth token first
        oauth_token = self._get_oauth_token()
        if oauth_token:
            listings = self._search_browse_api(query, max_results, min_price, max_price, listing_type, oauth_token)
            if listings:
                return listings

        # Try Finding API
        listings = self._search_finding_api(query, max_results, min_price, max_price, condition, listing_type)
        if listings:
            return listings

        # Fall back to web scraping
        return self._search_web_scrape(query, max_results, min_price, max_price, listing_type)

    def _search_browse_api(
        self,
        query: str,
        max_results: int,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        listing_type: Optional[str] = None,
        oauth_token: Optional[str] = None,
    ) -> List[Listing]:
        """Search using eBay Browse API with OAuth token"""
        token = oauth_token or self._get_oauth_token()
        if not token:
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "Content-Type": "application/json",
        }

        # Build filter string
        filters = []
        if min_price is not None:
            filters.append(f"price:[{min_price}]")
        if max_price is not None:
            filters.append(f"price:[..{max_price}]")
        if listing_type:
            if listing_type.lower() == "auction":
                filters.append("buyingOptions:{AUCTION}")
            else:
                filters.append("buyingOptions:{FIXED_PRICE}")

        params = {
            "q": query,
            "limit": min(max_results, 200),
            "sort": "price",
            "category_ids": POKEMON_CATEGORY_ID,
        }
        if filters:
            params["filter"] = ",".join(filters)

        try:
            response = requests.get(
                f"{self.browse_api_url}/item_summary/search",
                headers=headers,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_browse_response(data)

        except requests.RequestException as e:
            print(f"Browse API error (falling back to Finding API): {e}")
            return []

    def _parse_browse_response(self, data: Dict[str, Any]) -> List[Listing]:
        """Parse Browse API response into Listing objects"""
        listings = []
        items = data.get("itemSummaries", [])

        for item in items:
            try:
                price_info = item.get("price", {})
                price = float(price_info.get("value", 0))

                shipping_cost = 0.0
                shipping_options = item.get("shippingOptions", [])
                if shipping_options:
                    shipping_cost_info = shipping_options[0].get("shippingCost", {})
                    shipping_cost = float(shipping_cost_info.get("value", 0))

                buying_options = item.get("buyingOptions", [])
                listing_type = "Auction" if "AUCTION" in buying_options else "FixedPrice"

                listing = Listing(
                    item_id=item.get("itemId", ""),
                    title=item.get("title", ""),
                    price=price,
                    shipping_cost=shipping_cost,
                    currency=price_info.get("currency", "USD"),
                    url=item.get("itemWebUrl", ""),
                    image_url=item.get("image", {}).get("imageUrl", ""),
                    seller_name=item.get("seller", {}).get("username", ""),
                    listing_type=listing_type,
                    condition=item.get("condition", ""),
                    end_time=None,
                )
                listings.append(listing)
            except (KeyError, ValueError) as e:
                continue

        return listings

    def _search_finding_api(
        self,
        query: str,
        max_results: int,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        condition: Optional[str] = None,
        listing_type: Optional[str] = None,
    ) -> List[Listing]:
        """Search using eBay Finding API"""
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

    def _search_web_scrape(
        self,
        query: str,
        max_results: int,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        listing_type: Optional[str] = None,
    ) -> List[Listing]:
        """Search eBay by web scraping as fallback"""
        encoded_query = quote_plus(query)
        
        # Build URL with filters
        url = f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}&_sacat={POKEMON_CATEGORY_ID}&_sop=15"
        
        if listing_type:
            if listing_type.lower() == "auction":
                url += "&LH_Auction=1"
            else:
                url += "&LH_BIN=1"
        
        if min_price is not None:
            url += f"&_udlo={min_price}"
        if max_price is not None:
            url += f"&_udhi={max_price}"

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            listings = []

            # Find all listing items
            items = soup.select('div.s-item__wrapper')

            for item in items[:max_results]:
                try:
                    # Skip the first item (usually a placeholder)
                    title_elem = item.select_one('div.s-item__title span')
                    if not title_elem or "Shop on eBay" in title_elem.text:
                        continue

                    title = title_elem.text.strip()

                    # Extract price
                    price_elem = item.select_one('span.s-item__price')
                    if not price_elem:
                        continue

                    price_text = price_elem.text.strip()
                    price = self._extract_price(price_text)
                    if price is None:
                        continue

                    # Extract shipping
                    shipping_cost = 0.0
                    shipping_elem = item.select_one('span.s-item__shipping')
                    if shipping_elem:
                        shipping_text = shipping_elem.text.strip().lower()
                        if "free" in shipping_text:
                            shipping_cost = 0.0
                        else:
                            shipping_cost = self._extract_price(shipping_elem.text) or 0.0

                    # Extract URL
                    link_elem = item.select_one('a.s-item__link')
                    item_url = link_elem.get('href', '') if link_elem else ''
                    
                    # Extract item ID from URL
                    item_id = ""
                    if '/itm/' in item_url:
                        item_id = item_url.split('/itm/')[-1].split('?')[0]

                    # Determine listing type
                    detected_type = "FixedPrice"
                    bid_elem = item.select_one('span.s-item__bids')
                    if bid_elem:
                        detected_type = "Auction"

                    listing = Listing(
                        item_id=item_id,
                        title=title,
                        price=price,
                        shipping_cost=shipping_cost,
                        currency="USD",
                        url=item_url,
                        image_url="",
                        seller_name="",
                        listing_type=detected_type,
                        condition="",
                        end_time=None,
                    )
                    listings.append(listing)

                except Exception as e:
                    continue

            print(f"Found {len(listings)} listings via web scraping")
            return listings

        except requests.RequestException as e:
            print(f"Error scraping eBay: {e}")
            return []

    def search_sold_listings(
        self,
        query: str,
        days: int = 60,
        max_results: int = MAX_RESULTS
    ) -> List[Dict[str, Any]]:
        """
        Search for sold/completed Pokemon card listings on eBay

        Note: This uses web scraping with httpx as the official API has limited sold data access

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
            # Use httpx client for scraping (works better than requests for eBay)
            client = self._get_httpx_client()
            response = client.get(url)
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

        except httpx.HTTPError as e:
            print(f"Error fetching sold listings: {e}")
            return []
        except Exception as e:
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

    def get_tcg_market_price(self, search_query: str, set_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get market price from PriceCharting.com
        
        This is a fallback for when eBay sold listings can't be scraped.
        
        Args:
            search_query: Search query (e.g., "Charizard PSA 10" - we extract the card name)
            set_name: Optional set name to narrow results
            
        Returns:
            Dict with market_value and source info, or None if not found
        """
        try:
            # Extract card name from search query
            card_name = search_query.lower()
            
            # Remove grading terms (but remember if PSA 10 for price adjustment)
            is_graded_10 = 'psa 10' in card_name or 'bgs 10' in card_name or 'cgc 10' in card_name
            is_graded = any(g in card_name for g in ['psa', 'bgs', 'cgc'])
            
            for term in ['psa 10', 'psa 9', 'psa 8', 'psa 7', 'psa', 'bgs 10', 'bgs 9.5', 'bgs 9', 'bgs', 
                         'cgc 10', 'cgc 9.5', 'cgc 9', 'cgc', 'gem mint', 'mint', 'near mint', 'nm']:
                card_name = card_name.replace(term, '')
            
            # Remove common listing terms but keep set names
            for term in ['pokemon', 'card', 'tcg', 'holographic', 'rare', 'ultra rare', 
                         'secret rare', 'full art', 'japanese', 'english']:
                card_name = card_name.replace(term, '')
            
            card_name = ' '.join(card_name.split()).strip()
            
            if not card_name:
                return None
            
            # Use httpx client for PriceCharting
            client = self._get_httpx_client()
            
            # Search PriceCharting
            search_url = f'https://www.pricecharting.com/search-products?q={quote_plus(card_name)}&type=prices'
            response = client.get(search_url)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', id='games_table')
            
            if not table:
                return None
            
            rows = table.find_all('tr')[1:]  # Skip header
            
            if not rows:
                return None
            
            # Get the first matching result's price
            # Table structure: cell[0]=image, cell[1]=title, cell[2]=set, cell[3]=ungraded price, cell[4]=graded price
            for row in rows[:5]:
                cells = row.find_all('td')
                if len(cells) >= 4:
                    title_cell = cells[1]  # Title is in cell 1
                    set_cell = cells[2]    # Set name is in cell 2
                    price_cell = cells[3]  # Ungraded price is in cell 3
                    
                    title = title_cell.get_text(strip=True)
                    set_name_text = set_cell.get_text(strip=True)
                    price_text = price_cell.get_text(strip=True)
                    
                    # Parse price
                    price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
                    if price_match:
                        price = float(price_match.group(1).replace(',', ''))
                        
                        # If searching for graded cards, adjust price
                        # PSA 10 typically worth 2-5x ungraded for modern cards
                        if is_graded_10:
                            price = price * 2.5  # Conservative multiplier
                        elif is_graded:
                            price = price * 1.5
                        
                        return {
                            'market_value': price,
                            'source': 'pricecharting',
                            'card_name': title,
                            'set_name': set_name_text,
                            'updated_at': None
                        }
            
            return None
            
        except Exception as e:
            print(f"Error fetching PriceCharting price: {e}")
            return None
