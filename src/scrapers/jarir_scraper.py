"""Jarir.com Laptop & Desktop Scraper"""
import json
import re
from datetime import datetime
from typing import List, Dict, Any
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import FIRECRAWL_API_KEY, PLATFORMS, TIMESTAMP
from utils.firecrawl_helper import FirecrawlHelper


class JarirScraper:
    def __init__(self):
        self.firecrawl = FirecrawlHelper(FIRECRAWL_API_KEY)
        self.platform_name = 'Jarir'
        self.platform_key = 'jarir'
        self.products = []

    def normalize_price(self, price_str: str) -> float:
        """Convert price string to float, handling currency symbols and commas."""
        if not price_str:
            return None

        # Remove common currency symbols and whitespace
        price_str = str(price_str).replace('SR', '').replace('ر.س', '')\
            .replace('SAR', '').replace('﷼', '').strip()

        # Remove commas and spaces
        price_str = price_str.replace(',', '').replace(' ', '')

        try:
            return float(price_str)
        except ValueError:
            return None

    def parse_products_from_markdown(self, markdown: str, category: str = None) -> List[Dict[str, Any]]:
        """
        Parse products from Firecrawl's markdown output.
        Pattern: SR PRICE](actual_product_url)
        """
        products = []

        # Find all product URLs in markdown (paths with /sa-en/)
        product_urls = re.findall(
            r'https://www\.jarir\.com/sa-en/[^)]+\.html[^)\s]*',
            markdown
        )

        print(f"[Parser] Found {len(product_urls)} product URLs")

        # Process each URL
        for url in product_urls:
            # Find the section before this URL
            url_index = markdown.find(url)
            if url_index < 0:
                continue

            # Look back 1500 chars for the title and price
            section_start = max(0, url_index - 1500)
            section = markdown[section_start:url_index + len(url)]

            # Extract title - find the latest [![...] before the URL
            title_matches = re.findall(r'\[!\[([^\]]+)\]', section)
            title = title_matches[-1] if title_matches else None

            if not title or len(title) < 5:
                continue

            # Extract price with discount handling
            # Pattern: "SR XXXX\nSR YYYY\nSave: SR ZZZ" or just "SR XXXX"
            # The actual current price is the one NOT preceded by "Save:"

            # Look for price pattern in section: "\nSR XXXX\n" NOT followed by "Save"
            price_pattern = r'\n\s*SR\s+([\d,]+)\s*\n(?!.*Save)'
            price_match = re.search(price_pattern, section, re.DOTALL)

            if price_match:
                price = self.normalize_price(price_match.group(1))
            else:
                # Fallback: extract all prices and use the first one (usually current price)
                all_prices = re.findall(r'SR\s+([\d,]+)', section)
                if all_prices:
                    # Filter out very small prices (like discount amounts < 100)
                    valid_prices = [p for p in all_prices if self.normalize_price(p) and self.normalize_price(p) > 100]
                    price = self.normalize_price(valid_prices[0]) if valid_prices else None
                else:
                    price = None

            if price is None:
                continue

            # Extract rating from section
            rating_match = re.search(r'\n(\d\.\d)\n', section)
            rating = float(rating_match.group(1)) if rating_match else None

            # Extract specs from title
            specs = self._extract_specs(title)

            product = {
                'source_platform': self.platform_name,
                'category': category,
                'product_url': url,
                'raw_title': title,
                'price': price,
                'original_price': None,
                'currency': 'SAR',
                'availability': 'In Stock',
                'rating': rating,
                'review_count': 0,
                'image_url': '',
                'scraped_at': TIMESTAMP,
                **specs
            }

            products.append(product)
            print(f"  ✓ {title[:60]} - ₪{price:,.0f}" + (f" ({rating}⭐)" if rating else ""))

        return products

    def _extract_specs(self, title: str) -> Dict[str, str]:
        """Extract specs from product title."""
        specs = {}

        # Brand
        brands = ['Lenovo', 'HP', 'Dell', 'Acer', 'ASUS', 'MSI', 'Apple', 'Razer']
        for brand in brands:
            if brand.lower() in title.lower():
                specs['brand'] = brand
                break

        # Processor
        processor_match = re.search(
            r'(Intel Core [i3579]-\d+|AMD Ryzen \d+|Apple M\d|Intel Core Ultra)',
            title,
            re.IGNORECASE
        )
        if processor_match:
            specs['processor'] = processor_match.group(0)

        # RAM
        ram_match = re.search(r'(\d+)\s*GB\s*RAM', title, re.IGNORECASE)
        if ram_match:
            specs['ram'] = f"{ram_match.group(1)}GB"

        # Storage
        storage_match = re.search(r'(\d+)\s*(GB|TB)\s*(?:SSD|HDD|NVMe)', title, re.IGNORECASE)
        if storage_match:
            specs['storage'] = f"{storage_match.group(1)}{storage_match.group(2)}"

        # GPU
        gpu_match = re.search(
            r'(NVIDIA|AMD|Intel)\s*(?:GeForce|Radeon)?\s*[\w\d\s]+(?:Graphics|GPU)',
            title,
            re.IGNORECASE
        )
        if gpu_match:
            specs['graphics_card'] = gpu_match.group(0).strip()

        return specs

    def scrape_listing(self, url: str, category: str, max_products: int = 50,
                       max_pages: int = 5) -> List[Dict[str, Any]]:
        """Scrape a product listing page, following pagination (?p=N) until
        max_products is reached, a page returns no new products, or
        max_pages is hit."""
        print(f"\n{'='*60}")
        print(f"Scraping Jarir {category}: {url}")
        print(f"{'='*60}")

        category_products = []
        seen_urls = set()

        for page in range(1, max_pages + 1):
            page_url = url if page == 1 else f"{url}?p={page}"

            markdown = self.firecrawl.extract_products_from_page(page_url)

            if not markdown or len(markdown) < 200:
                print(f"[Jarir] Page {page}: empty/too short response, stopping pagination")
                break

            print(f"[Jarir] Page {page}: got content ({len(markdown)} chars), parsing...")
            page_products = self.parse_products_from_markdown(markdown, category=category)

            new_products = [p for p in page_products if p['product_url'] not in seen_urls]

            if not new_products:
                print(f"[Jarir] Page {page}: no new products, stopping pagination")
                break

            for p in new_products:
                seen_urls.add(p['product_url'])
            category_products.extend(new_products)

            if len(category_products) >= max_products:
                break

        category_products = category_products[:max_products]
        self.products.extend(category_products)
        return category_products

    def scrape_laptops(self, max_products: int = 50) -> List[Dict[str, Any]]:
        """Scrape Jarir laptops listing."""
        return self.scrape_listing(
            PLATFORMS['jarir']['laptop_url'],
            'Laptop',
            max_products
        )

    def scrape_desktops(self, max_products: int = 50) -> List[Dict[str, Any]]:
        """Scrape Jarir desktop computers listing."""
        return self.scrape_listing(
            PLATFORMS['jarir']['desktop_url'],
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


if __name__ == '__main__':
    scraper = JarirScraper()

    # Scrape with smaller batch for testing
    products = scraper.scrape_all(max_per_category=10)

    print(f"\n{'='*60}")
    print(f"SUMMARY: Scraped {len(products)} products from Jarir")
    print(f"{'='*60}")

    # Display first 5 products
    if products:
        print("\nFirst 5 Products (Structured Data):")
        for i, product in enumerate(products[:5], 1):
            print(f"\n{i}. {product['raw_title'][:70]}")
            print(f"   Price: ₪{product['price']:,.0f}")
            print(f"   URL: {product['product_url'][:60]}")
            if product.get('rating'):
                print(f"   Rating: {product['rating']} ⭐")
            if product.get('processor'):
                print(f"   Processor: {product['processor']}")
            if product.get('ram'):
                print(f"   RAM: {product['ram']}")

        # Save to JSON for inspection
        output_dir = '/Users/faisals/Documents/saudi-laptop-compare/data'
        os.makedirs(output_dir, exist_ok=True)

        output_file = f'{output_dir}/jarir_sample.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(products[:10], f, ensure_ascii=False, indent=2, default=str)
        print(f"\n✓ Sample data saved to {output_file}")
    else:
        print("⚠️  No products scraped. Check markdown parsing.")
