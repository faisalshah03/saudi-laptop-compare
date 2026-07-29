"""
Intelligent product matching and deduplication system
Merges identical products across multiple platforms using multi-tier matching strategy
"""

import re
from typing import List, Dict, Tuple, Set
from difflib import SequenceMatcher
from dataclasses import dataclass


@dataclass
class MatchResult:
    """Result of product matching"""
    score: float  # 0.0 to 1.0
    tier: int  # 1 (exact), 2 (high), 3 (fuzzy)
    details: str  # Why this match occurred


class ProductMatcher:
    """Match and merge products from multiple platforms"""

    # Common brand variations
    BRAND_ALIASES = {
        'hp': ['hp', 'hewlett-packard'],
        'dell': ['dell'],
        'lenovo': ['lenovo'],
        'asus': ['asus', 'asustek'],
        'acer': ['acer'],
        'msi': ['msi', 'micro-star'],
        'apple': ['apple', 'macbook'],
        'razer': ['razer'],
        'alienware': ['alienware'],
        'rog': ['rog'],  # ASUS ROG
        'pavilion': ['pavilion'],
        'inspiron': ['inspiron'],
        'vostro': ['vostro'],
        'xps': ['xps'],
        'vivobook': ['vivobook'],
        'thinkpad': ['thinkpad'],
    }

    def __init__(self):
        self.products_by_sku = {}  # master_sku -> [products]
        self.products_by_platform = {}  # platform -> [products]

    def extract_specs_from_title(self, title: str) -> Dict[str, str]:
        """Extract specifications from product title using regex patterns."""
        title_lower = title.lower()
        specs = {
            'brand': self._extract_brand(title_lower),
            'model_name': self._extract_model_name(title),
            'model_number': self._extract_model_number(title),
            'processor': self._extract_processor(title),
            'ram': self._extract_ram(title),
            'storage': self._extract_storage(title),
            'graphics_card': self._extract_gpu(title),
        }
        return {k: v for k, v in specs.items() if v}

    def _extract_brand(self, title_lower: str) -> str:
        """Extract brand from title."""
        for canonical, aliases in self.BRAND_ALIASES.items():
            for alias in aliases:
                if f' {alias} ' in f' {title_lower} ' or title_lower.startswith(alias):
                    return canonical.title()
        return None

    def _extract_model_name(self, title: str) -> str:
        """Extract model name (e.g., 'Pavilion 15', 'MacBook Air')."""
        patterns = [
            r'(Pavilion|Inspiron|Vostro|XPS|ThinkPad|VivoBook|MacBook|IdeaPad|ZenBook|ROG|Swift|Aspire|FX|TUF)\s+[\w\s-]+(?:\d+)',
            r'(Pavilion|Inspiron|Vostro|XPS|ThinkPad|VivoBook|MacBook|IdeaPad|ZenBook|ROG|Swift|Aspire|FX|TUF)\s+\d+',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                model = match.group(0).strip()
                # Remove generation indicators for consistency
                model = re.sub(r'\(.*\)', '', model).strip()
                return model

        return None

    def _extract_model_number(self, title: str) -> str:
        """Extract model number/SKU (e.g., '15-eg2013ne', 'A2338')."""
        patterns = [
            r'(\d{2}-[a-z]{2}\d{4}[a-z]{2})',  # HP format: 15-eg2013ne
            r'([A-Z]\d{4}[A-Z]?)',  # Mac format: A2338, M2338
            r'(SVE\d{7})',  # Sony format
            r'(FX\d{5})',  # ASUS FX format
            r'[\s\(]([A-Z0-9]{6,}?)[\s\)]',  # Generic alphanumeric
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return None

    def _extract_processor(self, title: str) -> str:
        """Extract processor info."""
        patterns = [
            r'(Intel Core i[3579]-\d+[A-Z]{1,2})',
            r'(Intel Core Ultra \d+)',
            r'(AMD Ryzen [357]\s*\d{2,}[A-Z]+)',
            r'(Apple M[1-3]\s*(?:Pro|Max)?)',
            r'(Intel Pentium)',
            r'(Intel Celeron)',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_ram(self, title: str) -> str:
        """Extract RAM capacity."""
        match = re.search(r'(\d+)\s*(?:GB|GB\s)?\s*(?:DDR[3-5]|RAM|Memory)', title, re.IGNORECASE)
        if match:
            return f"{match.group(1)}GB"

        match = re.search(r'(\d+)\s*GB', title)
        if match:
            return f"{match.group(1)}GB"

        return None

    def _extract_storage(self, title: str) -> str:
        """Extract storage capacity."""
        patterns = [
            r'(\d+)\s*TB\s*(?:SSD|HDD)',
            r'(\d+)\s*GB\s*(?:SSD|HDD)',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                value = match.group(1)
                unit = re.search(r'(TB|GB)', title[match.start():], re.IGNORECASE).group(1).upper()
                return f"{value}{unit}"

        return None

    def _extract_gpu(self, title: str) -> str:
        """Extract graphics card info."""
        patterns = [
            r'(NVIDIA\s+(?:GeForce\s+)?(?:RTX|GTX)\s+\d{4}[A-Z]{0,2})',
            r'(NVIDIA\s+(?:RTX|GTX)\s+\d{4})',
            r'(AMD\s+Radeon\s+(?:RX\s+)?\d{4})',
            r'(Intel\s+Iris\s+(?:Xe|Plus)?)',
            r'(Apple\s+GPU)',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def normalize_spec_key(self, key: str) -> str:
        """Normalize spec value for comparison."""
        if not key:
            return ''

        return key.lower().strip()

    def calculate_match_score(self, specs1: Dict, specs2: Dict) -> MatchResult:
        """Calculate match score between two product specs."""
        if not specs1 or not specs2:
            return MatchResult(score=0.0, tier=0, details="Missing specs")

        # Exact match on model number
        if specs1.get('model_number') and specs1['model_number'] == specs2.get('model_number'):
            return MatchResult(score=1.0, tier=1, details="Exact model number match")

        # High confidence match: Brand + Model + Processor + RAM + Storage
        score = 0
        matches = 0
        total = 0

        key_specs = ['brand', 'model_name', 'processor', 'ram', 'storage']
        for spec in key_specs:
            total += 1
            if specs1.get(spec) and specs2.get(spec):
                if self.normalize_spec_key(specs1[spec]) == self.normalize_spec_key(specs2[spec]):
                    score += 1
                    matches += 1

        if total > 0:
            match_ratio = score / total

            if match_ratio >= 0.8:
                return MatchResult(
                    score=match_ratio,
                    tier=2,
                    details=f"High confidence: {matches}/{total} specs match"
                )

        # Fuzzy matching on model name
        if specs1.get('model_name') and specs2.get('model_name'):
            fuzzy_score = SequenceMatcher(
                None,
                self.normalize_spec_key(specs1['model_name']),
                self.normalize_spec_key(specs2['model_name'])
            ).ratio()

            if fuzzy_score >= 0.8:
                return MatchResult(
                    score=fuzzy_score,
                    tier=3,
                    details=f"Fuzzy match: {fuzzy_score:.1%} similar"
                )

        return MatchResult(score=0.0, tier=0, details="No match")

    def generate_master_sku(self, specs: Dict) -> str:
        """Generate unique master SKU from specs."""
        parts = [
            specs.get('brand', 'UNKNOWN'),
            specs.get('model_name', 'MODEL').replace(' ', '-'),
            specs.get('processor', '').split()[0] if specs.get('processor') else '',
            specs.get('ram', '').replace('GB', ''),
        ]

        sku = '-'.join(p for p in parts if p).upper()
        return sku[:32]  # Keep reasonable length

    def merge_products(self, products: List[Dict]) -> Dict[str, Dict]:
        """
        Merge products from all platforms into unified master records.

        Args:
            products: List of product dicts from all platforms

        Returns:
            Dict of master_sku -> unified product data
        """
        matched_groups = {}
        unmatched = []

        # First pass: extract specs for all products
        for product in products:
            product['extracted_specs'] = self.extract_specs_from_title(product['raw_title'])

        # Second pass: match products
        processed = set()

        for i, product1 in enumerate(products):
            if i in processed:
                continue

            specs1 = product1.get('extracted_specs', {})
            master_sku = self.generate_master_sku(specs1)
            matched_group = [product1]

            # Find matching products from other platforms
            for j, product2 in enumerate(products[i + 1:], start=i + 1):
                if j in processed or product2['source_platform'] == product1['source_platform']:
                    continue

                specs2 = product2.get('extracted_specs', {})
                match = self.calculate_match_score(specs1, specs2)

                if match.score >= 0.8:  # Confidence threshold
                    matched_group.append(product2)
                    processed.add(j)

            processed.add(i)
            matched_groups[master_sku] = {
                'master_sku': master_sku,
                'products': matched_group,
                'specs': specs1,
            }

        # Third pass: create unified master records
        unified_products = {}

        for master_sku, group in matched_groups.items():
            unified = {
                'master_sku': master_sku,
                'brand': group['specs'].get('brand'),
                'model_name': group['specs'].get('model_name'),
                'model_number': group['specs'].get('model_number'),
                'processor': group['specs'].get('processor'),
                'ram': group['specs'].get('ram'),
                'storage': group['specs'].get('storage'),
                'graphics_card': group['specs'].get('graphics_card'),
            }

            # Aggregate platform-specific data
            for platform in ['amazon_sa', 'jarir', 'extra', 'noon']:
                unified[f'{platform}_price'] = None
                unified[f'{platform}_link'] = None
                unified[f'{platform}_availability'] = 'Not Listed'

            # Map products to platforms
            for product in group['products']:
                platform = product['source_platform'].lower().replace('.com', '').replace('amazon.sa', 'amazon_sa')
                if 'jarir' in platform.lower():
                    platform = 'jarir'

                platform_key = f"{platform}_price"
                link_key = f"{platform}_link"
                avail_key = f"{platform}_availability"

                if platform_key in unified:
                    unified[platform_key] = product['price']
                    unified[link_key] = product['product_url']
                    unified[avail_key] = product['availability']

            # Calculate best price
            prices = [
                v for k, v in unified.items()
                if k.endswith('_price') and v is not None
            ]

            if prices:
                unified['best_price'] = min(prices)
                for platform in ['amazon_sa', 'jarir', 'extra', 'noon']:
                    if unified.get(f'{platform}_price') == unified['best_price']:
                        unified['best_price_platform'] = platform.title()
                        break
            else:
                unified['best_price'] = None
                unified['best_price_platform'] = None

            unified['last_updated'] = group['products'][0]['scraped_at']
            unified_products[master_sku] = unified

        return unified_products
