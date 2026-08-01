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


def search_local(
    query: str,
    products: List[Dict[str, Any]],
    max_results: int = 30,
    brand: str = None,
    ram: str = None,
    storage: str = None,
    processor: str = None,
) -> List[Dict[str, Any]]:
    """Search the already-scraped, merged product catalog.

    Requires ALL free-text query terms to match (AND, not OR) - a query
    like "Apple M5 Max 48GB" previously matched anything sharing even
    one term (e.g. a Lenovo with "Max" in its title, or unrelated 48GB
    storage), because it scored by match COUNT rather than requiring
    every term. Since brand is almost always one of the query terms,
    AND-matching also fixes cross-brand bleed without any special-casing.

    The brand/ram/storage/processor params are exact-ish dropdown
    filters (from the dashboard UI) applied before the free-text match,
    for users who want a strict brand + spec combination rather than
    typing it all as free text.
    """
    searchable_fields = ['title', 'brand', 'model_name', 'model_number', 'processor']

    def haystack_of(product: Dict[str, Any]) -> str:
        return ' '.join(str(product.get(f, '')) for f in searchable_fields).lower()

    candidates = products

    if brand and brand != 'All':
        candidates = [p for p in candidates if str(p.get('brand', '')).lower() == brand.lower()]
    if ram and ram != 'All':
        candidates = [p for p in candidates if str(p.get('ram', '')).lower() == ram.lower()]
    if storage and storage != 'All':
        candidates = [p for p in candidates if str(p.get('storage', '')).lower() == storage.lower()]
    if processor and processor != 'All':
        candidates = [p for p in candidates if processor.lower() in str(p.get('processor', '')).lower()]

    query_lower = query.lower().strip()
    if not query_lower:
        return candidates[:max_results]

    terms = query_lower.split()

    scored = []
    for product in candidates:
        haystack = haystack_of(product)
        matched_terms = sum(1 for term in terms if term in haystack)
        if matched_terms == len(terms):
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
