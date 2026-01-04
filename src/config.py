"""Configuration management for PokeBuy"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DB_PATH = DATA_DIR / "cache.db"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# eBay API Configuration
EBAY_APP_ID = os.getenv("EBAY_APP_ID", "")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID", "")
EBAY_DEV_ID = os.getenv("EBAY_DEV_ID", "")
EBAY_USER_TOKEN = os.getenv("EBAY_USER_TOKEN", "")

# Pokemon TCG API Configuration (for TCGPlayer market prices)
POKEMON_TCG_API_KEY = os.getenv("POKEMON_TCG_API_KEY", "")

# PriceCharting API Configuration
PRICECHARTING_API_KEY = os.getenv("PRICECHARTING_API_KEY", "")

# Application Configuration
DEFAULT_DISCOUNT_THRESHOLD = int(os.getenv("DEFAULT_DISCOUNT_THRESHOLD", "50"))
CACHE_EXPIRY_HOURS = int(os.getenv("CACHE_EXPIRY_HOURS", "48"))
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "50"))

# eBay Search Configuration
EBAY_GLOBAL_ID = "EBAY-US"  # US site
EBAY_SITE_ID = 0

# Pokemon card categories on eBay
POKEMON_CATEGORY_ID = "183454"  # CCG Individual Cards > Pokemon

# Grading companies
GRADING_COMPANIES = ["PSA", "BGS", "CGC", "Beckett", "SGC"]

# Condition keywords
CONDITION_KEYWORDS = {
    "mint": ["mint", "nm", "near mint", "m"],
    "excellent": ["excellent", "ex", "exc"],
    "good": ["good", "gd"],
    "played": ["played", "lp", "light play", "mp", "moderate play"],
    "poor": ["poor", "hp", "heavy play", "damaged"]
}
