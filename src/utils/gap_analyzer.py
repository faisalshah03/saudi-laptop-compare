"""
Cross-Platform Assortment Gap Analysis

Classifies products from a "base" platform (or the combined universe of
several platforms) against a "compare" platform's catalog:

  - "Exact Match"       - the product-matcher already linked a listing on
                           the compare platform to this same master SKU
  - "Similar Available" - the compare platform doesn't carry this exact
                           SKU, but does carry something close (same
                           brand + mostly overlapping specs) - a
                           near-miss, not a true gap
  - "Not Available"     - no reasonable match on the compare platform at
                           all - a genuine assortment gap

Supports two modes:
  - Universe mode (base_platform_key=None): base = "any of Amazon/Jarir/
    Extra", used for the combined "Noon Assortment Gap" report.
  - Single-platform mode (base_platform_key='jarir'/'extra'/'amazon_sa'):
    base = only that platform's listings, used for the "Jarir vs Noon",
    "Extra vs Noon", "Amazon vs Noon" reports - each treats that one
    platform's SKUs as the base set and checks Noon's coverage of them
    specifically, rather than lumping all three together.

This reuses ProductMatcher's existing spec-extraction/scoring logic
rather than re-implementing matching from scratch.
"""

from typing import List, Dict, Any, Optional
from utils.product_matcher import ProductMatcher


SIMILAR_MATCH_THRESHOLD = 0.5   # below EXACT_MATCH_THRESHOLD, above this = "similar"
EXACT_MATCH_THRESHOLD = 0.8     # matches ProductMatcher's own merge threshold

BASE_PLATFORM_LABELS = {
    'amazon_sa': 'Amazon.sa',
    'jarir': 'Jarir',
    'extra': 'Extra',
    'noon': 'Noon',
}


class NoonGapAnalyzer:
    def __init__(self):
        self.matcher = ProductMatcher()

    def analyze(self, unified_products: List[Dict[str, Any]],
               raw_compare_products: List[Dict[str, Any]],
               base_platform_key: Optional[str] = None,
               compare_platform_key: str = 'noon') -> List[Dict[str, Any]]:
        """
        Args:
            unified_products: merged master products (list of dicts from
                ProductMatcher.merge_products().values())
            raw_compare_products: the raw (unmerged) product list for the
                compare platform, used for the fuzzy "similar available" pass
            base_platform_key: None = universe (any of amazon_sa/jarir/
                extra); or a specific platform key to scope the base set
                to just that one platform's listings
            compare_platform_key: platform to check coverage against
                (default 'noon')

        Returns:
            List of gap-analysis rows, one per base-set product
        """
        compare_specs = [
            (cp, self.matcher.extract_specs_from_title(cp['raw_title']))
            for cp in raw_compare_products
        ]

        universe_keys = [k for k in ['amazon_sa', 'jarir', 'extra'] if k != compare_platform_key]
        rows = []

        for product in unified_products:
            if base_platform_key:
                if product.get(f'{base_platform_key}_price') is None:
                    continue
                available_on = [BASE_PLATFORM_LABELS[base_platform_key]]
            else:
                available_on = [
                    BASE_PLATFORM_LABELS[k] for k in universe_keys
                    if product.get(f'{k}_price') is not None
                ]
                if not available_on:
                    # Only exists on the compare platform itself - not a
                    # gap from the base side, skip it from this report
                    continue

            row = {
                'master_sku': product.get('master_sku'),
                'title': product.get('title'),
                'category': product.get('category'),
                'brand': product.get('brand'),
                'model_name': product.get('model_name'),
                'processor': product.get('processor'),
                'processor_full': product.get('processor_full'),
                'ram': product.get('ram'),
                'storage': product.get('storage'),
                'graphics_card': product.get('graphics_card'),
                'ai_classification': product.get('ai_classification'),
                'available_on': ', '.join(available_on),
                'base_price': product.get(f'{base_platform_key}_price') if base_platform_key else product.get('best_price'),
                'base_link': product.get(f'{base_platform_key}_link') if base_platform_key else None,
                'best_price_elsewhere': product.get('best_price'),
                'best_price_platform': product.get('best_price_platform'),
            }

            compare_price_key = f'{compare_platform_key}_price'
            compare_link_key = f'{compare_platform_key}_link'

            if product.get(compare_price_key) is not None:
                row['compare_status'] = 'Exact Match'
                row['compare_price'] = product.get(compare_price_key)
                row['compare_link'] = product.get(compare_link_key)
                row['compare_similar_product'] = None
                row['price_diff_vs_compare'] = (
                    row['best_price_elsewhere'] - row['compare_price']
                    if row['best_price_elsewhere'] is not None else None
                )
                rows.append(row)
                continue

            # Not exactly matched - run the fuzzy pass against raw compare-platform listings
            product_specs = {
                k: product.get(k) for k in
                ['brand', 'model_name', 'model_number', 'processor', 'ram', 'storage']
                if product.get(k)
            }

            best_score = 0.0
            best_match = None
            for compare_product, c_specs in compare_specs:
                if product.get('category') and compare_product.get('category') and \
                   product['category'] != compare_product['category']:
                    continue
                match = self.matcher.calculate_match_score(product_specs, c_specs)
                if match.score > best_score:
                    best_score = match.score
                    best_match = compare_product

            if best_score >= EXACT_MATCH_THRESHOLD and best_match:
                row['compare_status'] = 'Exact Match'
                row['compare_price'] = best_match.get('price')
                row['compare_link'] = best_match.get('product_url')
                row['compare_similar_product'] = None
                row['price_diff_vs_compare'] = (
                    row['best_price_elsewhere'] - row['compare_price']
                    if row['best_price_elsewhere'] is not None and row['compare_price'] is not None else None
                )
            elif best_score >= SIMILAR_MATCH_THRESHOLD and best_match:
                row['compare_status'] = 'Similar Available'
                row['compare_price'] = None
                row['compare_link'] = None
                row['compare_similar_product'] = best_match.get('raw_title')
                row['compare_similar_price'] = best_match.get('price')
                row['compare_similar_url'] = best_match.get('product_url')
                row['match_confidence'] = round(best_score, 2)
                row['price_diff_vs_compare'] = None
            else:
                row['compare_status'] = 'Not Available'
                row['compare_price'] = None
                row['compare_link'] = None
                row['compare_similar_product'] = None
                row['price_diff_vs_compare'] = None

            rows.append(row)

        return rows

    def summarize(self, gap_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Produce headline stats for a gap analysis result."""
        total = len(gap_rows)
        exact = sum(1 for r in gap_rows if r['compare_status'] == 'Exact Match')
        similar = sum(1 for r in gap_rows if r['compare_status'] == 'Similar Available')
        missing = sum(1 for r in gap_rows if r['compare_status'] == 'Not Available')

        by_brand = {}
        for r in gap_rows:
            if r['compare_status'] != 'Not Available':
                continue
            brand = r.get('brand') or 'Unknown'
            by_brand[brand] = by_brand.get(brand, 0) + 1

        return {
            'total_base_products': total,
            'exact_match_count': exact,
            'exact_match_pct': round(100 * exact / total, 1) if total else 0,
            'similar_available_count': similar,
            'similar_available_pct': round(100 * similar / total, 1) if total else 0,
            'not_available_count': missing,
            'not_available_pct': round(100 * missing / total, 1) if total else 0,
            'missing_by_brand': dict(sorted(by_brand.items(), key=lambda x: -x[1])),
        }
