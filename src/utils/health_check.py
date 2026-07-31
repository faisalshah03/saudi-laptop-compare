"""
Pipeline health checks and structured run logging.

Distinguishes three states per platform, since a naive "hard fail on low
count" check would incorrectly kill the whole pipeline whenever a
scraper's fallback path (e.g. Jarir's markdown fallback) is legitimately
degraded-but-working:

  - HEALTHY:  count >= expected normal range
  - DEGRADED: count > 0 but below normal (e.g. a fallback path kicked in,
              or a platform partially blocked this run) - log loudly,
              keep going
  - FAILED:   count is ~zero - both primary and any fallback produced
              nothing. This is the one case worth stopping the whole
              pipeline for, since continuing would silently ship data
              that's missing an entire platform with no signal to anyone.
"""

import json
import os
from datetime import datetime
from typing import Dict, List


# (hard_fail_below, degraded_below) per platform. hard_fail_below should
# sit below any legitimate fallback's expected output (e.g. Jarir's
# markdown fallback surfaces ~12-24 products - that's DEGRADED, not FAILED).
THRESHOLDS = {
    'Jarir': (5, 100),
    'Amazon.sa': (5, 30),
    'Noon': (5, 100),
    'Extra': (5, 50),
}


class PlatformScrapeFailure(RuntimeError):
    """Raised when a platform returns ~zero products - both its primary
    method and any fallback failed. This is treated as fatal because
    silently shipping a run missing an entire platform is worse than
    stopping loudly."""
    pass


def check_platform_health(platform_name: str, product_count: int) -> str:
    """Returns 'healthy' / 'degraded' / 'failed'. Raises PlatformScrapeFailure
    if 'failed' (count below the hard-fail threshold)."""
    hard_fail_below, degraded_below = THRESHOLDS.get(platform_name, (1, 10))

    if product_count < hard_fail_below:
        raise PlatformScrapeFailure(
            f"{platform_name} returned only {product_count} products "
            f"(hard-fail threshold: {hard_fail_below}). Both the primary "
            f"scraping method and any fallback appear to have failed - "
            f"stopping the pipeline rather than shipping data silently "
            f"missing this entire platform."
        )

    if product_count < degraded_below:
        print(f"⚠️  HEALTH CHECK: {platform_name} returned {product_count} products "
              f"(expected {degraded_below}+). Likely running in a degraded/fallback "
              f"mode this run - continuing, but this data is incomplete.")
        return 'degraded'

    return 'healthy'


def compute_field_coverage(products: List[Dict], fields: List[str]) -> Dict[str, float]:
    """Percentage of products with a non-null value for each field."""
    total = len(products)
    if total == 0:
        return {f: 0.0 for f in fields}
    return {
        field: round(100 * sum(1 for p in products if p.get(field)) / total, 1)
        for field in fields
    }


def compute_merge_stats(unified_products: List[Dict], raw_products: List[Dict]) -> Dict:
    """Cluster-size stats - a high singleton rate can indicate the matcher
    is failing to find real cross-platform matches (over-fragmentation),
    while a very low unique count relative to raw count can indicate
    over-merging (false positives)."""
    total_raw = len(raw_products)
    total_unified = len(unified_products)

    # Reconstruct cluster sizes from platform-price population
    platform_keys = ['amazon_sa_price', 'jarir_price', 'extra_price', 'noon_price']
    cluster_sizes = []
    for p in unified_products:
        size = sum(1 for k in platform_keys if p.get(k) is not None)
        cluster_sizes.append(max(size, 1))

    singleton_count = sum(1 for s in cluster_sizes if s == 1)

    return {
        'total_raw_listings': total_raw,
        'total_unified_products': total_unified,
        'dedup_ratio': round(total_raw / total_unified, 2) if total_unified else None,
        'singleton_count': singleton_count,
        'singleton_rate_pct': round(100 * singleton_count / total_unified, 1) if total_unified else None,
        'multi_platform_matches': total_unified - singleton_count,
    }


def log_run(log_path: str, platform_counts: Dict[str, int], platform_health: Dict[str, str],
           field_coverage: Dict[str, float], merge_stats: Dict, gap_summary: Dict = None,
           status: str = 'success', error: str = None):
    """Append a structured JSON-lines entry for this run. Append-only, so
    it accumulates a history across runs even though the data/*.json
    snapshots themselves get overwritten each run."""
    entry = {
        'timestamp': datetime.now().isoformat(),
        'status': status,
        'error': error,
        'platform_counts': platform_counts,
        'platform_health': platform_health,
        'field_coverage_pct': field_coverage,
        'merge_stats': merge_stats,
        'gap_summary': gap_summary,
    }

    os.makedirs(os.path.dirname(log_path) or '.', exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')

    print(f"📝 Run logged to {log_path}")
