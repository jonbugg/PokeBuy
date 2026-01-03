"""Caching service for market prices"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

from ..config import CACHE_DB_PATH, CACHE_EXPIRY_HOURS


class CacheService:
    """SQLite-based cache for market prices"""

    def __init__(self, db_path: Path = CACHE_DB_PATH):
        """Initialize cache service"""
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_prices (
                    search_key TEXT PRIMARY KEY,
                    market_value REAL NOT NULL,
                    source TEXT NOT NULL,
                    data TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)
            conn.commit()

    def get(self, search_key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached market price

        Args:
            search_key: Unique identifier for the card

        Returns:
            Cached data dict or None if not found/expired
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM market_prices WHERE search_key = ?",
                (search_key,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            # Check if expired
            updated_at = datetime.fromisoformat(row["updated_at"])
            expiry_time = updated_at + timedelta(hours=CACHE_EXPIRY_HOURS)

            if datetime.now() > expiry_time:
                # Expired, delete and return None
                conn.execute("DELETE FROM market_prices WHERE search_key = ?", (search_key,))
                conn.commit()
                return None

            # Parse and return data
            return {
                "search_key": row["search_key"],
                "market_value": row["market_value"],
                "source": row["source"],
                "data": json.loads(row["data"]) if row["data"] else None,
                "updated_at": updated_at
            }

    def set(
        self,
        search_key: str,
        market_value: float,
        source: str,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Cache market price

        Args:
            search_key: Unique identifier for the card
            market_value: Market value in USD
            source: Data source (e.g., "ebay_sold", "pricecharting")
            data: Additional data to cache (JSON serializable)
        """
        now = datetime.now()
        data_json = json.dumps(data) if data else None

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO market_prices
                (search_key, market_value, source, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (search_key, market_value, source, data_json, now, now))
            conn.commit()

    def clear_expired(self):
        """Clear all expired cache entries"""
        expiry_threshold = datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM market_prices WHERE updated_at < ?",
                (expiry_threshold,)
            )
            deleted_count = cursor.rowcount
            conn.commit()

        return deleted_count

    def clear_all(self):
        """Clear all cache entries"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM market_prices")
            conn.commit()
