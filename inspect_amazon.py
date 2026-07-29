#!/usr/bin/env python3
"""Inspect Amazon.sa markdown structure"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/src')

from config.config import FIRECRAWL_API_KEY
from utils.firecrawl_helper import FirecrawlHelper

firecrawl = FirecrawlHelper(FIRECRAWL_API_KEY)
markdown = firecrawl.scrape_page('https://www.amazon.sa/s?k=laptops&i=computers')

if markdown:
    with open('amazon_raw.md', 'w', encoding='utf-8') as f:
        f.write(markdown)
    print(f"✓ Saved: amazon_raw.md ({len(markdown)} chars)")

    # Show first 3000 chars
    print("\n=== FIRST 3000 CHARS ===\n")
    print(markdown[:3000])
else:
    print("❌ Failed")
