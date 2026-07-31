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


class _DisjointSet:
    """Union-Find over product indices, used to compute the transitive
    closure of pairwise matches into final clusters. Needed because
    pairwise matching alone is not transitive: A~B and B~C does not
    imply A~C would score a direct match, but they should still end up
    in the same group. A greedy first-match-wins merge (the original
    approach) doesn't guarantee this and is order-dependent."""

    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[ry] = rx


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

    # Fields a scraper may already have populated from a platform's own
    # structured data (Jarir's Constructor.io metadata, Noon's
    # plp_specifications). These are more reliable than title regex when
    # present, so extract_specs() only falls back to title parsing for
    # whichever of these are still missing - it must NOT blindly
    # overwrite good structured data with a fresh title-only extraction.
    STRUCTURED_SPEC_FIELDS = [
        'brand', 'model_name', 'model_number', 'processor',
        'ram', 'storage', 'graphics_card', 'subtype',
    ]

    def __init__(self):
        self.products_by_sku = {}  # master_sku -> [products]
        self.products_by_platform = {}  # platform -> [products]

    def extract_specs(self, product: Dict) -> Dict[str, str]:
        """Build a product's spec dict, preferring whatever structured
        data the scraper already populated (from a platform's own clean
        API/metadata), and only falling back to title-regex extraction
        for fields that are still missing. This is the fix for specs
        silently going missing when a platform's structured data doesn't
        cover a field - title parsing acts as a second-layer fallback
        instead of never running, or (the previous bug) always running
        and discarding good structured data in the process."""
        title_specs = self.extract_specs_from_title(product.get('raw_title', ''))

        specs = {}
        for field in self.STRUCTURED_SPEC_FIELDS:
            structured_value = product.get(field)
            specs[field] = structured_value if structured_value else title_specs.get(field)

        return {k: v for k, v in specs.items() if v}

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
            'subtype': self._extract_subtype(title),
        }
        return {k: v for k, v in specs.items() if v}

    def _extract_brand(self, title_lower: str) -> str:
        """Extract brand from title."""
        for canonical, aliases in self.BRAND_ALIASES.items():
            for alias in aliases:
                if f' {alias} ' in f' {title_lower} ' or title_lower.startswith(alias):
                    return canonical.title()
        return None

    # Known model-line keywords, used as a fallback when the comma-split
    # heuristic doesn't isolate a clean model name (e.g. no comma in title)
    MODEL_KEYWORDS = (
        r'Pavilion|Inspiron|Vostro|XPS|Latitude|Precision|ThinkPad|ThinkBook|'
        r'Legion|LOQ|VivoBook|ZenBook|ExpertBook|ROG|TUF|MacBook|IdeaPad|'
        r'Yoga|Swift|Aspire|Nitro|Predator|Spin|Chromebook|Victus|OmniBook|'
        r'EliteBook|ProBook|Envy|Katana|Bravo|Modern|Stealth|Raider|Titan|'
        r'Galaxy Book|Surface|Zephyrus|Strix|Flow'
    )

    def _extract_model_name(self, title: str) -> str:
        """Extract model name (e.g., 'IdeaPad Slim 3', 'MacBook Air')."""
        # Listings are typically "Brand Model Line, Spec, Spec, ..." -
        # the segment before the first comma is the cleanest model description
        first_segment = title.split(',')[0].strip()

        # Titles without an early comma (common on Amazon, which often
        # uses " - " or "|" instead) would otherwise leave first_segment
        # as nearly the whole title. Truncate at the first spec/detail
        # boundary - an inch mark, a spaced dash, a pipe, or a number
        # immediately followed by a spec unit - since that's where the
        # actual model designator ends and free-text spec description
        # begins.
        boundary_match = re.search(
            r'["|]|\s-\s|\b\d+\s*(?:GB|TB|GHz|MHz)\b|\b\d+(?:th|st|nd|rd)?\s*Gen\b',
            first_segment, re.IGNORECASE
        )
        if boundary_match:
            first_segment = first_segment[:boundary_match.start()].strip()

        # Strip generic trailing/descriptor words that aren't part of the model name
        cleaned = re.sub(
            r'\b(Laptop|Desktop|Computer|PC|Gaming|Notebook|Tower|All[- ]in[- ]One)\b',
            '',
            first_segment,
            flags=re.IGNORECASE
        ).strip()
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)

        # Remove the brand prefix if present, keep the rest as model name
        brand = self._extract_brand(title.lower())
        if brand and cleaned.lower().startswith(brand.lower()):
            cleaned = cleaned[len(brand):].strip()

        if cleaned and len(cleaned) >= 2:
            return cleaned

        # Fallback: known model-line keyword search anywhere in the title
        pattern = rf'({self.MODEL_KEYWORDS})\s*[\w-]*(?:\s+\d+\w*)?'
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return re.sub(r'\(.*\)', '', match.group(0)).strip()

        return None

    def _extract_model_number(self, title: str) -> str:
        """Extract model number/SKU (e.g., '15-eg2013ne', 'A2338').

        The generic fallback pattern requires at least one digit in the
        matched token - without this, it was matching plain English words
        like "ThinkBook" or "Windows" (6+ letters between whitespace) and
        treating them as model numbers, causing unrelated products that
        both happened to mention the same common word to falsely tier-1
        "exact match" merge."""
        patterns = [
            r'(\d{2}-[a-z]{2}\d{4}[a-z]{2})',  # HP format: 15-eg2013ne
            r'(?<!\d)([A-Z]\d{4}[A-Z]?)',  # Mac format: A2338, M2338 - not preceded
                                             # by a digit, so "1920x1080" doesn't match
                                             # (the 'x' there is directly preceded by '0')
            r'(SVE\d{7})',  # Sony format
            r'(FX\d{5})',  # ASUS FX format
            r'[\s\(]([A-Z0-9]{6,}?)[\s\)]',  # Generic alphanumeric - filtered below
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                token = match.group(1).upper()
                if any(c.isdigit() for c in token):
                    return token

        return None

    def _extract_processor(self, title: str) -> str:
        """Extract processor info. Handles both full SKUs (i5-1355U) and
        bare tiers (just "Intel Core i5"), since listings frequently omit
        the specific SKU suffix."""
        patterns = [
            r'(Intel Core i[3579]-\d+[A-Za-z]{0,3})',       # Intel Core i5-1355U
            r'(Intel Core Ultra [579]\s*\d{0,3}[A-Za-z]{0,2})',  # Ultra 7 155H (full SKU + suffix,
                                                                    # not just the bare tier number)
            r'(Intel Core [3579](?!\d))',                     # Jarir style: "Intel Core 7" (no "i")
            r'(AMD Ryzen [357]\s*\d{2,4}[A-Za-z]{0,3})',      # AMD Ryzen 7 7730U
            r'(Apple M[1-9]\s*(?:Pro|Max|Ultra)?)',           # Apple M2 Pro (M1..M9, future-proofed)
            r'(i[3579]-\d{4,5}[A-Za-z]{0,3})',                # bare SKU, no brand prefix: i5-10310U
            r'(Ryzen [357]\s*\d{3,4}[A-Za-z]{0,3})',          # bare "Ryzen 7 7730U"
            r'(Intel Core i[3579])(?!-)',                     # bare "Intel Core i5"
            r'(AMD Ryzen [357])(?!\s*\d)',                    # bare "AMD Ryzen 5"
            r'((?:Intel\s+)?Pentium(?:\s+Gold|\s+Silver)?)',
            r'((?:Intel\s+)?Celeron)',
            r'(Snapdragon\s*[\w\s]*\d)',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return re.sub(r'\s{2,}', ' ', match.group(1).strip())

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
        """Extract graphics card info. Handles dedicated GPUs with a model
        number (RTX 4060) as well as listings that only give VRAM size
        (e.g. "NVIDIA GeForce 4 GB") and generic integrated graphics."""
        patterns = [
            r'(NVIDIA\s+(?:GeForce\s+)?(?:RTX|GTX)\s+\d{3,4}[A-Za-z]{0,2}(?:\s+\d+\s*GB)?)',
            r'(NVIDIA\s+(?:GeForce\s+)?\d+\s*GB)',              # "NVIDIA GeForce 4 GB" (no model #)
            r'(AMD\s+Radeon\s+(?:RX\s+)?\d{3,4}[A-Za-z]{0,2})',
            r'(AMD\s+Radeon\s+Graphics)',
            r'(Intel\s+Iris\s+X?e?\s*(?:Plus|Graphics)?)',
            r'(Intel\s+UHD\s+Graphics(?:\s+\d+)?)',
            r'(Apple\s+GPU|Apple\s+Integrated\s+Graphics)',
            r'(Intel\s+(?:Integrated\s+)?Graphics)',            # generic fallback
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return re.sub(r'\s{2,}', ' ', match.group(1).strip())

        return None

    def _extract_subtype(self, title: str) -> str:
        """Extract product subtype/use-case (Gaming, 2-in-1, Business, etc.)."""
        title_lower = title.lower()

        subtype_rules = [
            ('Gaming', r'\bgaming\b'),
            ('2-in-1 / Convertible', r'\b(2[\s-]in[\s-]1|convertible)\b'),
            ('Chromebook', r'\bchromebook\b'),
            ('All-in-One', r'\ball[\s-]in[\s-]one\b'),
            ('Mini PC', r'\bmini\s*pc\b'),
            ('Workstation', r'\bworkstation\b'),
            ('Business', r'\b(thinkpad|latitude|elitebook|probook|expertbook|thinkbook|vostro)\b'),
            ('Ultrabook', r'\b(ultrabook|thin\s*(?:&|and)?\s*light)\b'),
        ]

        for label, pattern in subtype_rules:
            if re.search(pattern, title_lower):
                return label

        return 'Standard'

    def normalize_spec_key(self, key: str) -> str:
        """Normalize spec value for comparison."""
        if not key:
            return ''

        return key.lower().strip()

    def _normalize_capacity(self, value: str) -> str:
        """Normalize RAM/storage values to a canonical 'NUMBERUNIT' form
        (e.g. '16GB') for comparison. Different platforms' structured
        data formats these differently even for the identical value -
        Jarir's own metadata gives RAM as "16 GB RAM", our title regex
        extracts "16GB" - a plain string comparison would treat these as
        different and silently block almost every cross-platform match
        once structured data (preferred over regex, see extract_specs)
        is in the mix."""
        if not value:
            return ''
        match = re.search(r'(\d+(?:\.\d+)?)\s*(GB|TB|MB)', str(value), re.IGNORECASE)
        if not match:
            return self.normalize_spec_key(value)
        num, unit = match.group(1), match.group(2).upper()
        if '.' in num and float(num) == int(float(num)):
            num = str(int(float(num)))
        return f"{num}{unit}"

    def _processors_match(self, v1: str, v2: str) -> bool:
        """Compare processor strings after stripping descriptive wrapper
        text that varies between structured platform data and
        title-regex extraction ("(13th Gen)", "CPU", "10-core") for the
        identical chip. Uses prefix matching rather than pure fuzzy
        similarity - "Intel Core i5" and "Intel Core i7" are a single
        character apart and would falsely fuzzy-match despite being
        meaningfully different tiers, whereas one side simply lacking
        the full SKU suffix (bare tier vs. full SKU) should still count
        as a match."""
        def strip_wrapper(v):
            v = re.sub(r'\(.*?\)', '', str(v))
            v = re.sub(r'\b(CPU|Processor|\d+-core|\d+\s*Core)\b', '', v, flags=re.IGNORECASE)
            return self.normalize_spec_key(re.sub(r'\s{2,}', ' ', v))

        n1, n2 = strip_wrapper(v1), strip_wrapper(v2)
        if not n1 or not n2:
            return False
        return n1 == n2 or n1.startswith(n2) or n2.startswith(n1)

    def _model_numeric_tokens(self, model_name: str) -> Set[str]:
        """Extract distinguishing numeric tokens from a model name (e.g.
        '7430' from 'Latitude 7430'). Used to stop fuzzy title matching
        from conflating same-line-different-generation products like
        'Latitude 7430' vs 'Latitude 7440', which score high on
        SequenceMatcher similarity despite being different products."""
        if not model_name:
            return set()
        return set(re.findall(r'\d{3,4}', model_name))

    def _model_names_match(self, name1: str, name2: str) -> bool:
        """Fuzzy-compare two model names, gated by numeric-token agreement.
        Exact string equality is too strict here: different platforms/
        sellers phrase the same physical product's model name slightly
        differently (e.g. "EliteBook 845 G8 14" vs "EliteBook 845 G8
        Business" - same product, different trailing descriptor).
        A pure fuzzy ratio is too loose on its own though - it can't
        tell "Latitude 7430" from "Latitude 7440" (tiny edit distance).
        Combining both: fuzzy similarity as the primary signal, with a
        hard veto if both names carry DIFFERENT distinguishing numeric
        tokens."""
        if not name1 or not name2:
            return False

        n1, n2 = self.normalize_spec_key(name1), self.normalize_spec_key(name2)
        if n1 == n2:
            return True

        tokens1 = self._model_numeric_tokens(name1)
        tokens2 = self._model_numeric_tokens(name2)
        if tokens1 and tokens2 and tokens1 != tokens2:
            return False

        return SequenceMatcher(None, n1, n2).ratio() >= 0.72

    def calculate_match_score(self, specs1: Dict, specs2: Dict,
                             category1: str = None, category2: str = None) -> MatchResult:
        """Calculate match score between two product specs.

        Fixed vs. the original version: the comparable-fields denominator
        now only counts fields present on BOTH sides (a product missing
        3 of 5 fields could previously never score above 0.4 even if its
        2 comparable fields matched perfectly). Tier 3 fuzzy title
        matching is now gated behind brand + at least one other spec
        agreement, plus a numeric-token check, so e.g. "Dell Latitude
        7430" can no longer fuzzy-match "Dell Latitude 7440".
        """
        if not specs1 or not specs2:
            return MatchResult(score=0.0, tier=0, details="Missing specs")

        # Never match a laptop against a desktop, regardless of spec similarity
        if category1 and category2 and category1 != category2:
            return MatchResult(score=0.0, tier=0, details="Category mismatch")

        # Tier 1: exact match on model number
        if specs1.get('model_number') and specs1['model_number'] == specs2.get('model_number'):
            return MatchResult(score=1.0, tier=1, details="Exact model number match")

        # Tier 2: spec overlap, scored only over fields present on both sides.
        # model_name uses fuzzy comparison (see _model_names_match) since
        # exact string equality rarely holds across platforms/sellers for
        # the same physical product; the other fields are standardized
        # enough (RAM/storage/processor SKUs, brand names) to compare exactly.
        key_specs = ['brand', 'model_name', 'processor', 'ram', 'storage']
        comparable = 0
        matches = 0
        model_name_matches = False
        for spec in key_specs:
            v1, v2 = specs1.get(spec), specs2.get(spec)
            if v1 and v2:
                comparable += 1
                if spec == 'model_name':
                    is_match = self._model_names_match(v1, v2)
                elif spec in ('ram', 'storage'):
                    is_match = self._normalize_capacity(v1) == self._normalize_capacity(v2)
                elif spec == 'processor':
                    is_match = self._processors_match(v1, v2)
                else:
                    is_match = self.normalize_spec_key(v1) == self.normalize_spec_key(v2)
                if is_match:
                    matches += 1
                    if spec == 'model_name':
                        model_name_matches = True

        # Require at least 3 comparable fields (not 2 - "brand" and "ram"
        # alone are both weak/common signals; e.g. two completely
        # different Lenovo laptops that both happen to have 16GB RAM
        # would otherwise falsely match at 2/2). ALSO require model_name
        # specifically to be among the agreeing fields - it's the one
        # field that actually distinguishes different products in the
        # same brand line; without this, "brand+ram+storage all match"
        # can still conflate two different models that share a common
        # config (e.g. any 16GB/512GB laptop from the same brand).
        if comparable >= 3 and model_name_matches:
            match_ratio = matches / comparable
            if match_ratio >= 0.8:
                return MatchResult(
                    score=match_ratio,
                    tier=2,
                    details=f"High confidence: {matches}/{comparable} comparable specs match"
                )

        # Tier 3: fuzzy title match, gated behind brand + another spec
        # agreeing first, and behind numeric-token agreement in the model
        # name, so same-brand different-generation products don't collide.
        brand_match = (
            specs1.get('brand') and specs2.get('brand') and
            self.normalize_spec_key(specs1['brand']) == self.normalize_spec_key(specs2['brand'])
        )
        def _spec_matches(spec_name, a, b):
            if spec_name == 'processor':
                return self._processors_match(a, b)
            if spec_name in ('ram', 'storage'):
                return self._normalize_capacity(a) == self._normalize_capacity(b)
            return self.normalize_spec_key(a) == self.normalize_spec_key(b)

        other_spec_match = any(
            specs1.get(s) and specs2.get(s) and _spec_matches(s, specs1[s], specs2[s])
            for s in ['processor', 'ram', 'storage']
        )

        if brand_match and other_spec_match and specs1.get('model_name') and specs2.get('model_name'):
            tokens1 = self._model_numeric_tokens(specs1['model_name'])
            tokens2 = self._model_numeric_tokens(specs2['model_name'])

            # If both model names carry a distinguishing numeric token
            # (e.g. "7430" vs "7440"), they must match exactly - fuzzy
            # string similarity is not trustworthy for this.
            if tokens1 and tokens2 and tokens1 != tokens2:
                return MatchResult(score=0.0, tier=0, details="Numeric model token mismatch")

            fuzzy_score = SequenceMatcher(
                None,
                self.normalize_spec_key(specs1['model_name']),
                self.normalize_spec_key(specs2['model_name'])
            ).ratio()

            if fuzzy_score >= 0.85:
                return MatchResult(
                    score=fuzzy_score,
                    tier=3,
                    details=f"Fuzzy match (brand+spec gated): {fuzzy_score:.1%} similar"
                )

        return MatchResult(score=0.0, tier=0, details="No match")

    def generate_master_sku(self, specs: Dict, category: str = None) -> str:
        """Generate unique master SKU from specs."""
        parts = [
            (category or '')[:4],
            specs.get('brand', 'UNKNOWN'),
            specs.get('model_name', 'MODEL').replace(' ', '-'),
            specs.get('processor', '').split()[0] if specs.get('processor') else '',
            specs.get('ram', '').replace('GB', ''),
        ]

        sku = '-'.join(p for p in parts if p).upper()

        # Disambiguate collisions (e.g. identical specs, different listing)
        return sku[:40]

    def _pick_representative_specs(self, group: List[Dict]) -> Dict:
        """Pick the most complete extracted_specs dict among a matched
        group, rather than always using whichever product happened to be
        first (which could be the sparsest listing in the group)."""
        def completeness(product):
            specs = product.get('extracted_specs', {})
            return (len(specs), len(product.get('raw_title', '')))

        best_product = max(group, key=completeness)
        return best_product.get('extracted_specs', {})

    def merge_products(self, products: List[Dict]) -> Dict[str, Dict]:
        """
        Merge products from all platforms into unified master records.

        Uses pairwise matching (calculate_match_score) plus Union-Find to
        take the transitive closure of matches into clusters, so that if
        A matches B and B matches C, all three end up in one group even
        if A vs C alone wouldn't have scored a direct match. A greedy
        first-match-wins approach (the original implementation) doesn't
        guarantee this and produces order-dependent, unstable clusters.

        Args:
            products: List of product dicts from all platforms

        Returns:
            Dict of master_sku -> unified product data
        """
        n = len(products)

        # First pass: extract specs for all products - prefers each
        # platform's own structured data where available, title-regex
        # only fills in gaps (see extract_specs docstring)
        for product in products:
            product['extracted_specs'] = self.extract_specs(product)

        # Second pass: pairwise match + union. Only compare products from
        # different platforms - this matcher links the same product
        # ACROSS platforms, it's not meant to dedupe within-platform
        # listing variants (colors, bundles, etc.) against each other.
        dsu = _DisjointSet(n)

        for i in range(n):
            for j in range(i + 1, n):
                if products[i]['source_platform'] == products[j]['source_platform']:
                    continue

                match = self.calculate_match_score(
                    products[i]['extracted_specs'], products[j]['extracted_specs'],
                    products[i].get('category'), products[j].get('category')
                )

                if match.score >= 0.8:
                    dsu.union(i, j)

        # Group by cluster root
        clusters: Dict[int, List[Dict]] = {}
        for i in range(n):
            root = dsu.find(i)
            clusters.setdefault(root, []).append(products[i])

        # Third pass: create unified master records
        unified_products = {}
        used_skus = set()

        for group in clusters.values():
            specs = self._pick_representative_specs(group)
            category = group[0].get('category')

            base_sku = self.generate_master_sku(specs, category)
            master_sku = base_sku
            suffix = 2
            while master_sku in used_skus:
                master_sku = f"{base_sku}-{suffix}"
                suffix += 1
            used_skus.add(master_sku)

            # Prefer the longest raw title in the group - it's usually the
            # most complete/descriptive listing across matched platforms
            representative_title = max((p['raw_title'] for p in group), key=len)

            unified = {
                'master_sku': master_sku,
                'title': representative_title,
                'category': category,
                'subtype': specs.get('subtype'),
                'brand': specs.get('brand'),
                'model_name': specs.get('model_name'),
                'model_number': specs.get('model_number'),
                'processor': specs.get('processor'),
                'ram': specs.get('ram'),
                'storage': specs.get('storage'),
                'graphics_card': specs.get('graphics_card'),
            }

            # Aggregate platform-specific data
            for platform in ['amazon_sa', 'jarir', 'extra', 'noon']:
                unified[f'{platform}_price'] = None
                unified[f'{platform}_link'] = None
                unified[f'{platform}_availability'] = 'Not Listed'

            # Map products to platforms
            for product in group:
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

            unified['last_updated'] = group[0]['scraped_at']
            unified_products[master_sku] = unified

        return unified_products
