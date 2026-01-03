"""Deal data model"""

from dataclasses import dataclass
from typing import Optional
from .card import Card
from .listing import Listing


@dataclass
class Deal:
    """Represents a potential deal on a Pokemon card"""

    card: Card
    listing: Listing

    # Deal metrics
    market_value: float
    listing_price: float
    discount_amount: float
    discount_percent: float

    # Deal score (0-100)
    deal_score: float = 0.0

    # Flags
    is_hot_deal: bool = False  # >60% off
    is_star_deal: bool = False  # 50-60% off
    is_rare_card: bool = False

    def __post_init__(self):
        """Calculate deal score and flags after initialization"""
        # Set deal tier flags
        if self.discount_percent >= 60:
            self.is_hot_deal = True
        elif self.discount_percent >= 50:
            self.is_star_deal = True

        # Calculate deal score
        self.deal_score = self._calculate_deal_score()

    def _calculate_deal_score(self) -> float:
        """
        Calculate deal score (0-100)

        Formula:
        - Discount % (0-40 points): Higher discount = higher score
        - Absolute savings (0-30 points): More $ saved = higher score
        - Listing quality (0-20 points): Seller feedback, shipping
        - Card value tier (0-10 points): Higher value cards get bonus
        """
        score = 0.0

        # Discount percentage (0-40 points)
        # 50% = 20pts, 75% = 30pts, 100% = 40pts
        discount_score = min(40, (self.discount_percent / 100) * 40)
        score += discount_score

        # Absolute savings (0-30 points)
        # $50 = 10pts, $100 = 20pts, $200+ = 30pts
        savings_score = min(30, (self.discount_amount / 200) * 30)
        score += savings_score

        # Listing quality (0-20 points)
        quality_score = 0
        if self.listing.seller_feedback_percent and self.listing.seller_feedback_percent >= 98:
            quality_score += 10
        elif self.listing.seller_feedback_percent and self.listing.seller_feedback_percent >= 95:
            quality_score += 5

        if self.listing.free_shipping or (self.listing.shipping_cost and self.listing.shipping_cost < 5):
            quality_score += 5

        if not self.listing.is_auction():
            quality_score += 5  # Buy It Now is immediate

        score += quality_score

        # Card value tier (0-10 points)
        if self.market_value >= 500:
            score += 10
        elif self.market_value >= 200:
            score += 7
        elif self.market_value >= 100:
            score += 5
        elif self.market_value >= 50:
            score += 3

        return round(score, 2)

    def get_emoji(self) -> str:
        """Get emoji representing deal quality"""
        if self.is_hot_deal:
            return "🔥"
        elif self.is_star_deal:
            return "⭐"
        elif self.discount_percent >= 40:
            return "💎"
        else:
            return "📦"

    def __str__(self) -> str:
        """String representation of the deal"""
        emoji = self.get_emoji()
        return (
            f"{emoji} {self.card.name} - "
            f"${self.listing_price:.2f} (Market: ${self.market_value:.2f}, "
            f"Save ${self.discount_amount:.2f}, {self.discount_percent:.1f}% off)"
        )
