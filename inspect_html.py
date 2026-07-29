#!/usr/bin/env python3
"""Inspect HTML structure to find correct CSS selectors"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/src')

from config.config import FIRECRAWL_API_KEY
from utils.firecrawl_helper import FirecrawlHelper
from bs4 import BeautifulSoup

# Get HTML from Jarir
firecrawl = FirecrawlHelper(FIRECRAWL_API_KEY)
html = firecrawl.scrape_page('https://www.jarir.com/sa-en/computers-laptops/laptops')

if html:
    # Save raw HTML for inspection
    with open('jarir_raw.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✓ Saved raw HTML: jarir_raw.html ({len(html)} chars)")

    # Parse and inspect
    soup = BeautifulSoup(html, 'html.parser')

    print("\n=== STRUCTURE ANALYSIS ===\n")

    # Find all divs
    divs = soup.find_all('div', limit=20)
    print(f"Total divs: {len(soup.find_all('div'))}")

    # Look for common patterns
    print("\nSearching for patterns...")

    patterns = [
        ('class containing "product"', soup.select('[class*="product"]')),
        ('class containing "item"', soup.select('[class*="item"]')),
        ('class containing "card"', soup.select('[class*="card"]')),
        ('li elements', soup.find_all('li', limit=10)),
        ('article elements', soup.find_all('article', limit=10)),
        ('a with href', soup.find_all('a', href=True, limit=10)),
    ]

    for pattern_name, elements in patterns:
        if elements:
            print(f"\n✓ Found {len(elements)} elements matching: {pattern_name}")
            if len(elements) > 0:
                elem = elements[0]
                print(f"  Example: {elem.name}")
                if hasattr(elem, 'attrs'):
                    print(f"  Attrs: {elem.attrs}")
                    text = elem.get_text(strip=True)[:100]
                    print(f"  Text: {text}...")

    # Look for price patterns
    print("\n=== PRICE PATTERNS ===\n")
    price_patterns = [
        ('Contains "ر.س"', [e for e in soup.find_all(string=True) if 'ر.س' in str(e) or 'SAR' in str(e)]),
        ('Contains digits "000-999"', [e for e in soup.find_all(string=True) if any(c.isdigit() for c in str(e))]),
    ]

    for pattern_name, elements in price_patterns:
        if elements:
            print(f"✓ {pattern_name}: {len(elements)} matches")
            for e in elements[:3]:
                text = str(e).strip()[:100]
                print(f"  - {text}")

    # Show page title
    title = soup.find('title')
    if title:
        print(f"\n📄 Page Title: {title.get_text()}")

    # Check if page is dynamic
    scripts = soup.find_all('script')
    print(f"\n📝 Scripts: {len(scripts)}")

    if len(html) < 1000:
        print("⚠️  HTML is very small - content might be loaded dynamically")
        print("\nHTML Content:")
        print(html)

else:
    print("❌ Failed to get HTML")
