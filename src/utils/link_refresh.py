"""
Link-based catalog refresh.

The initial scrape (main.py, search/category-based) is the expensive
one-time exercise: discovering product URLs across all four platforms.
Once those links exist in merged_products.json, routine (e.g. weekly)
updates don't need to re-search from scratch - they just need to
revisit each stored URL, pull the current price/availability, and
discard links that no longer resolve. This is cheaper, faster, and
doesn't fight each platform's bot-detection/rate-limits the way a full
re-search does every time.

This module only handles the "revisit" half. Discovering brand-new
products that weren't in a previous scrape still requires periodically
re-running main.py's full search-based scrape - this module can't find
products it doesn't already have a link for.
"""

import re
import sys
import os
import time
import random
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import FIRECRAWL_API_KEY

try:
    import requests
except ImportError:
    requests = None

try:
    from firecrawl import FirecrawlApp
except ImportError:
    FirecrawlApp = None


# Product-detail pages embed the current price as structured JSON
# rather than (or in addition to) visible text - these patterns are
# unique to the product actually being viewed (unlike generic "SAR
# 1,234" text matches, which also hit unrelated content like BNPL/
# financing boilerplate or "related products" price tags elsewhere on
# the page - confirmed by testing against real pages during development,
# where a naive text-only regex matched installment-plan minimum-
# purchase amounts before ever reaching the real price).
JSON_PRICE_PATTERNS = {
    'jarir': [r'"jarir_final_price":([\d.]+)', r'"final_price":([\d.]+)'],
    'extra': [r'"price":\{"currencyIso":"SAR","value":([\d.]+)'],
}

# Generic text fallback, used only if a platform has no JSON pattern
# match (or for platforms without a known JSON field yet) - scans a much
# larger window than a single page's opening paragraph, since the real
# price can be deep in a multi-hundred-KB page.
TEXT_PRICE_PATTERNS = [
    r'SAR\s*([\d,]+\.?\d*)',
    r'SR\s{1,3}([\d,]+\.?\d*)',
    r'﷼\s*([\d,]+\.?\d*)',
]

OUT_OF_STOCK_PATTERNS = [
    r'\bout of stock\b', r'\bunavailable\b', r'\bsold out\b',
    r'\bcurrently unavailable\b', r'\bnot available\b',
]

IN_STOCK_JSON_PATTERNS = [
    r'"stockLevelStatus":\{"code":"inStock"',
]
OUT_OF_STOCK_JSON_PATTERNS = [
    r'"stockLevelStatus":\{"code":"outOfStock"',
]

PLATFORM_FIELD_MAP = {
    'jarir': ('jarir_price', 'jarir_link', 'jarir_availability'),
    'amazon_sa': ('amazon_sa_price', 'amazon_sa_link', 'amazon_sa_availability'),
    'extra': ('extra_price', 'extra_link', 'extra_availability'),
    'noon': ('noon_price', 'noon_link', 'noon_availability'),
}
PLATFORM_DISPLAY = {'jarir': 'Jarir', 'amazon_sa': 'Amazon.sa', 'extra': 'Extra', 'noon': 'Noon'}


class LinkRefresher:
    def __init__(self):
        self.session = None
        if requests:
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
        self._firecrawl = None

    def _get_firecrawl(self):
        if self._firecrawl is None and FirecrawlApp:
            self._firecrawl = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        return self._firecrawl

    def _extract_price(self, text: str, platform_key: str = None) -> Optional[float]:
        """Prefer the platform's known JSON price field (precise, unique
        to the product being viewed) over generic visible-text scanning
        (which can match unrelated boilerplate - BNPL/financing minimums,
        related-product prices - before reaching the real price)."""
        if platform_key and platform_key in JSON_PRICE_PATTERNS:
            for pattern in JSON_PRICE_PATTERNS[platform_key]:
                match = re.search(pattern, text)
                if match:
                    try:
                        val = float(match.group(1))
                        if 50 < val < 100000:
                            return val
                    except ValueError:
                        continue

        # Fallback: generic text scan over a much larger window than a
        # single "page opening" - the real price can be deep in the page
        for pattern in TEXT_PRICE_PATTERNS:
            matches = re.findall(pattern, text[:60000])
            for m in matches:
                try:
                    val = float(m.replace(',', ''))
                    if 50 < val < 100000:
                        return val
                except ValueError:
                    continue
        return None

    def _is_out_of_stock(self, text: str, platform_key: str = None) -> bool:
        if any(re.search(p, text) for p in OUT_OF_STOCK_JSON_PATTERNS):
            return True
        if any(re.search(p, text) for p in IN_STOCK_JSON_PATTERNS):
            return False
        text_lower = text[:20000].lower()
        return any(re.search(p, text_lower) for p in OUT_OF_STOCK_PATTERNS)

    def refresh_via_requests(self, url: str, platform_key: str = None) -> Dict:
        """For platforms that don't block plain HTTP (Jarir, Extra)."""
        if not self.session:
            return {'status': 'error', 'error': 'requests not installed'}
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 404:
                return {'status': 'dead_link'}
            resp.raise_for_status()
            price = self._extract_price(resp.text, platform_key)
            if price is None:
                return {'status': 'dead_link'}
            return {
                'status': 'ok',
                'price': price,
                'availability': 'Out of Stock' if self._is_out_of_stock(resp.text, platform_key) else 'In Stock',
            }
        except Exception as e:
            err = str(e)
            if '404' in err:
                return {'status': 'dead_link'}
            return {'status': 'error', 'error': err}

    def refresh_via_firecrawl(self, url: str, platform_key: str = None,
                              stealth: bool = False, wait_for: int = 4000) -> Dict:
        """For platforms that need real JS rendering (Amazon, Noon which
        additionally needs the stealth proxy)."""
        fc = self._get_firecrawl()
        if not fc:
            return {'status': 'error', 'error': 'firecrawl not installed'}
        try:
            kwargs = {'formats': ['markdown'], 'wait_for': wait_for}
            if stealth:
                kwargs['proxy'] = 'stealth'
            result = fc.scrape(url, **kwargs)
            text = result.markdown if hasattr(result, 'markdown') else result.get('markdown', '')
            if not text:
                return {'status': 'dead_link'}
            price = self._extract_price(text, platform_key)
            if price is None:
                return {'status': 'dead_link'}
            return {
                'status': 'ok',
                'price': price,
                'availability': 'Out of Stock' if self._is_out_of_stock(text, platform_key) else 'In Stock',
            }
        except Exception as e:
            err = str(e)
            if '404' in err or 'not found' in err.lower():
                return {'status': 'dead_link'}
            return {'status': 'error', 'error': err}

    def refresh_link(self, platform_key: str, url: str) -> Dict:
        """Dispatch to the right refresh method for a platform."""
        if not url:
            return {'status': 'no_link'}
        if platform_key == 'jarir':
            return self.refresh_via_requests(url, platform_key)
        if platform_key == 'extra':
            return self.refresh_via_requests(url, platform_key)
        if platform_key == 'noon':
            return self.refresh_via_firecrawl(url, platform_key, stealth=True)
        if platform_key == 'amazon_sa':
            return self.refresh_via_firecrawl(url, platform_key, stealth=False)
        return {'status': 'error', 'error': f'Unknown platform: {platform_key}'}

    # Platforms confirmed safe for refresh, verified against real stored
    # links during development: both expose a precise JSON price field
    # on their product-detail pages (Jarir: "jarir_final_price"/
    # "final_price"; Extra: nested "price":{"value":...}), tested
    # against real products including catching a genuine Extra price
    # change and an Extra out-of-stock flag correctly.
    #
    # Noon and Amazon are deliberately excluded from the default.
    # Noon's LISTING pages expose price via window.__TSR_ROUTER__ state
    # (see noon_scraper.py), but its PRODUCT DETAIL pages don't carry
    # the same data in an easily-found spot - two rounds of diagnostics
    # against a real product page found no usable price field, either in
    # visible text or in the router state's loaderData. Amazon returned
    # a price on one manual test but paired with a suspicious out-of-
    # stock flag and a large price jump that wasn't independently
    # verified. Shipping either as "trusted" risks a refresh run
    # silently marking good products dead_link (nulling their price and
    # link) on a false negative - worse than not refreshing them at all.
    # Re-enable by passing platforms=['jarir','extra','noon','amazon_sa']
    # once Noon/Amazon extraction is verified the same way Jarir/Extra were.
    DEFAULT_SAFE_PLATFORMS = ['jarir', 'extra']

    def refresh_catalog(self, merged_products: List[Dict], platforms: List[str] = None,
                        max_per_platform: int = None, delay_range=(0.5, 1.5)) -> Dict:
        """
        Revisit every stored link across the merged catalog, update
        price/availability in place, and null out dead links (caller
        decides whether to drop those products entirely or just note
        the platform is no longer available for them).

        Defaults to DEFAULT_SAFE_PLATFORMS (Jarir + Extra) unless the
        caller explicitly opts into Noon/Amazon - see that constant's
        docstring for why they're not trusted by default yet.

        Returns {'products': updated list, 'stats': per-platform counts}.
        """
        platforms = platforms or self.DEFAULT_SAFE_PLATFORMS
        stats = {p: {'checked': 0, 'updated': 0, 'dead': 0, 'errors': 0} for p in platforms}
        now = datetime.now().isoformat()

        for platform_key in platforms:
            price_field, link_field, avail_field = PLATFORM_FIELD_MAP[platform_key]
            checked_this_platform = 0

            for product in merged_products:
                url = product.get(link_field)
                if not url:
                    continue
                if max_per_platform and checked_this_platform >= max_per_platform:
                    break

                result = self.refresh_link(platform_key, url)
                stats[platform_key]['checked'] += 1
                checked_this_platform += 1

                if result['status'] == 'ok':
                    product[price_field] = result['price']
                    product[avail_field] = result.get('availability', 'In Stock')
                    product['last_refreshed'] = now
                    stats[platform_key]['updated'] += 1
                elif result['status'] == 'dead_link':
                    product[price_field] = None
                    product[link_field] = None
                    product[avail_field] = 'Not Listed'
                    stats[platform_key]['dead'] += 1
                else:
                    stats[platform_key]['errors'] += 1
                    print(f"[LinkRefresh] {PLATFORM_DISPLAY[platform_key]} error on {url}: {result.get('error')}")

                time.sleep(random.uniform(*delay_range))

        # Recompute best_price / best_price_platform after updates
        for product in merged_products:
            prices = {
                platform_key: product.get(PLATFORM_FIELD_MAP[platform_key][0])
                for platform_key in PLATFORM_FIELD_MAP
                if product.get(PLATFORM_FIELD_MAP[platform_key][0]) is not None
            }
            if prices:
                best_platform = min(prices, key=prices.get)
                product['best_price'] = prices[best_platform]
                product['best_price_platform'] = PLATFORM_DISPLAY[best_platform]
            else:
                product['best_price'] = None
                product['best_price_platform'] = None

        return {'products': merged_products, 'stats': stats}
