"""
Jarir.com Laptop & Desktop Scraper

Uses Jarir's real backend search API (Constructor.io) directly instead of
scraping rendered HTML. Jarir's public "Laptops"/"Desktops" landing pages
are curated marketing widgets showing ~12 handpicked SKUs each - NOT the
full catalog. The real catalog (900+ laptops, 400+ desktop-category
listings) is only reachable through site search, which is backed by
Constructor.io using a public, browser-exposed search-only API key.
"""

import json
import re
import random
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import TIMESTAMP, FIRECRAWL_API_KEY, PLATFORMS

try:
    import requests
except ImportError:
    requests = None

try:
    from utils.firecrawl_helper import FirecrawlHelper
except ImportError:
    FirecrawlHelper = None


# Public Constructor.io search-only key, observed in Jarir's own storefront
# network traffic (browser-exposed by design, read-only search access).
CNSTRC_KEY = 'key_KcSYfmQTEwRpBnd9'
CNSTRC_BASE = 'https://ac.cnstrc.com/search'

# Product-type allowlists to exclude accessories/peripherals that merely
# mention "laptop"/"desktop" in their title (bags, keyboards, chargers...).
LAPTOP_PTYPES = {'Laptop', 'Gaming Laptop', '2-in-1 Laptop - Convertible'}
DESKTOP_PTYPE_SUBSTRING = 'Desktop Computer'  # covers "Desktop Computer", "Gaming Desktop Computer", etc.


class JarirScraper:
    def __init__(self):
        if requests is None:
            raise ImportError("requests not installed. Run: python3 -m pip install requests")
        self.platform_name = 'Jarir'
        self.platform_key = 'jarir'
        self.products = []
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
        self._firecrawl = None  # lazy - only needed if the API fallback triggers
        self.used_fallback = {}  # category -> bool, for health-check reporting

    def _search_page(self, query: str, page: int, per_page: int = 100) -> Optional[Dict]:
        """Call Jarir's Constructor.io-backed search API for one page of results."""
        params = {
            'c': 'ciojs-2.1447.2',
            'key': CNSTRC_KEY,
            'num_results_per_page': per_page,
            'page': page,
        }
        try:
            resp = self.session.get(f'{CNSTRC_BASE}/{query}', params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[Jarir] API error on page {page}: {e}")
            return None

    def normalize_price(self, value) -> Optional[float]:
        if value is None or value == '':
            return None
        try:
            return float(str(value).replace(',', '').strip())
        except (ValueError, TypeError):
            return None

    def _passes_type_filter(self, ptyp: str, category: str) -> bool:
        if not ptyp:
            return False
        if category == 'Laptop':
            return ptyp in LAPTOP_PTYPES
        if category == 'Desktop':
            return DESKTOP_PTYPE_SUBSTRING in ptyp
        if category is None:
            return True  # unfiltered - used for ad-hoc user search, not the catalog scrape
        return False

    def _map_result_to_product(self, hit: Dict, category: str) -> Optional[Dict[str, Any]]:
        """Convert one Constructor.io search hit into our standard product schema."""
        data = hit.get('data', {})
        meta = data.get('metadata', {})

        ptyp = meta.get('ptyp', '')
        if not self._passes_type_filter(ptyp, category):
            return None

        if category is None:
            # ad-hoc search: resolve a display category from ptyp instead
            # of trusting an input category (there isn't one)
            if 'laptop' in ptyp.lower():
                category = 'Laptop'
            elif 'desktop' in ptyp.lower():
                category = 'Desktop'
            else:
                category = ptyp or 'Other'

        title = hit.get('value') or meta.get('name')
        if not title:
            return None

        price = self.normalize_price(data.get('price'))
        if price is None:
            return None

        url_slug = data.get('url', '')
        product_url = f'https://www.jarir.com/sa-en/{url_slug}' if url_slug else ''

        # Try to pull a final/discounted price out of the embedded GTM blob if present
        original_price = None
        gtm_raw = meta.get('additionalDataToReturn')
        if gtm_raw:
            try:
                gtm = json.loads(gtm_raw)
                final_price = self.normalize_price(gtm.get('GTM_final_price'))
                if final_price is not None and final_price < price:
                    original_price = price
                    price = final_price
            except (json.JSONDecodeError, TypeError):
                pass

        product = {
            'source_platform': self.platform_name,
            'category': category,
            'subtype': 'Gaming' if 'Gaming' in ptyp else ('2-in-1 / Convertible' if '2-in-1' in ptyp else 'Standard'),
            'product_url': product_url,
            'raw_title': title,
            'title': title,
            'price': price,
            'original_price': original_price,
            'currency': 'SAR',
            'availability': 'In Stock',
            'rating': None,
            'review_count': 0,
            'image_url': data.get('image_url', ''),
            'scraped_at': TIMESTAMP,
            'brand': meta.get('brand'),
            'model_name': meta.get('seri') or meta.get('model'),
            'model_number': meta.get('moch') or data.get('sku'),
            # Jarir's own metadata already splits short tier ('prse', e.g.
            # "Intel Core i5") from the full SKU/generation descriptor
            # ('prcr', e.g. "Intel Core i5-1355U (13th Gen)") - use both
            # directly rather than re-deriving via regex.
            'processor': meta.get('prse'),
            'processor_full': meta.get('prcr') or meta.get('prse'),
            'ram': meta.get('symm'),
            'storage': meta.get('tsca'),
            # graphics_card intentionally not set here - Jarir's own
            # 'gyro'/'grpc' fields sometimes give a raw core-count
            # attribute instead of an actual GPU name (e.g. Apple
            # products show "8 Core GPU"); GPU is always derived
            # centrally from the title instead (see product_matcher.py
            # STRUCTURED_SPEC_FIELDS docstring).
        }
        return product

    def scrape_category(self, query: str, category: str, max_products: int = 1000) -> List[Dict[str, Any]]:
        """Scrape all products for a category via paginated search API calls.
        Falls back to markdown-scraping the curated category landing page
        (Firecrawl) if the API returns nothing at all - e.g. if Jarir
        rotates/revokes the Constructor.io key this integration depends
        on. The fallback only surfaces ~12 curated products (that page's
        known limitation, see module docstring), so it's a degraded-but-
        alive mode, not full parity."""
        print(f"\n{'='*60}")
        print(f"Scraping Jarir {category} (query='{query}') via search API")
        print(f"{'='*60}")

        per_page = 100
        collected = []
        seen_urls = set()
        page = 1
        total_num_results = None
        api_had_any_response = False

        while len(collected) < max_products:
            result = self._search_page(query, page, per_page)
            if not result:
                break
            api_had_any_response = True

            response = result.get('response', {})
            if total_num_results is None:
                total_num_results = response.get('total_num_results')
                print(f"[Jarir] Reported total matches for '{query}': {total_num_results}")

            hits = response.get('results', [])
            if not hits:
                print(f"[Jarir] Page {page}: no more results, stopping")
                break

            page_added = 0
            for hit in hits:
                product = self._map_result_to_product(hit, category)
                if not product or product['product_url'] in seen_urls:
                    continue
                seen_urls.add(product['product_url'])
                collected.append(product)
                page_added += 1

            print(f"[Jarir] Page {page}: {len(hits)} raw hits -> {page_added} matched {category} products (total so far: {len(collected)})")

            # Stop once we've paged past the API's reported total
            if page * per_page >= (total_num_results or 0):
                break

            page += 1
            time.sleep(random.uniform(0.3, 0.8))  # jittered, be polite

        self.used_fallback[category] = False

        if not collected:
            reason = "API unreachable" if not api_had_any_response else "API reachable but 0 genuine matches"
            print(f"[Jarir] ⚠ {category}: search API produced no results ({reason}). Falling back to markdown-scraping the category landing page.")
            collected = self._scrape_category_via_markdown_fallback(category, max_products)
            self.used_fallback[category] = True

        collected = collected[:max_products]
        self.products.extend(collected)
        print(f"✓ Jarir {category}: {len(collected)} genuine products collected"
              f"{' (via fallback)' if self.used_fallback[category] else ''}")
        return collected

    def _scrape_category_via_markdown_fallback(self, category: str, max_products: int) -> List[Dict[str, Any]]:
        """Degraded-mode fallback: scrape Jarir's curated category landing
        page via Firecrawl + regex, same technique used before the
        Constructor.io API was discovered. Only surfaces the page's ~12
        curated products, not the full catalog - but keeps the pipeline
        alive instead of returning zero Jarir data."""
        if FirecrawlHelper is None:
            print("[Jarir] Fallback unavailable: firecrawl-py not installed")
            return []

        url_key = 'laptop_url' if category == 'Laptop' else 'desktop_url'
        url = PLATFORMS['jarir'].get(url_key)
        if not url:
            return []

        if self._firecrawl is None:
            try:
                self._firecrawl = FirecrawlHelper(FIRECRAWL_API_KEY)
            except Exception as e:
                print(f"[Jarir] Fallback unavailable: {e}")
                return []

        markdown = self._firecrawl.extract_products_from_page(url)
        if not markdown:
            print(f"[Jarir] Fallback: failed to fetch {url}")
            return []

        products = []
        product_urls = re.findall(r'https://www\.jarir\.com/sa-en/[^)]+\.html[^)\s]*', markdown)

        for product_url in product_urls:
            idx = markdown.find(product_url)
            if idx < 0:
                continue
            section = markdown[max(0, idx - 1500):idx + len(product_url)]

            title_matches = re.findall(r'\[!\[([^\]]+)\]', section)
            title = title_matches[-1] if title_matches else None
            if not title or len(title) < 5:
                continue

            price_pattern = r'\n\s*SR\s+([\d,]+)\s*\n(?!.*Save)'
            price_match = re.search(price_pattern, section, re.DOTALL)
            if price_match:
                price = self.normalize_price(price_match.group(1))
            else:
                all_prices = re.findall(r'SR\s+([\d,]+)', section)
                valid_prices = [p for p in all_prices if self.normalize_price(p) and self.normalize_price(p) > 100]
                price = self.normalize_price(valid_prices[0]) if valid_prices else None

            if price is None:
                continue

            products.append({
                'source_platform': self.platform_name,
                'category': category,
                'subtype': 'Gaming' if 'gaming' in title.lower() else 'Standard',
                'product_url': product_url,
                'raw_title': title,
                'title': title,
                'price': price,
                'original_price': None,
                'currency': 'SAR',
                'availability': 'In Stock',
                'rating': None,
                'review_count': 0,
                'image_url': '',
                'scraped_at': TIMESTAMP,
                'brand': None,
                'model_name': None,
                'model_number': None,
                'processor': None,
                'ram': None,
                'storage': None,
                'graphics_card': None,
            })

            if len(products) >= max_products:
                break

        print(f"[Jarir] Fallback: {len(products)} products from curated landing page")
        return products

    def scrape_laptops(self, max_products: int = 1000) -> List[Dict[str, Any]]:
        return self.scrape_category('laptop', 'Laptop', max_products)

    def scrape_desktops(self, max_products: int = 1000) -> List[Dict[str, Any]]:
        return self.scrape_category('desktop', 'Desktop', max_products)

    def scrape_all(self, max_per_category: int = 1000) -> List[Dict[str, Any]]:
        self.scrape_laptops(max_per_category)
        self.scrape_desktops(max_per_category)
        return self.products

    def get_products(self) -> List[Dict[str, Any]]:
        return self.products

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Ad-hoc live search for a specific product (used by the
        dashboard's product search feature, not the full catalog scrape).
        Unfiltered by category/ptyp - returns whatever Jarir's search
        thinks matches the query."""
        result = self._search_page(query, page=1, per_page=max_results)
        if not result:
            return []
        hits = result.get('response', {}).get('results', [])
        products = []
        for hit in hits[:max_results]:
            product = self._map_result_to_product(hit, category=None)
            if product:
                products.append(product)
        return products


if __name__ == '__main__':
    scraper = JarirScraper()
    products = scraper.scrape_all(max_per_category=1000)

    print(f"\n{'='*60}")
    print(f"SUMMARY: Scraped {len(products)} products from Jarir")
    print(f"{'='*60}")

    if products:
        for p in products[:5]:
            print(f"\n- [{p['category']}] {p['raw_title'][:70]}")
            print(f"  Price: SAR {p['price']:,.0f}  Brand: {p.get('brand')}  CPU: {p.get('processor')}")

        output_dir = '/Users/faisals/Documents/saudi-laptop-compare/data'
        os.makedirs(output_dir, exist_ok=True)
        with open(f'{output_dir}/jarir_sample.json', 'w', encoding='utf-8') as f:
            json.dump(products[:10], f, ensure_ascii=False, indent=2, default=str)
