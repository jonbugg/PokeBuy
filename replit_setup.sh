#!/bin/bash
# PokeBuy Replit Setup Script
# Run this to set up PokeBuy on Replit

echo "🎴 Setting up PokeBuy..."

# Create directory structure
mkdir -p src/{api,models,services,cli} static/{css,js} templates data

# Install dependencies
pip install flask requests python-dotenv beautifulsoup4 --quiet

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Add your files (copy from GitHub or upload)"
echo "2. Set EBAY_APP_ID in Secrets"
echo "3. Run: python web_app.py"
