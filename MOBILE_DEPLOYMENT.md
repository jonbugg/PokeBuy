# 📱 PokeBuy Mobile Deployment Guide

This guide shows you how to access PokeBuy from your mobile device!

## 🌐 Option 1: Deploy to Replit (Easiest - 5 minutes!)

**Replit** is a free online coding platform that lets you run PokeBuy in the cloud and access it from any device.

### Steps:

1. **Go to Replit.com**
   - Visit https://replit.com
   - Sign up for a free account (or log in with Google/GitHub)

2. **Create New Repl**
   - Click "+ Create Repl"
   - Choose "Import from GitHub"
   - Paste your repository URL: `https://github.com/jonbugg/PokeBuy`
   - Click "Import from GitHub"

3. **Configure Environment**
   - In the Replit sidebar, click "Secrets" (🔒 icon)
   - Add a new secret:
     - Key: `EBAY_APP_ID`
     - Value: `Jonathan-PinPrice-PRD-9ad97ab13-49d103a6`
   - Click "Add new secret"

4. **Run the Web App**
   - In the Shell (bottom panel), type:
     ```bash
     pip install -r requirements.txt
     python web_app.py
     ```
   - Or click the "Run" button at the top

5. **Access from Mobile**
   - Replit will show you a URL like: `https://pokebuy-yourname.replit.app`
   - Copy this URL
   - Open it on your phone's browser
   - Bookmark it for easy access!

**That's it!** You can now search for Pokemon card deals from your phone! 📱🎴

---

## 🚀 Option 2: Deploy to Railway (Free Tier)

Railway is another great option for hosting web apps.

### Steps:

1. **Sign Up**
   - Go to https://railway.app
   - Sign up with GitHub

2. **Deploy from GitHub**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your PokeBuy repository
   - Click "Deploy"

3. **Add Environment Variables**
   - In your project, go to "Variables"
   - Add: `EBAY_APP_ID=Jonathan-PinPrice-PRD-9ad97ab13-49d103a6`

4. **Configure Start Command**
   - In "Settings" → "Deploy"
   - Set start command: `python web_app.py`

5. **Generate Domain**
   - Go to "Settings" → "Networking"
   - Click "Generate Domain"
   - You'll get a URL like: `pokebuy.up.railway.app`

6. **Access from Mobile**
   - Open the Railway URL on your phone
   - Bookmark it!

---

## 💻 Option 3: Run on Your Computer + Access from Phone

If you have a computer on the same WiFi network as your phone:

### Steps:

1. **On Your Computer:**
   ```bash
   cd PokeBuy
   pip install flask
   python web_app.py
   ```

2. **Find Your Computer's IP Address:**

   **On Mac/Linux:**
   ```bash
   ifconfig | grep "inet "
   ```

   **On Windows:**
   ```bash
   ipconfig
   ```

   Look for something like `192.168.1.100`

3. **On Your Phone:**
   - Make sure you're on the same WiFi network
   - Open your phone's browser
   - Go to: `http://YOUR_IP:5000`
   - Example: `http://192.168.1.100:5000`

4. **Bookmark It**
   - Add to home screen for quick access

⚠️ **Note:** This only works when your computer is on and connected to the same WiFi network.

---

## ☁️ Option 4: Deploy to Heroku (Requires Credit Card)

Heroku offers free tier but requires a credit card on file.

### Steps:

1. **Install Heroku CLI**
   ```bash
   # Mac
   brew install heroku/brew/heroku

   # Or download from: https://devcenter.heroku.com/articles/heroku-cli
   ```

2. **Create Heroku App**
   ```bash
   cd PokeBuy
   heroku login
   heroku create pokebuy-yourname
   ```

3. **Add Procfile**
   Create a file named `Procfile` (no extension) with:
   ```
   web: python web_app.py
   ```

4. **Set Environment Variable**
   ```bash
   heroku config:set EBAY_APP_ID=Jonathan-PinPrice-PRD-9ad97ab13-49d103a6
   ```

5. **Deploy**
   ```bash
   git add .
   git commit -m "Add web interface"
   git push heroku main
   ```

6. **Open on Mobile**
   ```bash
   heroku open
   ```
   - Bookmark the URL on your phone!

---

## 🎨 Web Interface Features

When you open PokeBuy on mobile, you'll see:

### Home Screen
- 🔍 Search bar for any Pokemon or card
- ⚙️ Advanced filters (discount %, price range, listing type)
- Quick search buttons (Charizard, Pikachu, Umbreon, etc.)

### Search Results
- Beautiful card grid optimized for mobile
- Each deal shows:
  - Card image
  - Market value vs listing price
  - Savings amount and discount %
  - Deal score (0-100)
  - Deal quality indicator (🔥 Hot, ⭐ Star, 💎 Good)
  - Auction 🔨 or Buy It Now 💰
  - Seller rating
  - Direct link to eBay listing

### Mobile-Friendly
- Responsive design (works on all screen sizes)
- Touch-optimized buttons
- Fast loading
- Works offline once loaded (for viewing saved results)

---

## 🔥 Quick Start (After Deployment)

1. **Open the web app URL on your phone**
2. **Try a search:**
   - Type: "Charizard PSA 10"
   - Click 🔍 Search
   - Wait for results
3. **Browse deals:**
   - Tap any card to see details
   - Tap "View on eBay →" to see the listing
4. **Use filters:**
   - Tap "⚙️ Advanced Filters"
   - Adjust discount %, price range, etc.
   - Search again

---

## 💡 Pro Tips for Mobile Use

### 1. Add to Home Screen (iOS)
1. Open PokeBuy in Safari
2. Tap the Share button
3. Tap "Add to Home Screen"
4. Now PokeBuy appears like an app!

### 2. Add to Home Screen (Android)
1. Open PokeBuy in Chrome
2. Tap menu (⋮)
3. Tap "Add to Home Screen"
4. PokeBuy is now an app!

### 3. Quick Searches
Use the pre-made quick search buttons for instant results:
- 🔥 Charizard PSA 10
- ⚡ Pikachu
- 🌙 Umbreon Alt Art
- ✨ Base Set Holo

### 4. Save Your Favorite Searches
Bookmark specific searches in your browser:
- Search for "Umbreon VMAX"
- Bookmark the URL
- Quick access next time!

### 5. Enable Notifications (If using PWA)
Some browsers support notifications for new deals (coming soon!)

---

## 📊 Comparison: Which Deployment Option?

| Option | Setup Time | Cost | Always Available? | Best For |
|--------|-----------|------|-------------------|----------|
| **Replit** | 5 min | Free | ✅ Yes | Beginners, quick start |
| **Railway** | 10 min | Free (500 hrs/mo) | ✅ Yes | Best free option |
| **Local + Phone** | 2 min | Free | ❌ Only when PC on | Testing, home use |
| **Heroku** | 15 min | Free* (*card required) | ✅ Yes | Professional use |

**Recommendation:** Start with **Replit** - it's the easiest and completely free!

---

## 🐛 Troubleshooting

### "Cannot connect" or "Network error"
- Make sure the server is running
- Check your internet connection
- Try refreshing the page

### "No deals found"
- Lower the discount threshold (try 40% instead of 50%)
- Use broader search terms
- Check if the card is too rare/new

### Slow loading
- eBay's API might be slow
- Try searching for more common cards first
- Close other apps on your phone

### App not updating
- Clear browser cache
- Force refresh (pull down on mobile)
- Restart the deployment

---

## 🎯 Next Steps

After deploying:

1. ✅ Bookmark the URL on your phone
2. ✅ Add to home screen
3. ✅ Try searching for your favorite Pokemon
4. ✅ Set up filters for your budget
5. ✅ Share with fellow collectors!

---

## 🚀 Future Enhancements (Coming Soon!)

Ideas for improving the mobile experience:
- [ ] Push notifications for watchlist cards
- [ ] Save favorite searches
- [ ] Price drop alerts
- [ ] Dark mode
- [ ] Offline mode
- [ ] Share deals with friends
- [ ] Price history charts

---

**You're all set! Start hunting for Pokemon card deals on your phone! 🎴📱✨**

Questions? Check the main README.md or USAGE.md for more details!
