"""Card data model"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Card:
    """Represents a Pokemon card"""

    name: str
    pokemon: str
    set_name: Optional[str] = None
    card_number: Optional[str] = None
    rarity: Optional[str] = None
    year: Optional[int] = None

    # Grading information
    grading_company: Optional[str] = None
    grade: Optional[str] = None

    # Condition (for ungraded cards)
    condition: Optional[str] = None

    # Variants
    first_edition: bool = False
    shadowless: bool = False
    reverse_holo: bool = False
    holo: bool = False

    # Market data
    market_value: Optional[float] = None
    market_value_source: Optional[str] = None
    market_value_updated: Optional[datetime] = None

    def __str__(self) -> str:
        """String representation of the card"""
        parts = [self.name]

        if self.set_name:
            parts.append(f"({self.set_name})")

        if self.grading_company and self.grade:
            parts.append(f"{self.grading_company} {self.grade}")
        elif self.condition:
            parts.append(f"{self.condition}")

        if self.first_edition:
            parts.append("1st Edition")
        if self.shadowless:
            parts.append("Shadowless")
        if self.holo:
            parts.append("Holo")

        return " ".join(parts)

    def get_search_key(self) -> str:
        """Generate a unique search key for caching"""
        key_parts = [
            self.name.lower(),
            self.set_name.lower() if self.set_name else "",
            f"{self.grading_company}_{self.grade}" if self.grading_company and self.grade else "",
            self.condition.lower() if self.condition else ""
        ]
        return "_".join(filter(None, key_parts))
