"""Grading fees per card, from each company's own site (read 2026-11-07). Edit here when they change.

Each tier: (name, fee in USD, max declared value in USD, turnaround note, minimum cards).
The cheapest tier whose max declared value covers the card's graded value is the one you'd use.
"""

FEES = {
    "TAG": {
        "source": "taggrading.com/pages/grading",
        "tiers": [
            ("Value", 29.95, 250, "~90 business days", 10),
            ("Base", 39.95, 500, "~60 business days", 5),
            ("Standard", 59.95, 1000, "~45 business days", 1),
            ("Priority", 79.95, 1500, "~30 business days", 1),
            ("Express", 149.95, 2500, "~10 business days", 1),
            ("Premier", 299.95, 10000, "3-5 business days", 1),
        ],
    },
    "PSA": {
        "source": "psacard.com/services/tradingcardgrading",
        "tiers": [
            ("Value", 39.99, 500, "90-100 business days (paused when read)", 1),
            ("Standard", 59.99, 1000, "70-80 business days", 1),
            ("Priority", 79.99, 1500, "50-60 business days", 1),
            ("Express", 199.00, 2500, "20-30 business days", 1),
            ("Super Express", 349.00, 5000, "10-15 business days", 1),
            ("Premier", 599.00, 10000, "7-10 business days", 1),
        ],
    },
    "CGC": {
        "source": "cgccards.com/submit/services-fees/cgc",
        "tiers": [
            ("Bulk", 17.00, 500, "~150 days", 25),
            ("Economy", 20.00, 1000, "~90 days", 1),
            ("Standard", 55.00, 3000, "~10 days", 1),
            ("Express", 100.00, 10000, "~5 days", 1),
            ("WalkThrough", 300.00, 100000, "~2 days", 1),
        ],
    },
}


def all_fees():
    return FEES
