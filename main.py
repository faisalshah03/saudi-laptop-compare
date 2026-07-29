#!/usr/bin/env python3
"""
Main orchestration script for Saudi Arabia Laptop Price Comparison System
Phases: 1) Scrape → 2) Merge → 3) Export Excel → 4) Dashboard
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Setup path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))

from config.config import FIRECRAWL_API_KEY, OUTPUT_DIR, DATA_DIR
from scrapers.jarir_scraper import JarirScraper
from scrapers.amazon_scraper import AmazonScraper
from utils.product_matcher import ProductMatcher
from utils.excel_exporter import ExcelExporter


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def phase_1_scrape() -> list:
    """Phase 1: Scrape all platforms for laptop and desktop data."""
    print_section("PHASE 1: DATA EXTRACTION")

    all_products = []

    # Scrape Jarir
    print("📍 Scraping Jarir.com...")
    try:
        jarir = JarirScraper()
        jarir_products = jarir.scrape_all(max_per_category=20)
        print(f"✓ Jarir: {len(jarir_products)} products")
        all_products.extend(jarir_products)
    except Exception as e:
        print(f"✗ Jarir Error: {e}")

    # Scrape Amazon.sa
    print("\n📍 Scraping Amazon.sa...")
    try:
        amazon = AmazonScraper()
        amazon_products = amazon.scrape_laptops(max_products=25)
        print(f"✓ Amazon.sa: {len(amazon_products)} products")
        all_products.extend(amazon_products)
    except Exception as e:
        print(f"✗ Amazon.sa Error: {e}")

    # TODO: Add Extra.com, Noon.com scrapers here

    print(f"\n✓ Phase 1 Complete: {len(all_products)} total products scraped\n")
    return all_products


def phase_2_merge(raw_products: list) -> dict:
    """Phase 2: Intelligent product matching and merging."""
    print_section("PHASE 2: PRODUCT MATCHING & MERGING")

    print(f"📊 Matching {len(raw_products)} products across platforms...")

    matcher = ProductMatcher()
    unified_products = matcher.merge_products(raw_products)

    print(f"✓ Created {len(unified_products)} unique master products")

    # Summary stats
    price_available = sum(1 for p in unified_products.values()
                         if p.get('best_price') is not None)
    print(f"✓ {price_available} products with price data\n")

    return unified_products


def phase_3_export_excel(unified_products: dict, raw_products: list):
    """Phase 3: Generate Excel file."""
    print_section("PHASE 3: EXCEL EXPORT")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Convert unified dict to list
    products_list = list(unified_products.values())

    # Generate Excel
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    excel_path = f'{OUTPUT_DIR}/saudi_laptop_prices_{timestamp}.xlsx'

    print(f"📝 Generating Excel file: {os.path.basename(excel_path)}")
    ExcelExporter.merge_data_and_export(products_list, raw_products, excel_path)

    return excel_path


def phase_4_dashboard():
    """Phase 4: Setup web dashboard (placeholder)."""
    print_section("PHASE 4: WEB DASHBOARD")
    print("⏳ Dashboard setup (next step after Excel validation)")
    print("   Options:")
    print("   • Streamlit (lightweight, fast)")
    print("   • React + FastAPI (full-stack)")
    print("   • Flask + Vue.js (lightweight)")


def main():
    """Main orchestration."""
    print("\n" + "="*70)
    print("  🌏 SAUDI LAPTOP PRICE COMPARISON SYSTEM")
    print("  Amazon.sa | Jarir.com | Extra.com | Noon.com")
    print("="*70)

    try:
        # Phase 1: Scrape
        raw_products = phase_1_scrape()

        if not raw_products:
            print("❌ No products scraped. Exiting.")
            return

        # Save raw products
        os.makedirs(DATA_DIR, exist_ok=True)
        raw_file = f'{DATA_DIR}/raw_products.json'
        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(raw_products, f, ensure_ascii=False, indent=2, default=str)
        print(f"💾 Raw data saved: {raw_file}")

        # Phase 2: Merge
        unified_products = phase_2_merge(raw_products)

        # Save merged products
        merged_file = f'{DATA_DIR}/merged_products.json'
        with open(merged_file, 'w', encoding='utf-8') as f:
            json.dump(list(unified_products.values()), f, ensure_ascii=False, indent=2, default=str)
        print(f"💾 Merged data saved: {merged_file}")

        # Phase 3: Export Excel
        excel_path = phase_3_export_excel(unified_products, raw_products)

        # Phase 4: Dashboard
        phase_4_dashboard()

        # Summary
        print_section("✅ PIPELINE COMPLETE")
        print(f"📊 Total Products: {len(unified_products)}")
        print(f"📁 Output: {OUTPUT_DIR}/")
        print(f"📄 Excel: {os.path.basename(excel_path)}")
        print(f"📊 Raw Data: {raw_file}")
        print(f"📊 Merged Data: {merged_file}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
