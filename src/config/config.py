"""Configuration for the Saudi Laptop Price Comparison System"""
import os
from datetime import datetime

# API Configuration
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY', '')

# Platform URLs
PLATFORMS = {
    'jarir': {
        'name': 'Jarir.com',
        'laptop_url': 'https://www.jarir.com/sa-en/computers-laptops/laptops',
        'desktop_url': 'https://www.jarir.com/sa-en/computers-laptops/desktop-computers',
    },
    'amazon_sa': {
        'name': 'Amazon.sa',
        'laptop_url': 'https://www.amazon.sa/s?k=laptops&i=computers',
        'desktop_url': 'https://www.amazon.sa/s?k=desktop+computers&i=computers',
        # Supplementary query - the generic "desktop computers" search is
        # dominated by mainstream Dell/HP/mini-PC listings, so boutique
        # system-integrator gaming-PC brands (Infiniarc, CyberPowerPC,
        # TechTroniX, ...) never rank within our page-limited scrape of
        # it. "gaming desktop" ranks these much higher, surfacing brands
        # the generic query structurally misses.
        'gaming_desktop_url': 'https://www.amazon.sa/s?k=gaming+desktop&i=computers',
    },
    'extra': {
        'name': 'Extra.com',
        'laptop_url': 'https://www.extra.com/en/computers-&-accessories/laptops',
        'desktop_url': 'https://www.extra.com/en/computers-&-accessories/desktop-computers',
    },
    'noon': {
        'name': 'Noon.com',
        'laptop_url': 'https://www.noon.com/sa-en/computers-and-accessories/laptops',
        'desktop_url': 'https://www.noon.com/sa-en/computers-and-accessories/desktop-computers',
    }
}

# Output paths
DATA_DIR = '/Users/faisals/Documents/saudi-laptop-compare/data'
OUTPUT_DIR = '/Users/faisals/Documents/saudi-laptop-compare/output'
TIMESTAMP = datetime.now().isoformat()

# Scraper settings
MAX_PRODUCTS_PER_PLATFORM = 100  # Start with 100 for testing
REQUEST_TIMEOUT = 30
RETRY_ATTEMPTS = 3

# Fields to extract
REQUIRED_FIELDS = [
    'source_platform',
    'product_url',
    'raw_title',
    'price',
    'original_price',
    'currency',
    'availability',
    'rating',
    'review_count',
    'image_url',
    'scraped_at'
]
