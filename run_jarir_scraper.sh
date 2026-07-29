#!/bin/bash

# Saudi Laptop Comparison - Jarir Scraper Runner
# Make sure to: pip install -r requirements.txt first

set -e

echo "=========================================="
echo "Saudi Laptop Comparison System"
echo "Phase 1: Jarir.com Scraper"
echo "=========================================="
echo ""

# Check for Firecrawl API key
if [ -z "$FIRECRAWL_API_KEY" ]; then
    echo "⚠️  FIRECRAWL_API_KEY not set in environment"
    echo "Reading from ~/.zshrc..."
    source ~/.zshrc
fi

if [ -z "$FIRECRAWL_API_KEY" ]; then
    echo "❌ Error: FIRECRAWL_API_KEY not found"
    echo "Please set it: export FIRECRAWL_API_KEY='your-key'"
    exit 1
fi

echo "✓ FIRECRAWL_API_KEY found"
echo ""

# Install dependencies if needed
echo "Checking dependencies..."
pip install -q -r requirements.txt

echo "✓ Dependencies installed"
echo ""

# Run the scraper
echo "Starting Jarir.com scraper..."
export PYTHONPATH=/Users/faisals/Documents/saudi-laptop-compare:$PYTHONPATH
python3 /Users/faisals/Documents/saudi-laptop-compare/src/scrapers/jarir_scraper.py

echo ""
echo "✓ Scraper completed"
echo "Sample data saved to: /Users/faisals/Documents/saudi-laptop-compare/data/jarir_sample.json"
