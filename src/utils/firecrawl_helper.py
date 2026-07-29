"""Firecrawl API wrapper for web scraping"""
import json
import time
from typing import Optional, Dict, Any, List
import sys

try:
    from firecrawl import FirecrawlApp
except ImportError:
    FirecrawlApp = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


class FirecrawlHelper:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY environment variable not set")

        if not FirecrawlApp:
            raise ImportError("firecrawl package not installed. Run: python3 -m pip install firecrawl-py")

        self.client = FirecrawlApp(api_key=api_key)

    def scrape_page(self, url: str, max_retries: int = 3) -> Optional[str]:
        """
        Scrape a page using Firecrawl and return HTML/markdown.

        Args:
            url: Page URL to scrape
            max_retries: Number of retry attempts

        Returns:
            HTML/Markdown content as string
        """
        for attempt in range(max_retries):
            try:
                print(f"[Firecrawl] Scraping {url} (attempt {attempt + 1}/{max_retries})...")

                # Call scrape_url
                result = self.client.scrape_url(url)

                # Handle Document object returned by v2 API
                if result:
                    # Try to get markdown or html from result
                    content = None

                    if hasattr(result, 'markdown'):
                        content = result.markdown
                    elif hasattr(result, 'html'):
                        content = result.html
                    elif hasattr(result, 'content'):
                        content = result.content
                    elif isinstance(result, dict):
                        content = result.get('markdown') or result.get('html')
                    else:
                        # Try to convert to dict-like access
                        try:
                            content = result.get('markdown') or result.get('html')
                        except:
                            content = str(result)

                    if content:
                        print(f"[Firecrawl] ✓ Got content ({len(content)} chars)")
                        return content

                print(f"[Firecrawl] No content in response: {type(result)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

            except Exception as e:
                print(f"[Firecrawl] Error on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

        return None

    def extract_products_from_page(self, url: str) -> str:
        """
        Fetch page content for manual parsing.

        Args:
            url: Listing page URL

        Returns:
            HTML/Markdown content
        """
        return self.scrape_page(url)
