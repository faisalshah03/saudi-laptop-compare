#!/usr/bin/env python3
"""
Test runner for Jarir scraper
Run this to test Phase 1 of the Saudi Laptop Comparison system
"""

import sys
import os
import json
from pathlib import Path

# Setup path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))

# Check API key
if not os.getenv('FIRECRAWL_API_KEY'):
    print("⚠️  FIRECRAWL_API_KEY not set")
    print("Reading from ~/.zshrc...")

    # Try to source zshrc
    home = os.path.expanduser('~')
    zshrc = os.path.join(home, '.zshrc')

    if os.path.exists(zshrc):
        with open(zshrc, 'r') as f:
            for line in f:
                if 'FIRECRAWL_API_KEY' in line:
                    # Extract key from line like: export FIRECRAWL_API_KEY='...'
                    if '=' in line:
                        key_part = line.split('=', 1)[1].strip()
                        key = key_part.strip("'\"")
                        os.environ['FIRECRAWL_API_KEY'] = key
                        print(f"✓ Found key in ~/.zshrc: {key[:20]}...")
                        break

if not os.getenv('FIRECRAWL_API_KEY'):
    print("❌ FIRECRAWL_API_KEY still not found")
    print("Please run: export FIRECRAWL_API_KEY='your-api-key'")
    sys.exit(1)

print("\n" + "="*60)
print("Testing Jarir.com Laptop Scraper")
print("="*60)

try:
    from scrapers.jarir_scraper import JarirScraper

    print("\n[1/3] Initializing scraper...")
    scraper = JarirScraper()

    print("[2/3] Scraping laptops (max 5 products)...")
    laptops = scraper.scrape_laptops(max_products=5)

    print(f"\n[3/3] Scraping desktops (max 5 products)...")
    desktops = scraper.scrape_desktops(max_products=5)

    # Display results
    all_products = scraper.get_products()
    print(f"\n{'='*60}")
    print(f"✓ SUCCESS: Scraped {len(all_products)} products")
    print(f"{'='*60}")

    if all_products:
        print("\nFirst 3 Products:")
        for i, product in enumerate(all_products[:3], 1):
            print(f"\n{i}. {product['raw_title'][:70]}")
            print(f"   Price: SAR {product['price']:,.0f}")
            print(f"   URL: {product['product_url'][:60]}...")
            print(f"   Rating: {product['rating']} ⭐ ({product['review_count']} reviews)")
            print(f"   In Stock: {product['availability']}")

        # Save sample data
        data_dir = project_root / 'data'
        data_dir.mkdir(exist_ok=True)

        sample_file = data_dir / 'jarir_sample.json'
        with open(sample_file, 'w', encoding='utf-8') as f:
            json.dump(all_products[:5], f, ensure_ascii=False, indent=2, default=str)

        print(f"\n✓ Sample data saved: {sample_file}")

    else:
        print("⚠️  No products scraped. Check Firecrawl response.")

except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("\nRun: pip install -r requirements.txt")
    sys.exit(1)

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
