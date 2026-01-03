"""Listing data model"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Listing:
    """Represents an eBay listing"""

    # eBay data
    item_id: str
    title: str
    price: float
    currency: str = "USD"

    # Listing details
    listing_type: str = "FixedPrice"  # or "Auction"
    url: str = ""
    image_url: Optional[str] = None

    # Shipping
    shipping_cost: Optional[float] = None
    free_shipping: bool = False

    # Timing
    end_time: Optional[datetime] = None
    time_left: Optional[str] = None

    # Seller
    seller_name: Optional[str] = None
    seller_feedback_score: Optional[int] = None
    seller_feedback_percent: Optional[float] = None

    # Condition
    condition: Optional[str] = None

    # Location
    location: Optional[str] = None

    def get_total_cost(self) -> float:
        """Calculate total cost including shipping"""
        shipping = self.shipping_cost if self.shipping_cost and not self.free_shipping else 0
        return self.price + shipping

    def is_auction(self) -> bool:
        """Check if listing is an auction"""
        return self.listing_type.lower() in ["auction", "chinese"]

    def __str__(self) -> str:
        """String representation of the listing"""
        return f"{self.title} - ${self.price:.2f}"
