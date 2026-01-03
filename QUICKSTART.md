# 🚀 PokeBuy Quick Start Guide

Your PokeBuy tool is ready to use! Here's everything you need to know to start finding Pokemon card deals.

## ✅ Setup Complete

Your eBay API key is already configured and ready to go!

## 🎯 Basic Usage

### Find Charizard Deals
```bash
python pokebuy.py search "Charizard PSA 10"
```

### Find Any Pokemon at 60%+ Off
```bash
python pokebuy.py search "Pikachu" --discount 60
```

### Find Vintage Cards Under $200
```bash
python pokebuy.py search "Base Set Holo" --max-price 200 --discount 50
```

### Search for Specific Graded Cards
```bash
# PSA 10
python pokebuy.py search "Umbreon VMAX PSA 10"

# BGS 9.5
python pokebuy.py search "Charizard BGS 9.5"

# Any PSA 9
python pokebuy.py search "Blastoise Base Set PSA 9"
```

### Auction Hunting (Best Deals!)
```bash
python pokebuy.py search "Mewtwo" --listing-type Auction --discount 55
```

### Export Deals to CSV
```bash
python pokebuy.py search "Charizard" --export charizard_deals.csv
```

## 📈 Price Trend Analysis

Check if a card's price is rising or falling:

```bash
python pokebuy.py trend "Charizard Base Set PSA 10"
```

Use this to decide:
- **Rising** 📈: Buy now before it gets more expensive
- **Falling** 📉: Wait for better deals
- **Stable** ➡️: Good time to buy

## 🎨 Understanding Results

### Deal Quality Indicators
- 🔥 **Hot Deal**: >60% off - These are exceptional!
- ⭐ **Star Deal**: 50-60% off - Great deals
- 💎 **Good Deal**: 40-50% off - Solid savings
- 📦 **Regular Deal**: Meets your threshold

### Listing Types
- 🔨 **Auction**: Bid to win (can get steals!)
- 💰 **Buy It Now**: Instant purchase

### Deal Score
- **90-100**: Exceptional deal - buy immediately!
- **80-89**: Excellent deal - very strong
- **70-79**: Very good deal - worth buying
- **60-69**: Good deal - solid value
- **<60**: Decent deal - review carefully

## 💡 Pro Tips

### 1. Start Broad, Then Narrow
```bash
# Start here
python pokebuy.py search "Charizard"

# Then narrow down
python pokebuy.py search "Charizard Base Set PSA 9"
```

### 2. Lower Discount for Rare Cards
```bash
# Popular cards - use 50%+
python pokebuy.py search "Pikachu VMAX" --discount 50

# Rare vintage - use 40%
python pokebuy.py search "Charizard 1st Edition" --discount 40
```

### 3. Check Multiple Grades
```bash
# PSA 10 (most expensive)
python pokebuy.py search "Charizard PSA 10"

# PSA 9 (better deals, still great!)
python pokebuy.py search "Charizard PSA 9"
```

### 4. Daily Deal Hunting
Create a watchlist script:

```bash
#!/bin/bash
# watchlist.sh

echo "=== Daily Pokemon Card Deal Check ==="
echo ""

echo "🔥 Charizard Deals:"
python pokebuy.py search "Charizard PSA 10" --max-results 3

echo ""
echo "⚡ Pikachu Deals:"
python pokebuy.py search "Pikachu" --max-results 3

echo ""
echo "🌟 Umbreon Deals:"
python pokebuy.py search "Umbreon VMAX Alt Art" --max-results 3
```

Make it executable and run daily:
```bash
chmod +x watchlist.sh
./watchlist.sh
```

### 5. Clear Cache for Fresh Prices
Market prices are cached for 48 hours. For the latest data:

```bash
# Clear expired cache
python pokebuy.py cache-clear --expired

# Clear all cache (forces fresh lookups)
python pokebuy.py cache-clear --all
```

## 🎓 Example Workflows

### Vintage Card Hunter
```bash
# Step 1: Explore what's available
python pokebuy.py search "Base Set Charizard"

# Step 2: Focus on your grade
python pokebuy.py search "Base Set Charizard PSA 9" --min-price 200 --max-price 800

# Step 3: Export for review
python pokebuy.py search "Base Set Charizard PSA 9" --export charizard.csv
```

### Budget Collector
```bash
# Find vintage holos under $50
python pokebuy.py search "Vintage Holo" --max-price 50 --discount 45

# Find specific Pokemon in budget
python pokebuy.py search "Gengar Holo" --max-price 30 --discount 40
```

### Modern Card Deals
```bash
# New set releases
python pokebuy.py search "Temporal Forces Secret" --discount 40

# Chase cards
python pokebuy.py search "Alt Art" --discount 45 --listing-type FixedPrice
```

### Investment Hunting
```bash
# Check trend first
python pokebuy.py trend "Umbreon VMAX Alt Art"

# If rising, find deals
python pokebuy.py search "Umbreon VMAX Alt Art" --discount 45

# Export for tracking
python pokebuy.py search "Umbreon VMAX Alt Art" --export umbreon_$(date +%Y%m%d).csv
```

## 🔧 All Commands

```bash
# Search for deals
python pokebuy.py search "QUERY" [OPTIONS]

# Options:
  --discount, -d      Minimum discount % (default: 50)
  --max-results, -n   Max results to show (default: 20)
  --min-price         Minimum price filter
  --max-price         Maximum price filter
  --listing-type      Auction or FixedPrice
  --export            Export to CSV file
  --no-cache          Skip cache, fetch fresh data

# Price trend analysis
python pokebuy.py trend "QUERY"

# Show configuration
python pokebuy.py config

# Clear cache
python pokebuy.py cache-clear --expired  # Only expired
python pokebuy.py cache-clear --all      # All entries

# Help
python pokebuy.py --help
python pokebuy.py search --help
```

## ⚠️ Important Notes

### Always Verify Listings
Before buying, ALWAYS:
1. ✅ Click through to the actual eBay listing
2. ✅ Check photos carefully (front, back, edges)
3. ✅ Read the full description
4. ✅ Verify seller feedback and rating
5. ✅ Check return policy
6. ✅ Confirm it's the exact card/grade you want
7. ✅ Watch for counterfeits (especially high-value cards)

### Market Value Notes
- Market value is calculated from sold listings (last 60 days)
- Outliers are removed for accuracy
- Very rare or new cards may not have enough data
- Prices fluctuate - always double-check current market

### Best Practices
- Run searches regularly (new listings appear daily)
- Use price trends to time your purchases
- Consider seller feedback (98%+ is ideal)
- Factor in shipping costs (included in price display)
- For auctions, watch ending times carefully
- Build a watchlist of cards you want

## 🐛 Troubleshooting

**"No deals found"**
- Lower discount threshold: `--discount 40`
- Use broader search: `"Charizard"` instead of `"Charizard Base Set Shadowless 1st Edition PSA 10"`
- Check if card is too new/rare

**"Could not determine market value"**
- Not enough sold listings (need 3+ in last 60 days)
- Try broader search terms
- Card might be too rare or too new

**Strange market values**
- Clear cache: `python pokebuy.py cache-clear --all`
- Re-run search with `--no-cache` flag

## 📚 More Information

- **README.md**: Overview and features
- **USAGE.md**: Comprehensive guide with advanced examples
- **GitHub**: Check for updates and new features

## 🎯 Ready to Hunt!

Start finding deals right now:

```bash
# Popular searches to try:
python pokebuy.py search "Charizard"
python pokebuy.py search "Pikachu VMAX"
python pokebuy.py search "Umbreon Alt Art"
python pokebuy.py search "Base Set Holo"
python pokebuy.py search "PSA 10" --max-price 100
```

---

**Happy hunting! May you find amazing deals on all your chase cards! 🎴✨**

Got questions? Check USAGE.md for detailed examples and workflows!
