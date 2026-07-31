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
from scrapers.noon_scraper import NoonScraper
from scrapers.extra_scraper import ExtraScraper
from utils.product_matcher import ProductMatcher
from utils.excel_exporter import ExcelExporter
from utils.gap_analyzer import NoonGapAnalyzer
from utils.health_check import (
    check_platform_health, compute_field_coverage, compute_merge_stats,
    log_run, PlatformScrapeFailure
)
from utils.link_refresh import LinkRefresher


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def phase_1_scrape() -> tuple:
    """Phase 1: Scrape all platforms for laptop and desktop data.

    Runs a health check per platform after scraping (see health_check.py):
    a platform returning ~zero products raises PlatformScrapeFailure and
    stops the pipeline (both its primary method and any fallback failed -
    shipping a run silently missing an entire platform is worse than
    failing loudly). A platform returning a low-but-nonzero count is
    logged as 'degraded' and the pipeline continues.
    """
    print_section("PHASE 1: DATA EXTRACTION")

    all_products = []
    platform_counts = {}
    platform_health = {}

    def run_scraper(label, fn):
        """Attempt a scraper independently - one platform crashing
        outright shouldn't prevent the others from being attempted. Any
        exception collapses to a count of 0, which the health check will
        then correctly classify as a hard failure."""
        print(f"\n📍 Scraping {label}...")
        try:
            products = fn()
            print(f"✓ {label}: {len(products)} products")
            return products
        except Exception as e:
            print(f"✗ {label} raised an exception: {e}")
            return []

    # Scrape Jarir (via their real Constructor.io-backed search API - see
    # jarir_scraper.py docstring for why the old category-page approach
    # only ever surfaced ~12 curated products instead of the real catalog)
    jarir_products = run_scraper('Jarir.com', lambda: JarirScraper().scrape_all(max_per_category=1000))
    platform_counts['Jarir'] = len(jarir_products)
    all_products.extend(jarir_products)

    # Scrape Amazon.sa (supports true &page=N pagination, both categories)
    amazon_products = run_scraper('Amazon.sa', lambda: AmazonScraper().scrape_all(max_per_category=60))
    platform_counts['Amazon.sa'] = len(amazon_products)
    all_products.extend(amazon_products)

    # Scrape Noon.com (Saudi) - requires Firecrawl stealth proxy, see
    # noon_scraper.py docstring for why
    noon_products = run_scraper('Noon.com (Saudi)', lambda: NoonScraper().scrape_all(max_per_category=200))
    platform_counts['Noon'] = len(noon_products)
    all_products.extend(noon_products)

    # Scrape Extra.com (Saudi) - no bot-blocking, just needs a longer
    # Firecrawl wait_for the client-rendered product grid to hydrate
    extra_products = run_scraper('Extra.com', lambda: ExtraScraper().scrape_all(max_per_category=450))
    platform_counts['Extra'] = len(extra_products)
    all_products.extend(extra_products)

    # Health checks run after all platforms have been attempted, so a
    # hard-fail on one platform still reports what happened with the
    # others rather than aborting mid-scrape with no visibility.
    for platform, count in platform_counts.items():
        platform_health[platform] = check_platform_health(platform, count)

    print(f"\n✓ Phase 1 Complete: {len(all_products)} total products scraped\n")
    return all_products, platform_counts, platform_health


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


def phase_2b_gap_analysis(unified_products: dict, raw_products: list):
    """Phase 2b: Cross-platform assortment gap analysis vs Noon.

    Runs four separate comparisons:
      - "universe": any of Amazon/Jarir/Extra vs Noon (combined)
      - "jarir": Jarir specifically vs Noon
      - "extra": Extra specifically vs Noon
      - "amazon_sa": Amazon.sa specifically vs Noon

    The per-platform breakdowns matter separately from the combined
    universe view because each source platform has a different
    assortment character (Jarir skews business/enterprise, Amazon.sa's
    scraped sample skews similarly, Extra and Noon skew consumer) - a
    combined number can hide that one platform's overlap with Noon looks
    very different from another's.
    """
    print_section("PHASE 2B: CROSS-PLATFORM GAP ANALYSIS (vs NOON)")

    raw_noon_products = [p for p in raw_products if p.get('source_platform') == 'Noon']
    unified_list = list(unified_products.values())
    analyzer = NoonGapAnalyzer()

    comparisons = {}
    for key, label in [(None, 'universe'), ('jarir', 'jarir'), ('extra', 'extra'), ('amazon_sa', 'amazon_sa')]:
        rows = analyzer.analyze(unified_list, raw_noon_products, base_platform_key=key)
        summary = analyzer.summarize(rows)
        comparisons[label] = {'rows': rows, 'summary': summary}

        display_label = 'Universe (Amazon+Jarir+Extra)' if key is None else key
        print(f"\n[{display_label}] base products: {summary['total_base_products']}")
        print(f"  ✓ Exact match on Noon: {summary['exact_match_count']} ({summary['exact_match_pct']}%)")
        print(f"  ~ Similar available: {summary['similar_available_count']} ({summary['similar_available_pct']}%)")
        print(f"  ✗ Not available: {summary['not_available_count']} ({summary['not_available_pct']}%)")

    return comparisons


def phase_3_export_excel(unified_products: dict, raw_products: list,
                         comparisons: dict = None):
    """Phase 3: Generate Excel file."""
    print_section("PHASE 3: EXCEL EXPORT")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Convert unified dict to list
    products_list = list(unified_products.values())

    # Generate Excel
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    excel_path = f'{OUTPUT_DIR}/saudi_laptop_prices_{timestamp}.xlsx'

    print(f"📝 Generating Excel file: {os.path.basename(excel_path)}")
    ExcelExporter.merge_data_and_export(products_list, raw_products, excel_path, comparisons)

    return excel_path


def phase_4_dashboard():
    """Phase 4: Setup web dashboard (placeholder)."""
    print_section("PHASE 4: WEB DASHBOARD")
    print("⏳ Dashboard setup (next step after Excel validation)")
    print("   Options:")
    print("   • Streamlit (lightweight, fast)")
    print("   • React + FastAPI (full-stack)")
    print("   • Flask + Vue.js (lightweight)")


def run_refresh(max_per_platform: int = 200):
    """Cheap weekly refresh mode: revisit stored product links instead
    of re-running a full search-based scrape. Only updates products that
    already have a link from a previous full scrape (`python3 main.py`)
    - it cannot discover brand-new products on its own, since it never
    searches, only revisits known URLs. Run a full scrape periodically
    alongside this to pick up new SKUs.

    Only refreshes Jarir and Extra by default - see
    LinkRefresher.DEFAULT_SAFE_PLATFORMS for why Noon/Amazon aren't
    trusted for this yet (their product-detail-page price extraction
    isn't verified, and a false negative here would silently null out
    good data)."""
    print("\n" + "="*70)
    print("  🔄 LINK-BASED REFRESH (Jarir + Extra)")
    print("="*70)

    merged_file = f'{DATA_DIR}/merged_products.json'
    if not os.path.exists(merged_file):
        print(f"❌ {merged_file} not found - run a full scrape first (`python3 main.py`).")
        sys.exit(1)

    with open(merged_file, 'r', encoding='utf-8') as f:
        products = json.load(f)

    print(f"📊 Loaded {len(products)} products from previous scrape")

    refresher = LinkRefresher()
    result = refresher.refresh_catalog(products, max_per_platform=max_per_platform)

    with open(merged_file, 'w', encoding='utf-8') as f:
        json.dump(result['products'], f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 Updated merged data saved: {merged_file}")

    print_section("✅ REFRESH COMPLETE")
    for platform, stats in result['stats'].items():
        print(f"  {platform}: checked={stats['checked']} updated={stats['updated']} "
              f"dead={stats['dead']} errors={stats['errors']}")

    # Regenerate Excel using the refreshed prices. Gap analysis isn't
    # recomputed here (it needs the raw per-platform product lists,
    # which aren't kept around after a run) - re-uses whatever gap
    # analysis is already on disk from the last full scrape as a known
    # simplification; run a full scrape to refresh the gap analysis itself.
    gap_file = f'{DATA_DIR}/gap_analyses.json'
    comparisons = None
    if os.path.exists(gap_file):
        with open(gap_file, 'r', encoding='utf-8') as f:
            comparisons = json.load(f)

    raw_file = f'{DATA_DIR}/raw_products.json'
    raw_products = []
    if os.path.exists(raw_file):
        with open(raw_file, 'r', encoding='utf-8') as f:
            raw_products = json.load(f)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    excel_path = f'{OUTPUT_DIR}/saudi_laptop_prices_{timestamp}.xlsx'
    ExcelExporter.merge_data_and_export(result['products'], raw_products, excel_path, comparisons)
    print(f"📄 Excel regenerated: {os.path.basename(excel_path)}")


def main():
    """Main orchestration."""
    print("\n" + "="*70)
    print("  🌏 SAUDI LAPTOP PRICE COMPARISON SYSTEM")
    print("  Amazon.sa | Jarir.com | Extra.com | Noon.com")
    print("="*70)

    log_path = f'{DATA_DIR}/run_log.jsonl'
    platform_counts, platform_health = {}, {}

    try:
        # Phase 1: Scrape (raises PlatformScrapeFailure if any platform's
        # primary + fallback both produced ~zero products)
        raw_products, platform_counts, platform_health = phase_1_scrape()

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
        unified_list = list(unified_products.values())

        # Save merged products
        merged_file = f'{DATA_DIR}/merged_products.json'
        with open(merged_file, 'w', encoding='utf-8') as f:
            json.dump(unified_list, f, ensure_ascii=False, indent=2, default=str)
        print(f"💾 Merged data saved: {merged_file}")

        # Phase 2b: Cross-platform gap analysis (universe + 3 per-platform vs Noon)
        comparisons = phase_2b_gap_analysis(unified_products, raw_products)

        gap_file = f'{DATA_DIR}/gap_analyses.json'
        with open(gap_file, 'w', encoding='utf-8') as f:
            json.dump(comparisons, f, ensure_ascii=False, indent=2, default=str)
        print(f"💾 Gap analyses saved: {gap_file}")

        # Phase 3: Export Excel
        excel_path = phase_3_export_excel(unified_products, raw_products, comparisons)

        # Phase 4: Dashboard
        phase_4_dashboard()

        # Structured run log (append-only history, separate from the
        # data/*.json snapshots which get overwritten each run)
        field_coverage = compute_field_coverage(
            unified_list, ['title', 'category', 'brand', 'model_name', 'processor', 'ram', 'storage', 'graphics_card']
        )
        merge_stats = compute_merge_stats(unified_list, raw_products)
        log_run(log_path, platform_counts, platform_health, field_coverage, merge_stats,
               comparisons.get('universe', {}).get('summary'), status='success')

        # Summary
        print_section("✅ PIPELINE COMPLETE")
        print(f"📊 Total Products: {len(unified_products)}")
        print(f"📁 Output: {OUTPUT_DIR}/")
        print(f"📄 Excel: {os.path.basename(excel_path)}")
        print(f"📊 Raw Data: {raw_file}")
        print(f"📊 Merged Data: {merged_file}")
        print(f"📊 Gap Analyses: {gap_file}")
        print(f"📊 Field coverage: {field_coverage}")
        print(f"📊 Merge stats: {merge_stats}")

    except PlatformScrapeFailure as e:
        print(f"\n🛑 PIPELINE HALTED (platform health check failed): {e}")
        log_run(log_path, platform_counts, platform_health, {}, {}, status='failed', error=str(e))
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        log_run(log_path, platform_counts, platform_health, {}, {}, status='failed', error=str(e))
        sys.exit(1)


if __name__ == '__main__':
    if '--refresh' in sys.argv:
        run_refresh()
    else:
        main()
