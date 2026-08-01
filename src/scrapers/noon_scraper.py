"""
Noon.com (Saudi) Laptop & Desktop Scraper

Noon blocks plain HTTP requests and default (non-stealth) headless
browsers at the protocol/bot-detection level. It's a TanStack Start app
that embeds its full search-result payload (window.__TSR_ROUTER__) in the
page for hydration - so instead of parsing rendered HTML, we execute a
tiny JS snippet via Firecrawl (with proxy='stealth' to get past bot
detection) that pulls that state object directly. This gives clean,
pre-structured product data (brand, RAM, storage, rating, price) with no
regex title-parsing needed, and is far more reliable than scraping
rendered markdown.

IMPORTANT: this only works with proxy='stealth'. The default/basic proxy
gets served a generic, wrong, non-Saudi fallback catalog (verified during
development: nbHits=2.8M and unrelated products vs. the correct ~1,500).
"""

import json
import re
import random
import time
from typing import List, Dict, Any, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import FIRECRAWL_API_KEY, TIMESTAMP

try:
    from firecrawl import FirecrawlApp
except ImportError:
    FirecrawlApp = None


NOON_BASE = 'https://www.noon.com/saudi-en'

# Terms that mark a search hit as an accessory rather than the genuine
# product category, even though it matched the keyword search.
ACCESSORY_TERMS = [
    'bag', 'sleeve', 'case', 'cover', 'skin', 'stand', 'cooling pad',
    'charger', 'adapter', 'mouse', 'keyboard', 'headset', 'backpack',
    'cleaning kit', 'screen protector', 'dock', 'hub', 'cable',
]

EXTRACT_JS = r'''
(() => {
  const r = window.__TSR_ROUTER__;
  if (!r) return JSON.stringify({error: 'no router'});
  const m = r.state.matches.find(m => m.loaderData && m.loaderData.catalogData && m.loaderData.catalogData.catalog);
  if (!m) return JSON.stringify({error: 'no catalog match'});
  const c = m.loaderData.catalogData.catalog;
  return JSON.stringify({
    nbHits: c.nbHits,
    nbPages: c.nbPages,
    hits: c.hits || []
  });
})()
'''


class NoonScraper:
    def __init__(self):
        if not FirecrawlApp:
            raise ImportError("firecrawl package not installed. Run: python3 -m pip install firecrawl-py")
        self.client = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        self.platform_name = 'Noon'
        self.platform_key = 'noon'
        self.products = []

    def normalize_price(self, value) -> Optional[float]:
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _looks_like_accessory(self, name: str) -> bool:
        name_lower = name.lower()
        return any(term in name_lower for term in ACCESSORY_TERMS)

    def _fetch_page(self, query: str, page: int, max_retries: int = 3) -> Optional[Dict]:
        url = f'{NOON_BASE}/search/?q={query}&page={page}'

        for attempt in range(max_retries):
            try:
                result = self.client.scrape(
                    url,
                    formats=['markdown'],
                    wait_for=4000,
                    proxy='stealth',
                    actions=[
                        {'type': 'wait', 'milliseconds': 3000},
                        {'type': 'executeJavascript', 'script': EXTRACT_JS},
                    ]
                )
                returns = result.actions.get('javascriptReturns', []) if hasattr(result, 'actions') else result.get('actions', {}).get('javascriptReturns', [])
                if not returns:
                    continue
                return json.loads(returns[0]['value'])
            except Exception as e:
                print(f"[Noon] Error fetching page {page} for '{query}' (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))

        return None

    def _map_hit_to_product(self, hit: Dict, category: str) -> Optional[Dict[str, Any]]:
        name = hit.get('name')
        if not name or self._looks_like_accessory(name):
            return None

        # The "desktop computer" search query returns some results that
        # are actually laptops (e.g. gaming laptops marketed as capable
        # "desktop replacements") - reject anything whose title says
        # laptop/notebook when we're scraping the Desktop category, since
        # trusting the query category blindly was causing cross-category
        # false merges (a laptop mislabeled Desktop could never legitimately
        # match another laptop, since the matcher guards on category).
        name_lower_check = name.lower()
        if category == 'Desktop' and ('laptop' in name_lower_check or 'notebook' in name_lower_check) \
           and 'desktop' not in name_lower_check:
            return None
        if category == 'Laptop' and 'desktop' in name_lower_check and 'laptop' not in name_lower_check:
            return None

        price = self.normalize_price(hit.get('sale_price') if hit.get('sale_price') else hit.get('price'))
        if price is None:
            return None

        original_price = None
        list_price = self.normalize_price(hit.get('price'))
        if list_price is not None and list_price > price:
            original_price = list_price

        slug = hit.get('url', '')
        sku = hit.get('sku', '')
        product_url = f'{NOON_BASE}/{slug}/p/{sku}/' if slug else ''

        specs = hit.get('plp_specifications', {}) or {}
        rating_info = hit.get('product_rating', {}) or {}

        subtype = 'Standard'
        name_lower = name.lower()
        if 'gaming' in name_lower:
            subtype = 'Gaming'
        elif '2 in 1' in name_lower or '2-in-1' in name_lower or 'convertible' in name_lower:
            subtype = '2-in-1 / Convertible'
        elif 'chromebook' in name_lower:
            subtype = 'Chromebook'

        # processor/graphics_card intentionally not extracted here -
        # plp_specifications only reliably gives RAM/storage/OS, and
        # processor/GPU are now owned centrally by product_matcher.py's
        # extract_specs() (splits processor into short/full forms,
        # normalizes GPU to a clean name) - a raw value set here would
        # be treated as "structured" and shadow that better extraction.

        product = {
            'source_platform': self.platform_name,
            'category': category,
            'subtype': subtype,
            'product_url': product_url,
            'raw_title': name,
            'title': name,
            'price': price,
            'original_price': original_price,
            'currency': 'SAR',
            'availability': 'In Stock' if hit.get('is_buyable', True) else 'Out of Stock',
            'rating': rating_info.get('value'),
            'review_count': rating_info.get('count', 0),
            'image_url': hit.get('image_url', ''),
            'scraped_at': TIMESTAMP,
            'brand': hit.get('brand'),
            'model_name': None,
            'model_number': sku,
            'ram': specs.get('RAM Size'),
            'storage': specs.get('Internal Memory'),
        }
        return product

    def scrape_category(self, query: str, category: str, max_products: int = 500,
                        max_pages: int = 12) -> List[Dict[str, Any]]:
        print(f"\n{'='*60}")
        print(f"Scraping Noon {category} (query='{query}')")
        print(f"{'='*60}")

        collected = []
        seen_urls = set()

        for page in range(1, max_pages + 1):
            result = self._fetch_page(query, page)
            if not result or result.get('error'):
                print(f"[Noon] Page {page}: {result.get('error') if result else 'no response'}, stopping")
                break

            hits = result.get('hits', [])
            if not hits:
                print(f"[Noon] Page {page}: no hits, stopping")
                break

            if page == 1:
                print(f"[Noon] Reported nbHits={result.get('nbHits')}, nbPages={result.get('nbPages')}")

            page_added = 0
            for hit in hits:
                product = self._map_hit_to_product(hit, category)
                if not product or product['product_url'] in seen_urls:
                    continue
                seen_urls.add(product['product_url'])
                collected.append(product)
                page_added += 1

            print(f"[Noon] Page {page}: {len(hits)} raw hits -> {page_added} matched (total so far: {len(collected)})")

            if len(collected) >= max_products:
                break

            nb_pages = result.get('nbPages')
            if nb_pages and page >= nb_pages:
                break

            time.sleep(random.uniform(3.5, 4.5))  # jittered delay between pages

        collected = collected[:max_products]
        self.products.extend(collected)
        print(f"✓ Noon {category}: {len(collected)} products collected")
        return collected

    def scrape_laptops(self, max_products: int = 500) -> List[Dict[str, Any]]:
        return self.scrape_category('laptop', 'Laptop', max_products)

    def scrape_desktops(self, max_products: int = 500) -> List[Dict[str, Any]]:
        return self.scrape_category('desktop computer', 'Desktop', max_products)

    def scrape_all(self, max_per_category: int = 500) -> List[Dict[str, Any]]:
        self.scrape_laptops(max_per_category)
        self.scrape_desktops(max_per_category)
        return self.products

    def get_products(self) -> List[Dict[str, Any]]:
        return self.products

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Ad-hoc live search for a specific product (dashboard search
        feature). Unfiltered by category - uses Noon's own relevance
        ranking for whatever the user typed."""
        result = self._fetch_page(query, page=1)
        if not result or result.get('error'):
            return []
        hits = result.get('hits', [])
        products = []
        for hit in hits[:max_results]:
            product = self._map_hit_to_product(hit, category=None)
            if product:
                products.append(product)
        return products


if __name__ == '__main__':
    scraper = NoonScraper()
    products = scraper.scrape_all(max_per_category=100)

    print(f"\n{'='*60}")
    print(f"SUMMARY: Scraped {len(products)} products from Noon")
    print(f"{'='*60}")

    for p in products[:5]:
        print(f"\n- [{p['category']}] {p['raw_title'][:70]}")
        print(f"  Price: SAR {p['price']:,.0f}  Brand: {p.get('brand')}  RAM: {p.get('ram')}")

    if products:
        output_dir = '/Users/faisals/Documents/saudi-laptop-compare/data'
        os.makedirs(output_dir, exist_ok=True)
        with open(f'{output_dir}/noon_sample.json', 'w', encoding='utf-8') as f:
            json.dump(products[:10], f, ensure_ascii=False, indent=2, default=str)
