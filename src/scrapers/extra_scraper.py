"""
Extra.com (Saudi) Laptop & Desktop Scraper

Unlike Noon, Extra.com doesn't block plain HTTP requests or bot-detect
headless browsers - the category pages load fine, they just render the
product grid client-side after a delay (a `qacProdctResponseData` window
global holds it briefly, but wasn't reliably readable across requests in
testing). Firecrawl with a longer wait_for (6s) reliably captures the
fully-hydrated grid in markdown, which is parsed with the same
block-around-product-URL regex technique used for Jarir/Amazon.

Pagination is straightforward query params: ?pg=N&pageSize=100.
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


CATEGORY_URLS = {
    'Laptop': 'https://www.extra.com/en-sa/computer/laptops/c/3-303/facet/?q=%3Arelevance%3Atype%3APRODUCT&text=',
    'Desktop': 'https://www.extra.com/en-sa/computer/desktop/c/3-302/facet/?q=%3Arelevance%3Atype%3APRODUCT&text=',
}

ACCESSORY_TERMS = [
    'bag', 'sleeve', 'case', 'cover', 'skin', 'stand', 'cooling pad',
    'charger', 'adapter', 'mouse', 'keyboard', 'headset', 'backpack',
    'cleaning kit', 'screen protector', 'dock', 'hub', 'cable',
]


class ExtraScraper:
    def __init__(self):
        if not FirecrawlApp:
            raise ImportError("firecrawl package not installed. Run: python3 -m pip install firecrawl-py")
        self.client = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        self.platform_name = 'Extra'
        self.platform_key = 'extra'
        self.products = []

    def normalize_price(self, value) -> Optional[float]:
        if value is None or value == '':
            return None
        try:
            return float(str(value).replace(',', '').strip())
        except (ValueError, TypeError):
            return None

    def _looks_like_accessory(self, title: str) -> bool:
        title_lower = title.lower()
        return any(term in title_lower for term in ACCESSORY_TERMS)

    def _clean_title(self, raw_line: str) -> Optional[str]:
        """Extra's markdown repeats the brand name with no separator at
        the start of the title line, e.g. "HPHP Laptop Clamshell..." or
        "LENOVOLENOVO Yoga 7...". Detect and de-duplicate it."""
        line = raw_line.strip()
        dup_match = re.match(r'^([A-Z]{2,})\1(.*)$', line)
        if dup_match:
            return f"{dup_match.group(1)}{dup_match.group(2)}".strip()
        return line if line else None

    def _fetch_page(self, category: str, page: int, page_size: int = 96) -> Optional[str]:
        base_url = CATEGORY_URLS[category]
        url = f"{base_url}&pg={page}&pageSize={page_size}&sort=relevance"
        try:
            result = self.client.scrape(url, formats=['markdown'], wait_for=6000)
            return result.markdown if hasattr(result, 'markdown') else result.get('markdown')
        except Exception as e:
            print(f"[Extra] Error fetching {category} page {page}: {e}")
            return None

    def _parse_products_from_markdown(self, markdown: str, category: str) -> List[Dict[str, Any]]:
        products = []

        # Each product card starts with a "[![noname](...)" image link.
        # Splitting on the card-start marker gives one clean, non-
        # overlapping block per product - a backward-lookback-from-URL
        # approach bled adjacent products' prices/titles into each other
        # when cards were tightly packed.
        #
        # The closing "](product_url)" is NOT consistently preceded by
        # "dummy]" - that placeholder text only appears on cards missing
        # certain optional elements (rating badge, etc). Roughly half of
        # real cards close with something else instead (e.g. "...% Off"
        # directly followed by the link) - matching only "dummy](" was
        # silently dropping ~half of all real products (confirmed: 82
        # product URLs actually present on a page, only 36 matched
        # "dummy]", the rest closed differently). Match the LAST
        # "](extra_product_url)" in the block instead, regardless of
        # what precedes it.
        blocks = re.split(r'\[!\[noname\]', markdown)

        for block in blocks:
            url_matches = re.findall(r'\]\((https://www\.extra\.com/en-sa/computer/[^)\s]+/p/\d+)\)', block)
            if not url_matches:
                continue
            url = url_matches[-1]

            # Title: first substantial text line in the block that isn't
            # markup, a URL, or noise (ratings/stock/countdown text)
            lines = [l.strip() for l in block.split('\\') if l.strip()]
            title = None
            for line in lines:
                if line.startswith('[') or line.startswith('(') or 'http' in line or 'dummy]' in line:
                    continue
                cleaned = self._clean_title(line)
                if cleaned and len(cleaned) > 15 and re.search(r'[A-Za-z]{3,}', cleaned) \
                   and 'SAR' not in cleaned and '% Off' not in cleaned \
                   and not re.match(r'^[\d:.\s()]+$', cleaned) \
                   and cleaned.lower() not in ('out of stock', 'selling out fast'):
                    title = cleaned
                    break

            if not title or self._looks_like_accessory(title):
                continue

            price_match = re.search(r'SAR\*\*([\d,]+)\*\*', block)
            price = self.normalize_price(price_match.group(1)) if price_match else None
            if price is None:
                continue

            original_price = None
            save_match = re.search(r'(\d[\d,]*)\s*\*\*Save SAR', block)
            if save_match:
                original_price = self.normalize_price(save_match.group(1))

            availability = 'Out of Stock' if 'Out Of Stock' in block else 'In Stock'

            rating_match = re.search(r'\n(\d\.\d)\n', block)
            rating = float(rating_match.group(1)) if rating_match else None

            subtype = 'Standard'
            title_lower = title.lower()
            if 'gaming' in title_lower:
                subtype = 'Gaming'
            elif 'convertible' in title_lower or '2 in 1' in title_lower or '2-in-1' in title_lower:
                subtype = '2-in-1 / Convertible'

            products.append({
                'source_platform': self.platform_name,
                'category': category,
                'subtype': subtype,
                'product_url': url,
                'raw_title': title,
                'title': title,
                'price': price,
                'original_price': original_price,
                'currency': 'SAR',
                'availability': availability,
                'rating': rating,
                'review_count': 0,
                'image_url': '',
                'scraped_at': TIMESTAMP,
            })

        return products

    def scrape_category(self, category: str, max_products: int = 500, max_pages: int = 10) -> List[Dict[str, Any]]:
        print(f"\n{'='*60}")
        print(f"Scraping Extra {category}")
        print(f"{'='*60}")

        collected = []
        seen_urls = set()

        for page in range(1, max_pages + 1):
            markdown = self._fetch_page(category, page)
            if not markdown:
                print(f"[Extra] Page {page}: failed to fetch, stopping")
                break

            page_products = self._parse_products_from_markdown(markdown, category)
            new_products = [p for p in page_products if p['product_url'] not in seen_urls]

            if not new_products:
                print(f"[Extra] Page {page}: no new products, stopping")
                break

            for p in new_products:
                seen_urls.add(p['product_url'])
            collected.extend(new_products)

            print(f"[Extra] Page {page}: {len(page_products)} parsed -> {len(new_products)} new (total so far: {len(collected)})")

            if len(collected) >= max_products:
                break

            time.sleep(random.uniform(1.0, 2.0))

        collected = collected[:max_products]
        self.products.extend(collected)
        print(f"✓ Extra {category}: {len(collected)} products collected")
        return collected

    def scrape_laptops(self, max_products: int = 500) -> List[Dict[str, Any]]:
        return self.scrape_category('Laptop', max_products)

    def scrape_desktops(self, max_products: int = 300) -> List[Dict[str, Any]]:
        return self.scrape_category('Desktop', max_products)

    def scrape_all(self, max_per_category: int = 300) -> List[Dict[str, Any]]:
        self.scrape_laptops(max_per_category)
        self.scrape_desktops(max_per_category)
        return self.products

    def get_products(self) -> List[Dict[str, Any]]:
        return self.products

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Ad-hoc live search for a specific product (dashboard search
        feature). Extra's category URL supports a `text=` free-text
        filter param - reuses both category URLs with the query text
        rather than a dedicated site-wide search endpoint (not
        identified in the time available)."""
        import urllib.parse
        results = []
        for category, base_url in CATEGORY_URLS.items():
            url = base_url.replace('&text=', f'&text={urllib.parse.quote(query)}')
            try:
                result = self.client.scrape(url, formats=['markdown'], wait_for=6000)
                markdown = result.markdown if hasattr(result, 'markdown') else result.get('markdown')
                if markdown:
                    results.extend(self._parse_products_from_markdown(markdown, category))
            except Exception as e:
                print(f"[Extra] Search error ({category}): {e}")
        return results[:max_results]


if __name__ == '__main__':
    scraper = ExtraScraper()
    products = scraper.scrape_all(max_per_category=50)

    print(f"\n{'='*60}")
    print(f"SUMMARY: Scraped {len(products)} products from Extra")
    print(f"{'='*60}")

    for p in products[:5]:
        print(f"\n- [{p['category']}] {p['raw_title'][:70]}")
        print(f"  Price: SAR {p['price']:,.0f}")

    if products:
        output_dir = '/Users/faisals/Documents/saudi-laptop-compare/data'
        os.makedirs(output_dir, exist_ok=True)
        with open(f'{output_dir}/extra_sample.json', 'w', encoding='utf-8') as f:
            json.dump(products[:10], f, ensure_ascii=False, indent=2, default=str)
