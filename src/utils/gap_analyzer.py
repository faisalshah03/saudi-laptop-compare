"""
Noon Assortment Gap Analysis

Takes the merged "universe" of products (all platforms) and classifies
each one relative to Noon's catalog:

  - "Exact Match"       - the product-matcher already linked a Noon
                           listing to this same master SKU (same specs)
  - "Similar Available" - Noon doesn't carry this exact SKU, but does
                           carry something close (same brand + mostly
                           overlapping specs) - a near-miss, not a true gap
  - "Not Available"     - no reasonable match on Noon at all - a genuine
                           assortment gap

This reuses ProductMatcher's existing spec-extraction/scoring logic
rather than re-implementing matching from scratch.
"""

from typing import List, Dict, Any
from utils.product_matcher import ProductMatcher


SIMILAR_MATCH_THRESHOLD = 0.5   # below EXACT_MATCH_THRESHOLD, above this = "similar"
EXACT_MATCH_THRESHOLD = 0.8     # matches ProductMatcher's own merge threshold


class NoonGapAnalyzer:
    def __init__(self):
        self.matcher = ProductMatcher()

    def analyze(self, unified_products: List[Dict[str, Any]],
               raw_noon_products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Args:
            unified_products: merged master products (list of dicts from
                ProductMatcher.merge_products().values()) - already has
                noon_price/noon_link populated where an exact merge happened
            raw_noon_products: the raw (unmerged) Noon product list, used
                for the fuzzy "similar available" pass

        Returns:
            List of gap-analysis rows, one per non-Noon universe product
        """
        # Pre-extract specs for all raw Noon products once, for fuzzy comparison
        noon_specs = []
        for np in raw_noon_products:
            specs = self.matcher.extract_specs_from_title(np['raw_title'])
            noon_specs.append((np, specs))

        rows = []

        for product in unified_products:
            available_on = [
                platform.replace('_', '.').title()
                for platform in ['amazon_sa', 'jarir', 'extra']
                if product.get(f'{platform}_price') is not None
            ]

            if not available_on:
                # This master product only exists on Noon itself - not a
                # competitor-assortment gap, skip it from this report
                continue

            row = {
                'master_sku': product.get('master_sku'),
                'title': product.get('title'),
                'category': product.get('category'),
                'brand': product.get('brand'),
                'model_name': product.get('model_name'),
                'processor': product.get('processor'),
                'ram': product.get('ram'),
                'storage': product.get('storage'),
                'available_on': ', '.join(available_on),
                'best_price_elsewhere': product.get('best_price'),
                'best_price_platform': product.get('best_price_platform'),
            }

            if product.get('noon_price') is not None:
                row['noon_status'] = 'Exact Match'
                row['noon_price'] = product.get('noon_price')
                row['noon_link'] = product.get('noon_link')
                row['noon_similar_product'] = None
                row['price_diff_vs_noon'] = (
                    row['best_price_elsewhere'] - row['noon_price']
                    if row['best_price_elsewhere'] is not None else None
                )
                rows.append(row)
                continue

            # Not exactly matched - run the fuzzy pass against raw Noon listings
            product_specs = {
                k: product.get(k) for k in
                ['brand', 'model_name', 'model_number', 'processor', 'ram', 'storage']
                if product.get(k)
            }

            best_score = 0.0
            best_match = None
            for noon_product, n_specs in noon_specs:
                if product.get('category') and noon_product.get('category') and \
                   product['category'] != noon_product['category']:
                    continue
                match = self.matcher.calculate_match_score(product_specs, n_specs)
                if match.score > best_score:
                    best_score = match.score
                    best_match = noon_product

            if best_score >= EXACT_MATCH_THRESHOLD and best_match:
                # Fuzzy pass found what the merge pass missed
                row['noon_status'] = 'Exact Match'
                row['noon_price'] = best_match.get('price')
                row['noon_link'] = best_match.get('product_url')
                row['noon_similar_product'] = None
                row['price_diff_vs_noon'] = (
                    row['best_price_elsewhere'] - row['noon_price']
                    if row['best_price_elsewhere'] is not None and row['noon_price'] is not None else None
                )
            elif best_score >= SIMILAR_MATCH_THRESHOLD and best_match:
                row['noon_status'] = 'Similar Available'
                row['noon_price'] = None
                row['noon_link'] = None
                row['noon_similar_product'] = best_match.get('raw_title')
                row['noon_similar_price'] = best_match.get('price')
                row['noon_similar_url'] = best_match.get('product_url')
                row['match_confidence'] = round(best_score, 2)
                row['price_diff_vs_noon'] = None
            else:
                row['noon_status'] = 'Not Available'
                row['noon_price'] = None
                row['noon_link'] = None
                row['noon_similar_product'] = None
                row['price_diff_vs_noon'] = None

            rows.append(row)

        return rows

    def summarize(self, gap_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Produce headline stats for the gap analysis."""
        total = len(gap_rows)
        exact = sum(1 for r in gap_rows if r['noon_status'] == 'Exact Match')
        similar = sum(1 for r in gap_rows if r['noon_status'] == 'Similar Available')
        missing = sum(1 for r in gap_rows if r['noon_status'] == 'Not Available')

        by_brand = {}
        for r in gap_rows:
            if r['noon_status'] != 'Not Available':
                continue
            brand = r.get('brand') or 'Unknown'
            by_brand[brand] = by_brand.get(brand, 0) + 1

        return {
            'total_universe_products': total,
            'exact_match_count': exact,
            'exact_match_pct': round(100 * exact / total, 1) if total else 0,
            'similar_available_count': similar,
            'similar_available_pct': round(100 * similar / total, 1) if total else 0,
            'not_available_count': missing,
            'not_available_pct': round(100 * missing / total, 1) if total else 0,
            'missing_by_brand': dict(sorted(by_brand.items(), key=lambda x: -x[1])),
        }
