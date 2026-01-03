# PokeBuy Usage Guide

This guide provides detailed examples and tips for using PokeBuy effectively.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Basic Searches](#basic-searches)
3. [Advanced Searches](#advanced-searches)
4. [Understanding Results](#understanding-results)
5. [Tips & Tricks](#tips--tricks)
6. [Troubleshooting](#troubleshooting)

## Getting Started

### First Time Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create your `.env` file:
   ```bash
   cp .env.example .env
   ```

3. Add your eBay App ID to `.env`:
   ```
   EBAY_APP_ID=YourAppIdHere
   ```

4. Test the configuration:
   ```bash
   python pokebuy.py config
   ```

### Getting an eBay API Key

1. Go to https://developer.ebay.com/
2. Sign in or create an account (it's free!)
3. Go to "My Account" → "Application Keys"
4. Create a new keyset for "Production" or "Sandbox"
5. Copy your "App ID (Client ID)"
6. Paste it into your `.env` file

## Basic Searches

### Search by Pokemon Name

Find any cards featuring a specific Pokemon:

```bash
python pokebuy.py search "Charizard"
```

This will find ALL Charizard cards (vintage, modern, graded, ungraded) at 50%+ discount.

### Search for Specific Card

Be more specific to narrow results:

```bash
python pokebuy.py search "Charizard Base Set"
```

### Search for Graded Cards

Find professionally graded cards:

```bash
# PSA graded
python pokebuy.py search "Charizard PSA 10"
python pokebuy.py search "Pikachu PSA 9"

# BGS graded
python pokebuy.py search "Blastoise BGS 9.5"

# CGC graded
python pokebuy.py search "Mewtwo CGC 9"
```

### Search for Specific Sets

Target cards from specific sets:

```bash
python pokebuy.py search "Charizard Base Set"
python pokebuy.py search "Umbreon Neo Discovery"
python pokebuy.py search "Rayquaza Evolving Skies"
python pokebuy.py search "Pikachu 151"
```

## Advanced Searches

### Adjust Discount Threshold

Find cards at different discount levels:

```bash
# Ultra deals - 70%+ off (rare but amazing)
python pokebuy.py search "Gyarados" --discount 70

# Great deals - 60%+ off
python pokebuy.py search "Venusaur" --discount 60

# Good deals - 40%+ off (more results)
python pokebuy.py search "Dragonite" --discount 40

# Any discount - 20%+ off (many results)
python pokebuy.py search "Pikachu VMAX" --discount 20
```

### Limit Number of Results

Control how many deals you see:

```bash
# Show top 5 deals only
python pokebuy.py search "Charizard" --max-results 5

# Show top 50 deals
python pokebuy.py search "Eevee" --max-results 50
```

### Filter by Price Range

Set minimum and maximum prices:

```bash
# Budget shopping - under $50
python pokebuy.py search "Holo Rare" --max-price 50

# Mid-range - $50 to $200
python pokebuy.py search "Charizard" --min-price 50 --max-price 200

# High-end - $500+
python pokebuy.py search "Charizard Base Set PSA 10" --min-price 500
```

### Filter by Listing Type

Choose between auctions and Buy It Now:

```bash
# Auctions only (potential for steals!)
python pokebuy.py search "Mewtwo" --listing-type Auction

# Buy It Now only (instant purchase)
python pokebuy.py search "Pikachu" --listing-type FixedPrice
```

### Combine Multiple Filters

Stack filters for precise searches:

```bash
# Vintage PSA 9 Charizard, $200-$1000, 60%+ off, auctions only
python pokebuy.py search "Charizard Base Set PSA 9" \
  --discount 60 \
  --min-price 200 \
  --max-price 1000 \
  --listing-type Auction \
  --max-results 10
```

### Export Results to CSV

Save deals for analysis or record-keeping:

```bash
# Export to CSV
python pokebuy.py search "Charizard" --export charizard_deals.csv

# Export with specific filters
python pokebuy.py search "Pikachu PSA 10" \
  --discount 55 \
  --export pikachu_deals_$(date +%Y%m%d).csv
```

## Understanding Results

### Reading the Results Table

```
┃   ┃ Card                                      ┃ Market    ┃ Price    ┃ Save      ┃ Discount ┃ Score ┃ Type ┃
┃ 🔥 ┃ Charizard Base Set Shadowless PSA 9     ┃ $2500.00 ┃ $899.99  ┃ $1600.01 ┃ 64.0%   ┃ 87   ┃ 💰   ┃
```

- **Emoji**: Deal quality indicator
  - 🔥 Hot Deal (>60% off)
  - ⭐ Star Deal (50-60% off)
  - 💎 Good Deal (40-50% off)
  - 📦 Regular Deal (meets threshold)

- **Card**: Card name (clickable link in supported terminals)
- **Market**: Calculated market value from sold listings
- **Price**: Current listing price (including shipping if applicable)
- **Save**: How much you save vs. market value
- **Discount**: Discount percentage
- **Score**: Deal quality score (0-100)
  - 90-100: Exceptional deal
  - 80-89: Excellent deal
  - 70-79: Very good deal
  - 60-69: Good deal
  - <60: Decent deal

- **Type**:
  - 🔨 Auction (bid to win)
  - 💰 Buy It Now (instant purchase)

### Deal Score Explained

The deal score (0-100) is calculated from:

1. **Discount % (40 points max)**
   - Higher discount = higher score
   - 50% off = 20 points
   - 75% off = 30 points
   - 100% off = 40 points

2. **Absolute Savings (30 points max)**
   - More dollars saved = higher score
   - $50 saved = 7.5 points
   - $100 saved = 15 points
   - $200+ saved = 30 points

3. **Listing Quality (20 points max)**
   - Seller feedback 98%+ = 10 points
   - Seller feedback 95%+ = 5 points
   - Free/cheap shipping = 5 points
   - Buy It Now = 5 points

4. **Card Value Tier (10 points max)**
   - $500+ card = 10 points
   - $200-499 card = 7 points
   - $100-199 card = 5 points
   - $50-99 card = 3 points

## Price Trend Analysis

Check if a card's price is rising or falling:

```bash
python pokebuy.py trend "Charizard Base Set PSA 10"
```

This shows:
- Sample size (number of sold listings in last 90 days)
- Average sold price
- Price range (min to max)
- Trend direction (rising 📈, falling 📉, stable ➡️)

Use this to decide:
- **Rising trend**: Buy now before it gets more expensive
- **Falling trend**: Wait for better deals
- **Stable trend**: Good time to buy

## Tips & Tricks

### 1. Start Broad, Then Narrow

Start with general searches:
```bash
python pokebuy.py search "Charizard"
```

Then refine based on what you see:
```bash
python pokebuy.py search "Charizard Base Set PSA 9"
```

### 2. Watch for Auction Endings

Auctions can offer the best deals but require timing:
```bash
python pokebuy.py search "Charizard" --listing-type Auction
```

Check the listing to see when it ends!

### 3. Clear Cache for Fresh Prices

Market prices are cached for 48 hours. For fresh data:
```bash
# Clear expired cache
python pokebuy.py cache-clear --expired

# Clear all cache (forces fresh lookups)
python pokebuy.py cache-clear --all
```

### 4. Check Price Trends Before Buying

```bash
# Check trend first
python pokebuy.py trend "Umbreon VMAX"

# Then search for deals
python pokebuy.py search "Umbreon VMAX"
```

### 5. Use Specific Grades for Graded Cards

Be specific about the grade you want:
```bash
# PSA 10 only
python pokebuy.py search "Charizard Base Set PSA 10"

# PSA 9 (usually better deals than 10)
python pokebuy.py search "Charizard Base Set PSA 9"
```

### 6. Export and Track Deals Over Time

```bash
# Daily exports to track price changes
python pokebuy.py search "Charizard PSA 10" --export charizard_$(date +%Y%m%d).csv
```

Compare CSV files over days/weeks to spot patterns!

### 7. Set Realistic Discount Thresholds

- **50-60%**: Great for common/modern cards
- **40-50%**: Better for vintage/rare cards
- **30-40%**: Realistic for highly sought-after cards

### 8. Verify Before Buying

Always:
1. Click through to the actual listing
2. Check the photos carefully
3. Read the description
4. Verify seller feedback
5. Check return policy
6. Confirm it's the exact card you want

### 9. Understand Market Value Calculation

Market value is based on:
- Sold listings from last 60 days
- Outliers removed (top/bottom 10%)
- Median price (robust to extreme values)

If market value seems off:
- Check if enough sold listings exist
- Consider if the card is very rare/new
- Clear cache and re-search

### 10. Best Times to Search

- **Sunday evenings**: Many auctions end
- **After set releases**: Modern cards at high supply
- **Off-season (summer)**: Less competition
- **Economic downturns**: More people selling

## Troubleshooting

### "No deals found"

**Possible causes:**
1. Discount threshold too high
2. Card too rare (no recent sales)
3. Prices have recently increased

**Solutions:**
```bash
# Lower discount threshold
python pokebuy.py search "Charizard" --discount 40

# Broaden search term
python pokebuy.py search "Charizard" # instead of "Charizard Base Set Shadowless 1st Edition"

# Check if market data exists
python pokebuy.py trend "Charizard"
```

### "Could not determine market value"

**Cause:** Not enough sold listings in past 60 days

**Solutions:**
- Try broader search terms
- Card might be too new or too rare
- Wait for more sales data to accumulate

### "eBay API Key not configured"

**Cause:** Missing or invalid eBay App ID

**Solution:**
1. Check `.env` file exists
2. Verify `EBAY_APP_ID=` is set correctly
3. Ensure no extra spaces or quotes
4. Get a valid API key from https://developer.ebay.com/

### Results seem inaccurate

**Solutions:**
```bash
# Clear cache and re-search
python pokebuy.py cache-clear --all
python pokebuy.py search "Your Search" --no-cache

# Check trend data
python pokebuy.py trend "Your Search"
```

### Too many/too few results

**Solutions:**
```bash
# Adjust max results
python pokebuy.py search "Pikachu" --max-results 100

# Adjust discount threshold
python pokebuy.py search "Pikachu" --discount 30  # More results
python pokebuy.py search "Pikachu" --discount 70  # Fewer results
```

## Example Workflows

### Workflow 1: Vintage Card Hunter

```bash
# Step 1: Check what's available
python pokebuy.py search "Charizard Base Set"

# Step 2: Focus on graded cards
python pokebuy.py search "Charizard Base Set PSA"

# Step 3: Target specific grade and price range
python pokebuy.py search "Charizard Base Set PSA 9" \
  --min-price 200 \
  --max-price 800 \
  --discount 50

# Step 4: Export for review
python pokebuy.py search "Charizard Base Set PSA 9" \
  --discount 50 \
  --export charizard_deals.csv
```

### Workflow 2: Modern Card Deals

```bash
# Step 1: Search new set
python pokebuy.py search "Temporal Forces" --discount 40

# Step 2: Focus on chase cards
python pokebuy.py search "Temporal Forces Secret Rare" --discount 45

# Step 3: Quick wins - Buy It Now only
python pokebuy.py search "Temporal Forces" \
  --discount 40 \
  --listing-type FixedPrice \
  --max-results 20
```

### Workflow 3: Investment Hunting

```bash
# Step 1: Check price trends
python pokebuy.py trend "Umbreon VMAX Alt Art"

# Step 2: If rising, find deals quickly
python pokebuy.py search "Umbreon VMAX Alt Art" \
  --discount 45 \
  --listing-type FixedPrice

# Step 3: Export for comparison
python pokebuy.py search "Umbreon VMAX Alt Art" \
  --export umbreon_$(date +%Y%m%d).csv
```

### Workflow 4: Budget Collecting

```bash
# Step 1: Set budget
python pokebuy.py search "Holo Rare" \
  --max-price 25 \
  --discount 50

# Step 2: Find specific Pokemon in budget
python pokebuy.py search "Gengar Holo" \
  --max-price 30 \
  --discount 45

# Step 3: Export all budget deals
python pokebuy.py search "Vintage Holo" \
  --max-price 50 \
  --discount 40 \
  --max-results 50 \
  --export budget_deals.csv
```

## Advanced Tips

### Combining with eBay Saved Searches

1. Use PokeBuy to find current deals
2. Set up eBay saved searches for cards you want
3. Run PokeBuy daily to catch new listings
4. Compare against your saved search notifications

### Building a Watchlist

Create a script to check multiple cards:

```bash
#!/bin/bash
# watchlist.sh

python pokebuy.py search "Charizard Base Set PSA 10" --max-results 3
python pokebuy.py search "Blastoise Base Set PSA 10" --max-results 3
python pokebuy.py search "Venusaur Base Set PSA 10" --max-results 3
python pokebuy.py search "Pikachu VMAX Rainbow" --max-results 3
```

Run daily:
```bash
chmod +x watchlist.sh
./watchlist.sh
```

### Seasonal Strategies

- **January-February**: Tax refund season, more buyers
- **March-April**: Spring cleaning, more sellers
- **May-June**: Pre-summer deals
- **July-August**: Lowest prices (vacation season)
- **September-October**: Back to school, moderate activity
- **November-December**: Holiday buying, higher prices

Adjust discount thresholds seasonally!

---

Happy deal hunting! 🎴✨
