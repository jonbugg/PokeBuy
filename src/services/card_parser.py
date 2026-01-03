"""Card information parser from listing titles"""

import re
from typing import Optional, Tuple

from ..config import GRADING_COMPANIES
from ..models import Card


class CardParser:
    """Parse Pokemon card information from listing titles"""

    @staticmethod
    def parse_listing_title(title: str, query: str = "") -> Card:
        """
        Parse a listing title to extract card information

        Args:
            title: eBay listing title
            query: Original search query (helps with Pokemon name)

        Returns:
            Card object with parsed information
        """
        title_lower = title.lower()

        # Extract grading info
        grading_company, grade = CardParser._extract_grading(title)

        # Extract condition (for ungraded cards)
        condition = CardParser._extract_condition(title) if not grading_company else None

        # Extract Pokemon name (use query as fallback)
        pokemon = CardParser._extract_pokemon_name(title, query)

        # Extract set name
        set_name = CardParser._extract_set_name(title)

        # Extract variants
        first_edition = "1st edition" in title_lower
        shadowless = "shadowless" in title_lower
        holo = "holo" in title_lower and "non-holo" not in title_lower
        reverse_holo = "reverse holo" in title_lower

        # Extract year (approximate)
        year = CardParser._extract_year(title)

        return Card(
            name=title,
            pokemon=pokemon,
            set_name=set_name,
            grading_company=grading_company,
            grade=grade,
            condition=condition,
            first_edition=first_edition,
            shadowless=shadowless,
            holo=holo,
            reverse_holo=reverse_holo,
            year=year
        )

    @staticmethod
    def _extract_grading(title: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract grading company and grade"""
        title_upper = title.upper()

        for company in GRADING_COMPANIES:
            # Look for pattern like "PSA 10" or "BGS 9.5"
            pattern = rf"{company}\s*(\d+(?:\.\d+)?)"
            match = re.search(pattern, title_upper)
            if match:
                grade = match.group(1)
                return company, grade

        return None, None

    @staticmethod
    def _extract_condition(title: str) -> Optional[str]:
        """Extract condition for ungraded cards"""
        title_lower = title.lower()

        condition_map = {
            "mint": ["mint", "nm", "near mint"],
            "excellent": ["excellent", "exc", "ex "],
            "good": ["good", "gd"],
            "played": ["lp", "light play", "mp", "moderate play", "played"],
            "poor": ["poor", "hp", "heavy play", "damaged"]
        }

        for condition, keywords in condition_map.items():
            if any(keyword in title_lower for keyword in keywords):
                return condition.title()

        return None

    @staticmethod
    def _extract_pokemon_name(title: str, query: str) -> str:
        """Extract Pokemon name from title or query"""
        # Common Pokemon names (partial list - can be expanded)
        common_pokemon = [
            "Charizard", "Blastoise", "Venusaur", "Pikachu", "Mewtwo",
            "Gyarados", "Dragonite", "Alakazam", "Gengar", "Machamp",
            "Lugia", "Ho-Oh", "Rayquaza", "Groudon", "Kyogre",
            "Umbreon", "Espeon", "Vaporeon", "Flareon", "Jolteon",
            "Eevee", "Mew", "Celebi", "Jirachi", "Deoxys"
        ]

        title_lower = title.lower()

        # Check title for Pokemon names
        for pokemon in common_pokemon:
            if pokemon.lower() in title_lower:
                return pokemon

        # Fall back to query
        if query:
            for pokemon in common_pokemon:
                if pokemon.lower() in query.lower():
                    return pokemon

            # Use first word of query as Pokemon name
            first_word = query.split()[0] if query.split() else query
            return first_word.title()

        # Extract first capitalized word from title
        words = title.split()
        for word in words:
            if word and word[0].isupper() and len(word) > 2:
                # Skip grading companies and common words
                if word.upper() not in GRADING_COMPANIES and word.lower() not in ["pokemon", "card", "holo"]:
                    return word

        return "Unknown"

    @staticmethod
    def _extract_set_name(title: str) -> Optional[str]:
        """Extract set name from title"""
        # Common Pokemon card sets
        sets = [
            "Base Set", "Jungle", "Fossil", "Team Rocket", "Gym Heroes",
            "Gym Challenge", "Neo Genesis", "Neo Discovery", "Neo Revelation",
            "Neo Destiny", "Legendary Collection", "Expedition", "Aquapolis",
            "Skyridge", "EX Ruby & Sapphire", "EX Sandstorm", "EX Dragon",
            "Hidden Fates", "Shining Fates", "Champions Path", "Evolving Skies",
            "Brilliant Stars", "Lost Origin", "Silver Tempest", "Crown Zenith",
            "Paldea Evolved", "Obsidian Flames", "151", "Paradox Rift"
        ]

        title_lower = title.lower()

        for set_name in sets:
            if set_name.lower() in title_lower:
                return set_name

        return None

    @staticmethod
    def _extract_year(title: str) -> Optional[int]:
        """Extract year from title"""
        # Look for 4-digit year
        match = re.search(r'\b(19\d{2}|20\d{2})\b', title)
        if match:
            return int(match.group(1))

        # Infer from set (Base Set = 1999, etc.) - simplified
        title_lower = title.lower()
        if "base set" in title_lower:
            return 1999
        elif any(s in title_lower for s in ["jungle", "fossil"]):
            return 1999
        elif "team rocket" in title_lower:
            return 2000

        return None
