"""Amazon.sa Laptop & Desktop Scraper"""
import json
import re
import random
import time
from datetime import datetime
from typing import List, Dict, Any
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import FIRECRAWL_API_KEY, PLATFORMS, TIMESTAMP
from utils.firecrawl_helper import FirecrawlHelper


# Terms that mark a search hit as an accessory rather than a genuine
# laptop/desktop, even though it matched the keyword search - these
# would otherwise poison brand/spec extraction (e.g. a "USB-C Hub for
# Dell HP Lenovo Laptops" listing incorrectly tagging brand="HP").
ACCESSORY_TERMS = [
    'bag', 'sleeve', 'case', 'cover', 'skin', 'stand', 'cooling pad',
    'charger', 'adapter', 'mouse', 'keyboard', 'headset', 'backpack',
    'cleaning kit', 'screen protector', 'dock', 'hub', 'cable', 'sticker',
    'decal', 'stylus', 'webcam cover', 'privacy filter', 'lock',
]


class AmazonScraper:
    def __init__(self):
        self.firecrawl = FirecrawlHelper(FIRECRAWL_API_KEY)
        self.platform_name = 'Amazon.sa'
        self.platform_key = 'amazon_sa'
        self.products = []

    def normalize_price(self, price_str: str) -> float:
        """Convert price string to float, handling currency symbols and commas."""
        if not price_str:
            return None

        # Remove common currency symbols and whitespace
        price_str = str(price_str).replace('ر.س', '').replace('SAR', '')\
            .replace('﷼', '').replace('SR', '').strip()

        # Remove commas and spaces
        price_str = price_str.replace(',', '').replace(' ', '')

        try:
            return float(price_str)
        except ValueError:
            return None

    def _looks_like_accessory(self, title: str) -> bool:
        title_lower = title.lower()
        return any(term in title_lower for term in ACCESSORY_TERMS)

    def parse_products_from_markdown(self, markdown: str, category: str = None) -> List[Dict[str, Any]]:
        """
        Parse products from Amazon.sa markdown output.

        Amazon search results follow this pattern per product:
        1. [**Title**](url_with/dp/ASIN/ref=...)
        2. RATING_out of 5 stars_ [(REVIEW_COUNT)](...)
        3. Price, product page [SAR X,XXX.XX...](...)
        """
        products = []

        # Find unique ASINs (Amazon product IDs) - each represents one product
        asins = re.findall(r'/dp/([A-Z0-9]{10})', markdown)
        unique_asins = list(dict.fromkeys(asins))  # Preserve order, dedupe

        print(f"[Parser] Found {len(unique_asins)} unique product ASINs")

        for asin in unique_asins:
            # Find the bold title link for this ASIN: [**Title**](.../dp/ASIN/...)
            title_pattern = rf'\[\*\*([^\]]+)\*\*\]\([^)]*?/dp/{asin}[^)]*\)'
            title_match = re.search(title_pattern, markdown)

            if not title_match:
                continue

            title = title_match.group(1).strip()
            title = title.replace('\\|', '|').replace('\\', '')

            if not title or len(title) < 5:
                continue

            if self._looks_like_accessory(title):
                continue

            # Build clean product URL
            product_url = f'https://www.amazon.sa/dp/{asin}'

            # Get section after title match for rating/price context
            section_start = title_match.end()
            section = markdown[section_start:section_start + 1200]

            # Extract rating: "2.2_2.2 out of 5 stars_"
            rating_match = re.search(r'(\d\.\d)\s*(?:_\d\.\d)?\s*out of 5 stars', section)
            rating = float(rating_match.group(1)) if rating_match else None

            # Extract review count: "[(21)]"
            review_match = re.search(r'\[\((\d[\d,]*)\)\]', section)
            review_count = int(review_match.group(1).replace(',', '')) if review_match else 0

            # Extract current price: "SAR X,XXX.XX" (first occurrence = current price)
            price_match = re.search(r'SAR\s*([\d,]+\.?\d*)', section)
            price = self.normalize_price(price_match.group(1)) if price_match else None

            # Extract original price if "Was:" present
            original_price = None
            was_match = re.search(r'Was:\s*SAR\s*([\d,]+\.?\d*)', section)
            if was_match:
                original_price = self.normalize_price(was_match.group(1))

            if price is None:
                continue

            # Extract specs from title
            specs = self._extract_specs(title)

            product = {
                'source_platform': self.platform_name,
                'category': category,
                'product_url': product_url,
                'raw_title': title,
                'price': price,
                'original_price': original_price,
                'currency': 'SAR',
                'availability': 'In Stock',
                'rating': rating,
                'review_count': review_count,
                'image_url': '',
                'scraped_at': TIMESTAMP,
                **specs
            }

            products.append(product)
            print(f"  ✓ {title[:60]} - SAR {price:,.0f}" + (f" ({rating}⭐ {review_count} reviews)" if rating else ""))

        return products

    def _extract_specs(self, title: str) -> Dict[str, str]:
        """Extract a couple of coarse specs for the Raw Data sheet only.

        Deliberately NOT extracting processor/graphics_card here anymore:
        those are now owned centrally by product_matcher.py's
        extract_specs(), which splits processor into short/full forms
        and normalizes GPU to a clean product name. A raw value set here
        would be treated as "structured" data and silently shadow that
        better central extraction (see product_matcher.py
        STRUCTURED_SPEC_FIELDS docstring)."""
        specs = {}

        # Brand
        brands = ['Lenovo', 'HP', 'Dell', 'Acer', 'ASUS', 'MSI', 'Apple', 'Razer', 'Samsung', 'Sony']
        for brand in brands:
            if brand.lower() in title.lower():
                specs['brand'] = brand
                break

        # RAM
        ram_match = re.search(r'(\d+)\s*GB\s*(?:RAM|DDR)', title, re.IGNORECASE)
        if ram_match:
            specs['ram'] = f"{ram_match.group(1)}GB"

        # Storage
        storage_match = re.search(r'(\d+)\s*(GB|TB)\s*(?:SSD|HDD|NVMe)', title, re.IGNORECASE)
        if storage_match:
            specs['storage'] = f"{storage_match.group(1)}{storage_match.group(2)}"

        return specs

    def scrape_listing(self, url: str, category: str, max_products: int = 50,
                       max_pages: int = 5) -> List[Dict[str, Any]]:
        """Scrape a product listing page, following pagination (&page=N)
        until max_products is reached or a page yields no new products."""
        print(f"\n{'='*60}")
        print(f"Scraping Amazon.sa {category}: {url}")
        print(f"{'='*60}")

        category_products = []
        seen_urls = set()
        separator = '&' if '?' in url else '?'

        for page in range(1, max_pages + 1):
            page_url = url if page == 1 else f"{url}{separator}page={page}"

            markdown = self.firecrawl.extract_products_from_page(page_url)

            if not markdown:
                print(f"[Amazon] Page {page}: failed to fetch, stopping pagination")
                break

            print(f"[Amazon] Page {page}: got content ({len(markdown)} chars), parsing...")
            page_products = self.parse_products_from_markdown(markdown, category=category)

            new_products = [p for p in page_products if p['product_url'] not in seen_urls]

            if not new_products:
                print(f"[Amazon] Page {page}: no new products, stopping pagination")
                break

            for p in new_products:
                seen_urls.add(p['product_url'])
            category_products.extend(new_products)

            if len(category_products) >= max_products:
                break

            time.sleep(random.uniform(0.8, 2.0))  # jittered delay between pages

        category_products = category_products[:max_products]
        self.products.extend(category_products)
        return category_products

    def scrape_laptops(self, max_products: int = 50) -> List[Dict[str, Any]]:
        """Scrape Amazon.sa laptops listing."""
        return self.scrape_listing(
            PLATFORMS['amazon_sa']['laptop_url'],
            'Laptop',
            max_products
        )

    def scrape_desktops(self, max_products: int = 50) -> List[Dict[str, Any]]:
        """Scrape Amazon.sa desktop computers listing."""
        return self.scrape_listing(
            PLATFORMS['amazon_sa']['desktop_url'],
            'Desktop',
            max_products
        )

    def scrape_all(self, max_per_category: int = 50) -> List[Dict[str, Any]]:
        """Scrape both laptops and desktops."""
        self.scrape_laptops(max_per_category)
        self.scrape_desktops(max_per_category)
        return self.products

    def get_products(self) -> List[Dict[str, Any]]:
        """Return all scraped products."""
        return self.products

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Ad-hoc live search for a specific product (dashboard search
        feature)."""
        import urllib.parse
        url = f"https://www.amazon.sa/s?k={urllib.parse.quote(query)}&i=computers"
        markdown = self.firecrawl.extract_products_from_page(url)
        if not markdown:
            return []
        products = self.parse_products_from_markdown(markdown, category=None)
        return products[:max_results]


if __name__ == '__main__':
    scraper = AmazonScraper()
    products = scraper.scrape_all(max_per_category=10)

    print(f"\n{'='*60}")
    print(f"SUMMARY: Scraped {len(products)} products from Amazon.sa")
    print(f"{'='*60}")

    if products:
        print("\nFirst 3 Products:")
        for i, product in enumerate(products[:3], 1):
            print(f"\n{i}. {product['raw_title'][:70]}")
            print(f"   Price: SAR {product['price']:,.0f}")
            print(f"   URL: {product['product_url'][:60]}")
            if product.get('rating'):
                print(f"   Rating: {product['rating']}⭐ ({product['review_count']} reviews)")

        output_dir = '/Users/faisals/Documents/saudi-laptop-compare/data'
        os.makedirs(output_dir, exist_ok=True)
        output_file = f'{output_dir}/amazon_sample.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(products[:10], f, ensure_ascii=False, indent=2, default=str)
        print(f"\n✓ Sample data saved to {output_file}")
    else:
        print("⚠️  No products scraped from Amazon.sa")
