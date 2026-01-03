# 🎴 PokeBuy - Pokemon Card Deal Finder

Find Pokemon cards listed at less than 50% their market value on eBay!

PokeBuy helps you discover amazing deals on Pokemon cards by comparing active eBay listings against historical sold prices. Whether you're hunting for vintage Charizards or modern chase cards, PokeBuy finds the best deals and highlights them for you.

## ✨ Features

- 🔍 **Smart Search**: Search by Pokemon name or specific card
- 💰 **Market Value Analysis**: Calculates market prices from sold eBay listings
- 📊 **Deal Scoring**: Intelligent algorithm ranks deals by quality
- 🔥 **Deal Tiers**: Hot deals (>60% off), Star deals (50-60% off), and more
- 💾 **Smart Caching**: Caches market prices to reduce API calls
- 📈 **Price Trends**: Analyze if card prices are rising or falling
- 📁 **Export**: Save deals to CSV for further analysis
- 🎨 **Beautiful CLI**: Rich terminal interface with colors and tables

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- eBay Developer Account (free)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/PokeBuy.git
cd PokeBuy
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your eBay API credentials:
```bash
cp .env.example .env
```

Edit `.env` and add your eBay App ID:
```
EBAY_APP_ID=your_app_id_here
```

Get your free eBay API credentials at: https://developer.ebay.com/

### Usage

#### Basic Search

Find deals on a Pokemon card:
```bash
python pokebuy.py search "Charizard PSA 10"
```

#### Search by Pokemon Name

Find any Charizard cards at 50%+ discount:
```bash
python pokebuy.py search "Charizard"
```

#### Specify Discount Threshold

Find Pikachu cards at 60%+ discount:
```bash
python pokebuy.py search "Pikachu" --discount 60
```

#### Filter by Grading

Find graded vintage cards:
```bash
python pokebuy.py search "Charizard Base Set PSA 9"
python pokebuy.py search "Blastoise BGS 9.5"
```

#### Auction vs Buy It Now

Search only auctions (for potential steals):
```bash
python pokebuy.py search "Mewtwo" --listing-type Auction
```

Search only Buy It Now (for immediate purchase):
```bash
python pokebuy.py search "Pikachu VMAX" --listing-type FixedPrice
```

#### Price Range Filters

```bash
python pokebuy.py search "Umbreon" --min-price 50 --max-price 200
```

#### Export Results

Save deals to CSV:
```bash
python pokebuy.py search "Charizard" --export deals.csv
```

#### View Price Trends

Analyze price trends over 90 days:
```bash
python pokebuy.py trend "Charizard Base Set PSA 10"
```

#### Check Configuration

```bash
python pokebuy.py config
```

#### Clear Cache

```bash
python pokebuy.py cache-clear --expired  # Clear only expired entries
python pokebuy.py cache-clear --all      # Clear all cache
```

## 📖 Examples

### Example 1: Vintage Charizard Hunt

Looking for a vintage Charizard PSA 9 at 50% off:
```bash
python pokebuy.py search "Charizard Base Set PSA 9" --discount 50
```

### Example 2: Modern Card Deals

Find modern Pikachu VMAX cards at any discount:
```bash
python pokebuy.py search "Pikachu VMAX" --discount 30 --max-results 30
```

### Example 3: Budget Shopping

Find deals under $100:
```bash
python pokebuy.py search "Gyarados Holo" --max-price 100 --discount 40
```

### Example 4: High-End Cards

Find expensive cards with big savings:
```bash
python pokebuy.py search "Lugia Neo Genesis PSA 10" --min-price 500
```

## 🎯 How It Works

1. **Market Value Calculation**: PokeBuy searches eBay's sold listings from the past 60 days and calculates a median market value (with outlier filtering)

2. **Active Listing Search**: Searches current eBay listings matching your query

3. **Deal Analysis**: Compares each listing price to market value and calculates:
   - Discount percentage
   - Absolute savings
   - Deal score (0-100)

4. **Smart Ranking**: Deals are ranked by a scoring algorithm that considers:
   - Discount percentage (40 points)
   - Absolute savings amount (30 points)
   - Listing quality - seller feedback, shipping (20 points)
   - Card value tier (10 points)

5. **Results Display**: Shows you the best deals first, with visual indicators

## 🏆 Deal Tiers

- 🔥 **Hot Deal**: >60% off market value
- ⭐ **Star Deal**: 50-60% off market value
- 💎 **Good Deal**: 40-50% off market value
- 📦 **Regular Deal**: Meets your discount threshold

## ⚙️ Configuration

Edit `.env` to customize:

```bash
# eBay API credentials
EBAY_APP_ID=your_app_id_here

# Default settings
DEFAULT_DISCOUNT_THRESHOLD=50    # Default discount %
CACHE_EXPIRY_HOURS=48           # How long to cache market prices
MAX_RESULTS=50                   # Max results per search
```

## 🗂️ Project Structure

```
PokeBuy/
├── src/
│   ├── api/
│   │   └── ebay.py              # eBay API client
│   ├── models/
│   │   ├── card.py              # Card data model
│   │   ├── listing.py           # Listing data model
│   │   └── deal.py              # Deal analysis model
│   ├── services/
│   │   ├── cache.py             # Price caching
│   │   ├── price_analyzer.py   # Market value calculation
│   │   ├── deal_finder.py      # Deal identification
│   │   └── card_parser.py      # Card info extraction
│   ├── cli/
│   │   └── main.py              # CLI interface
│   └── config.py                # Configuration
├── data/
│   └── cache.db                 # SQLite cache (auto-created)
├── pokebuy.py                   # Main entry point
├── requirements.txt
├── .env.example
└── README.md
```

## 🤝 Contributing

Contributions welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests

## 📝 License

MIT License - feel free to use this for personal or commercial purposes!

## ⚠️ Disclaimer

This tool is for educational and personal use. Always verify card authenticity and seller reputation before purchasing. PokeBuy is not affiliated with eBay, Pokemon, or The Pokemon Company.

## 🎓 Tips for Best Results

1. **Be Specific**: "Charizard Base Set PSA 10" is better than just "Charizard"
2. **Check Trends**: Use `trend` command to see if prices are falling (wait) or rising (buy now)
3. **Watch Auctions**: Ending auctions can sometimes offer the best deals
4. **Verify Listings**: Always check the actual listing details and photos
5. **Clear Cache**: If prices seem off, clear the cache to fetch fresh data
6. **Start Broad**: Try broader searches first, then narrow down

## 🐛 Troubleshooting

**"No deals found"**:
- Lower discount threshold: `--discount 40`
- Broaden search query
- Check if there are enough sold listings

**"eBay API Key not configured"**:
- Make sure `.env` file exists and contains `EBAY_APP_ID`
- Get free API key at https://developer.ebay.com/

**"Could not determine market value"**:
- Not enough sold listings in past 60 days
- Try different search terms
- Card might be too rare/new

## 🚀 Future Features

Ideas for future versions:
- [ ] PriceCharting API integration
- [ ] TCGPlayer price comparison
- [ ] Email/SMS alerts for watchlist
- [ ] Web dashboard
- [ ] Machine learning price predictions
- [ ] Multi-currency support
- [ ] Integration with grading company APIs

## 💡 Support

Questions or issues? Open an issue on GitHub!

---

**Happy hunting! May you find all the chase cards! 🎴✨**
