"""
Ad-hoc live product search across all platforms.

Used by the dashboard's "Search Any Product" tab: the user types a
title/model/brand/config and gets:
  1. An instant search over the already-scraped merged_products.json
     (free, no network calls)
  2. An optional live search that hits each platform's real search
     endpoint directly (Jarir's Constructor.io API, Noon's TSR-state
     extraction, Amazon/Extra via Firecrawl) - slower and consumes
     Firecrawl credits for the platforms that need it, so this is
     explicitly opt-in from the dashboard, not run automatically.
"""

import sys
import os
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def search_local(query: str, products: List[Dict[str, Any]], max_results: int = 30) -> List[Dict[str, Any]]:
    """Search the already-scraped, merged product catalog. Simple
    substring match across the fields a user would plausibly search by
    (title, brand, model name/number, processor) - fast and free."""
    query_lower = query.lower().strip()
    if not query_lower:
        return []

    terms = query_lower.split()
    searchable_fields = ['title', 'brand', 'model_name', 'model_number', 'processor']

    scored = []
    for product in products:
        haystack = ' '.join(str(product.get(f, '')) for f in searchable_fields).lower()
        matched_terms = sum(1 for term in terms if term in haystack)
        if matched_terms > 0:
            scored.append((matched_terms, product))

    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:max_results]]


def search_live(query: str, max_per_platform: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """Hit each platform's real search endpoint directly for the given
    query. Returns raw (unmerged) results per platform, since an ad-hoc
    search doesn't need cross-platform matching - showing all hits
    side by side lets the user compare directly."""
    from scrapers.jarir_scraper import JarirScraper
    from scrapers.amazon_scraper import AmazonScraper
    from scrapers.noon_scraper import NoonScraper
    from scrapers.extra_scraper import ExtraScraper

    results = {}

    for platform_name, scraper_cls in [
        ('Jarir', JarirScraper),
        ('Amazon.sa', AmazonScraper),
        ('Noon', NoonScraper),
        ('Extra', ExtraScraper),
    ]:
        try:
            scraper = scraper_cls()
            results[platform_name] = scraper.search(query, max_results=max_per_platform)
        except Exception as e:
            print(f"[LiveSearch] {platform_name} error: {e}")
            results[platform_name] = []

    return results
