# Saudi Arabia Laptop & Desktop Price Comparison System
## Technical Report

**Prepared**: 2026-07-31
**Repo**: [github.com/faisalshah03/saudi-laptop-compare](https://github.com/faisalshah03/saudi-laptop-compare) (public)
**Live dashboard**: Streamlit Community Cloud (auto-deploys on push to `main`)
**Purpose of this document**: full technical account of what was built, how, and why — written for a second reviewer (human or AI) to critique and suggest improvements. Not a marketing summary; includes known gaps and weak spots deliberately.

---

## 1. What This System Does

Scrapes laptop and desktop listings from Saudi e-commerce platforms (Amazon.sa, Jarir.com, Noon.com — Extra.com not yet built), merges duplicate listings of the same physical product across platforms into a single record with per-platform pricing, and outputs:

1. An Excel workbook (price comparison + raw data + Noon gap analysis)
2. A password-protected web dashboard (Streamlit), accessible from any device
3. A **Noon assortment gap analysis** — for a Noon employee, a report of which SKUs available elsewhere in the market Noon does/doesn't carry

Current scale: **604 unique products**, aggregated from **865 raw listings** (345 Jarir, 120 Amazon.sa, 400 Noon).

---

## 2. Architecture

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   Jarir      │   │  Amazon.sa   │   │    Noon      │   (Extra.com: not built)
│  scraper     │   │   scraper    │   │   scraper    │
│ (direct API) │   │ (Firecrawl)  │   │ (Firecrawl   │
│              │   │              │   │  + stealth)  │
└──────┬──────┘   └──────┬──────┘   └──────┬──────┘
       │                  │                  │
       └──────────────────┴──────────────────┘
                          │
                 raw_products.json
                          │
                 ┌────────▼────────┐
                 │  ProductMatcher  │  spec extraction + fuzzy dedup
                 └────────┬────────┘
                          │
                merged_products.json  (604 unique master SKUs)
                          │
              ┌───────────┴───────────┐
              │                       │
     ┌────────▼────────┐    ┌────────▼────────┐
     │  NoonGapAnalyzer │    │  ExcelExporter   │
     └────────┬────────┘    └────────┬────────┘
              │                       │
    noon_gap_analysis.json    saudi_laptop_prices_*.xlsx
              │                       │
              └───────────┬───────────┘
                          │
                 ┌────────▼────────┐
                 │  Streamlit app   │  password-gated, 2 tabs:
                 │  (dashboard.py)  │  Price Comparison / Noon Gap
                 └─────────────────┘
```

**Stack**: Python 3.14, `requests` (Jarir), `firecrawl-py` (Amazon/Noon), `openpyxl` (Excel), `pandas` + `streamlit` (dashboard). No database — flat JSON files in `data/`, regenerated on each pipeline run (`main.py`).

**Deployment**: GitHub (public repo, no secrets committed — verified via `git grep` across full history before making public) → Streamlit Community Cloud (free tier, secrets injected via Streamlit's secrets manager, not committed to the repo).

---

## 3. Scraping Methodology — the interesting part

This is where most of the session's effort went, because the initial naive approach (Firecrawl scrape → regex-parse the rendered markdown of a category listing page) badly undercounted every platform. Each platform needed a different fix.

### 3.1 Jarir.com — was returning ~12 products, now returns 345

**Diagnosis process**: The URL `jarir.com/sa-en/computers-laptops/laptops` rendered exactly 12 products with no "load more," no page-number links, and `?p=2` returned a near-empty response. Inspected the page's embedded Vuex state (`window.__INITIAL_STATE__.category-next.products`) via a real browser session and found it **empty even though the DOM clearly showed 12 rendered products** — meaning this page's content isn't driven by the app's normal category-browsing data flow at all. Conclusion: `/computers-laptops/laptops` is a **curated marketing landing widget** (bestsellers), not a live category query.

**The fix**: Jarir's actual site search *does* have live infinite scroll. Inspecting network traffic during a scroll-triggered fetch surfaced the real backend: `https://ac.cnstrc.com/search/{query}?key=key_KcSYfmQTEwRpBnd9&...` — Jarir's storefront search is powered by **Constructor.io**, and the API key visible in that client-side request is a public, read-only, search-scoped key (standard SaaS pattern, same class as an Algolia search-only key). Calling this endpoint directly:

- `GET https://ac.cnstrc.com/search/laptop?key=key_KcSYfmQTEwRpBnd9&num_results_per_page=100&page=N`
- Returns clean, pre-structured JSON per product: `data.metadata.prcr` (processor), `symm` (RAM), `tsca` (storage), `gyro`/`grpc` (GPU), `brand`, `price`, `url`, `sku` — **no HTML/markdown parsing needed at all**.
- `total_num_results: 941` for "laptop", `414` for "desktop" (before accessory filtering).

**Accessory filtering**: a plain keyword search for "desktop" also matches keyboards, headsets, chargers, etc. Constructor.io returns a `ptyp` (product type) field per result, so results are filtered to an allowlist (`Laptop`, `Gaming Laptop`, `2-in-1 Laptop - Convertible` / `Desktop Computer`) rather than trusting keyword relevance alone.

**Result**: 317 laptops + 28 desktops = 345 products. **The 28 desktops figure was independently cross-checked** by calling the API with a `filters[ptyp]=Desktop Computer` facet filter directly (bypassing keyword search entirely) — it also returns exactly 28. **This confirms 28 is Jarir's actual full desktop-tower catalog, not a scraping shortfall** — Jarir (originally a bookstore) simply has a small standalone-desktop assortment. This is worth knowing before assuming "more scraping = more desktops."

**Cost/speed**: zero Firecrawl usage, plain HTTP requests, sub-second per page. This is now the fastest and cheapest scraper of the three.

**Fragility note**: this depends on Jarir not rotating or restricting that Constructor.io key, and on Constructor.io's response schema staying stable. It's an undocumented integration detail, not a public API contract — worth monitoring, and a markdown-scraping fallback would be sensible for resilience (not currently implemented).

### 3.2 Amazon.sa — worked reasonably well from the start, now covers both categories

Amazon's `/s?k=laptops&i=computers` search results support standard `&page=2`, `&page=3` pagination, confirmed by diffing returned ASINs page-to-page (zero overlap between pages 1 and 2 in testing). Scraped via Firecrawl (markdown output), product blocks parsed by regex around each `/dp/{ASIN}` link. Previously only scraped laptops; now scrapes both laptops and desktops, 3 pages each (capped at 60/category — could be pushed higher, this was a time/cost tradeoff for this session, not a hard technical ceiling).

**Weakness**: still regex-parses noisy Amazon titles for brand/processor/RAM/storage/GPU (Amazon doesn't expose structured spec data the way Jarir's Constructor.io does), so extraction accuracy here is lower than Jarir's. See §6.

### 3.3 Noon.com (Saudi) — wasn't built at all, now covers ~400 products, was the hardest platform

**Attempt 1 — plain HTTP**: blocked outright. `curl` gets `HTTP/2 stream ... INTERNAL_ERROR` — Noon's edge rejects the connection at the protocol level before any content is served. This is deliberate bot detection, not a fluke (reproduced consistently).

**Attempt 2 — Playwright (local headless Chromium)**: also blocked (`ERR_HTTP2_PROTOCOL_ERROR`, then a timeout after adding stealth flags). Headless browser fingerprints are evidently also detected.

**Attempt 3 — real interactive browser session** (via the Chrome DevTools connection used during this session): **worked**. This confirmed the technique was sound and the blocking was specifically about automation signatures, not the approach.

**What actually works**: Noon is a TanStack Start (React SSR meta-framework) app. It embeds its full search-result payload in `window.__TSR_ROUTER__` (route loader data) for client hydration — `catalogData.catalog.hits`, with `nbHits`/`nbPages` (Algolia-shaped field names, suggesting Algolia or an Algolia-compatible engine under the hood). Firecrawl can render this — **but only with `proxy='stealth'`**. With the default (`proxy='basic'`), Firecrawl gets through Noon's bot wall but is served a **wrong, generic, non-Saudi-specific catalog** (`nbHits: 2,817,399`, first result a gaming headset, totally unrelated to the query) — a fallback/degraded response Noon apparently serves to non-trusted sessions. With `proxy='stealth'`, the *same* code path returns correct, Saudi-specific results (`nbHits: 1,512` for "laptop", first result a HUAWEI Matebook D16 — matches what a real browser shows).

**This distinction matters a lot** and is easy to silently get wrong: a scraper that "works" (200 OK, real-looking JSON) but is quietly getting the wrong country's/session's data would poison the whole gap-analysis feature, since the entire point is Saudi-specific assortment comparison. **Flagging explicitly since the user's brief said "Noon is all supposed to be from Saudi only"** — this was in fact the exact failure mode encountered and fixed.

**Implementation**: `client.scrape(url, proxy='stealth', actions=[{'type':'wait',...}, {'type':'executeJavascript','script': '...reads window.__TSR_ROUTER__...'}])`. Firecrawl runs the JS in-page and returns the result. Paginated via `&page=N` on the search URL, capped at 200/category for this session (12 pages max) for cost/time reasons — `nbHits` reports 1,500+ available for "laptop" alone, so there's much more headroom.

**Weakness**: same accessory-keyword-pollution issue as Jarir, handled here with a cruder keyword-exclusion list (`bag`, `sleeve`, `keyboard`, `charger`, etc.) rather than a clean category-ID filter, because Noon's per-product `cat_id` mapping wasn't reverse-engineered in the time available. Processor extraction is regex-based off the title (Noon's `plp_specifications` field reliably gives RAM/storage/OS but not CPU/GPU) — same limitation class as Amazon.

**Reliability**: one full-pipeline run had a transient `ERR_TUNNEL_CONNECTION_FAILED` from Firecrawl's proxy on the very first Noon call, which zeroed out that category for that run. Added a 3-attempt retry with backoff; the retry run succeeded cleanly. Firecrawl + stealth proxy is evidently less rock-solid than a direct API call (Jarir) or plain scraping (Amazon) — expect occasional retries needed in production/scheduled runs.

### 3.4 Extra.com — not built

Confirmed Extra.com has a public, standard `sitemap.xml` (unlike Noon), which is a promising, cheap starting point (a legitimate/documented mechanism vs. reverse-engineered internals). Not pursued further this session due to time. **This is the most obvious next piece of work.**

---

## 4. Product Matching & Deduplication

`src/utils/product_matcher.py`. Given a flat list of raw listings from all platforms, groups them into "master SKUs" representing the same physical product.

**Spec extraction** (per listing, from title + any structured metadata available): brand, model name, model number, processor, RAM, storage, GPU, subtype (Gaming / 2-in-1 / Business / Chromebook / etc. via keyword rules), category (Laptop/Desktop, passed through from the scraper rather than inferred).

**Matching tiers** (checked in order, first match wins):
1. **Exact model number match** → score 1.0
2. **Weighted spec overlap** across `[brand, model_name, processor, ram, storage]` — score = (matching fields) / 5. If ≥ 0.8, treated as the same product.
3. **Fuzzy title similarity** (Python `difflib.SequenceMatcher`) on cleaned model names, ≥ 0.8 similarity → same product.

**Guard rail added this session**: products are never matched across `category` (a laptop can never merge with a desktop, even if specs happen to look similar) — this wasn't enforced before and could have caused silent wrong-merges.

**Known weakness in the scoring** (see §6.1 below) — the denominator for tier-2 scoring is always 5 regardless of how many of those 5 fields are actually populated on either listing. A listing missing 3 of 5 fields can never score above 0.4 even if the 2 comparable fields match perfectly, which pushes borderline cases into "no match" rather than "match" or even "similar." This directly affects gap-analysis accuracy (§5).

**Master SKU generation**: `{category}-{brand}-{model_name}-{cpu_family}-{ram}`, truncated to 40 chars, with a collision-suffix loop (`-2`, `-3`, ...) added this session after finding that two genuinely distinct products with identical-looking generated keys were silently overwriting each other in the results dict — a real bug in the original implementation, now fixed with a test-covered-by-inspection (not unit-tested formally).

---

## 5. Noon Assortment Gap Analysis (new feature)

`src/utils/gap_analyzer.py`. For every merged master product that appears on **at least one of** Amazon/Jarir/Extra ("the universe" — 434 products currently, since Extra isn't built yet this is really "Amazon + Jarir universe"), classifies its Noon status:

- **Exact Match** (148 products, 34.1%): the merge step already linked a Noon listing into this master SKU (same specs, tier 1 or 2 above).
- **Similar Available** (0 products, 0.0% — see caveat below): a second, looser pass compares the product against *every* raw Noon listing individually (not just ones that already merged), using the same scoring function but a lower bar (≥ 0.5 instead of ≥ 0.8). Currently returning zero hits.
- **Not Available** (286 products, 65.9%): no reasonable match found on Noon at all.

**Known issue, flagged directly for review**: the 0% "Similar" result is very likely an artifact of the scoring-denominator weakness in §4/§6.1, not a genuine finding that Noon's near-miss inventory is empty. A product with 2 of 5 comparable specs available, even if both match, scores 0.4 — below the 0.5 "similar" threshold — so it silently falls into "Not Available" instead. **This should be fixed before treating the 65.9% "not available" figure as reliable** — the true gap is probably smaller, with some fraction of that 65.9% actually being "similar" once the scoring denominator is normalized to only the fields present on both sides being compared. I did not fix this in the time available; recommend it as the first thing the next iteration addresses (see §9).

**Output**: `data/noon_gap_analysis.json`, a new "Noon Gap Analysis" sheet in the Excel export (colour-coded by status), and a new dashboard tab with filters (status, category) and a top-missing-brands chart.

---

## 6. Data Quality — current field coverage (604 merged products)

| Field | Coverage | Note |
|---|---|---|
| title | 100% | representative title carried through from the longest raw listing in each match group |
| category | 100% | passed through from scraper (known at scrape time), not inferred |
| subtype | 100% | keyword-rule classification, always assigns at least "Standard" |
| model_name | 98% | comma-split heuristic on title, falls back to keyword list |
| ram | 99% | |
| storage | 71% | |
| brand | 65% | |
| processor | 65% | |
| graphics_card | 47% | **see 6.2 — largely a real data limitation, not a bug** |

### 6.1 The scoring-denominator issue (affects matching quality broadly, not just gap analysis)

Described in §4/§5. `calculate_match_score()` always divides by 5 key spec fields regardless of how many are actually present on both listings being compared. Correct fix: divide by the count of fields present-and-comparable on **both** sides, not a fixed 5. This would make both the merge-matching (tier 2, §4) and the gap-analysis "similar" tier (§5) meaningfully more accurate. Flagged, not fixed — genuine risk of scope creep / new bugs if changed without re-validating the whole merge pipeline, and this was already a very long session.

### 6.2 Why GPU coverage is only 47%

Spot-checked: this is largely **real**, not a parsing failure. A large fraction of scraped listings are business/office laptops (Dell Latitude, HP EliteBook/ProBook, Lenovo ThinkPad) whose titles genuinely don't mention a discrete GPU because they ship with unspecified integrated graphics and the seller doesn't bother stating it. Gaming laptops and Apple products consistently do have GPU populated. Treat 47% as close to the practical ceiling for title-only extraction, not a target to push to 100% — closing the gap further would need scraping full product-detail pages (spec tables), which is a materially bigger scrape (one HTTP call per product instead of per page of ~50-100 products) and wasn't attempted this session.

### 6.3 Amazon's "list price" appearing before "Was:" price fluctuates in scraped runs

Not deeply investigated — Amazon's markdown output sometimes has the current price and struck-through original price adjacent with no reliable separator token beyond "Was:", and the regex takes the first plausible number. Spot checks looked correct but this wasn't systematically verified against the live site for a sample of products. Worth a dedicated QA pass before trusting "best price" claims in a business context.

---

## 7. What Wasn't Verified / Trust Boundaries

Being explicit about what I'm *not* claiming:

- **No automated tests exist.** Everything in this report was validated by spot-checking sample output (printing 5-10 products per stage, eyeballing) and cross-checking counts against independently-queried totals (e.g., Jarir's 28-desktop figure verified two different ways). There is no regression test suite — a future change to any regex or matching threshold could silently break things with no automated signal.
- **Gap analysis math (§5) has a known, unfixed accuracy issue** (the 0% "Similar" bucket). Don't present the 65.9% "not available" figure to stakeholders as final without addressing §6.1 first, or at minimum caveat it clearly.
- **Extra.com isn't in the dataset at all yet** — the "universe" in the gap analysis is really "Amazon + Jarir," not the full market. This changes the true gap percentage once added (likely upward, since Extra will add more products Noon doesn't carry — but this is a guess, not measured).
- **Jarir's Constructor.io key is an undocumented integration detail**, not a stable public contract. It could stop working without notice if Jarir rotates it or changes vendors.
- **Volume caps were time/cost tradeoffs for this session**, not hard ceilings: Amazon capped at 60/category (3 pages), Noon at 200/category (up to 12 pages) despite `nbHits` indicating 1,500+ available. Jarir has no artificial cap (scrapes until the API stops returning new results) since it's free/fast.

---

## 8. File/Module Map

```
src/scrapers/jarir_scraper.py    - Constructor.io API client (no Firecrawl)
src/scrapers/amazon_scraper.py   - Firecrawl markdown scrape + regex parse, &page=N pagination
src/scrapers/noon_scraper.py     - Firecrawl + proxy='stealth' + executeJavascript, TSR state extraction
src/utils/product_matcher.py     - spec extraction, tiered matching/dedup, master SKU generation
src/utils/gap_analyzer.py        - Noon exact/similar/not-available classification (new)
src/utils/excel_exporter.py      - openpyxl workbook: Raw Data / Price Comparison / Noon Gap Analysis sheets
main.py                          - orchestrates: scrape -> merge -> gap-analyze -> export -> (dashboard is separate)
dashboard.py                     - Streamlit app, 2 tabs (Price Comparison, Noon Gap), password-gated
```

---

## 9. Recommended Next Steps (priority order, my opinion)

1. **Fix the scoring-denominator issue (§6.1)** before trusting gap-analysis percentages for a real business decision — this is the highest-leverage, most contained fix (one function, `calculate_match_score`).
2. **Build Extra.com scraper** — sitemap.xml already confirmed present, likely the easiest of the remaining platforms.
3. **Add a lightweight regression check**: even just "assert merged product count > N" and "assert field-coverage % > threshold" run after each scrape, to catch a future silent breakage (e.g., Jarir's API key getting revoked) automatically rather than discovering it via a confused user report.
4. **Product-detail-page scraping for a GPU-coverage boost**, if GPU data specifically matters for the gap-analysis use case — bigger scrape, worth scoping deliberately rather than doing reflexively.
5. **Raise the Amazon/Noon volume caps** now that the mechanics are proven — this session's caps were about keeping iteration time reasonable, not a technical limit.
6. **Verify Amazon price extraction (§6.3)** against a real sample before relying on "best price" claims.

---

---

## 10. Addendum: Response to External Review (2026-07-31, same day)

This report was sent to the user for external AI review. The review was sharp and mostly correct; this addendum documents what changed as a direct result, written with the same candor as the rest of this document.

### What the reviewer got right, and what we did about it

- **Match-score denominator bug** (§6.1 above): confirmed and fixed. `calculate_match_score` now divides only by fields present on both sides being compared, not a fixed 5.
- **Non-transitive, order-dependent clustering**: confirmed and fixed. Replaced greedy first-match-wins merging with Union-Find over pairwise matches, so the transitive closure of matches (A~B, B~C ⇒ all three grouped) is taken properly instead of depending on input order.
- **Tier-3 fuzzy title matching being dangerous** ("Latitude 7430" vs "7440"): confirmed and fixed. Tier 3 is now gated behind brand + another spec agreeing, plus a numeric-model-token check that vetoes the match if both model names carry different distinguishing numbers.
- **Amazon accessory-title poisoning brand extraction**: confirmed - Amazon had no accessory filter (Jarir and Noon did). Added one.
- **No rate limiting**: added jittered delays across all three scrapers.
- **Gap analysis conflating "not scraped" with "not carried"**: correct and important, not something a code change alone fixes (needs bigger scrape volume + subtype segmentation, both still open - see §12 below).
- **Flat JSON / no history**: agreed as a real limitation for anything beyond a prototype; not addressed this round (out of scope for a same-day fix cycle), but the append-only `data/run_log.jsonl` added this round (see below) is a first, cheap step toward it.

### Two real bugs the review didn't catch, found while implementing its own recommendations

Fixing the denominator and adding transitive closure immediately surfaced two **existing** false-positive bugs that greedy matching had been silently absorbing:

1. `_extract_model_number`'s generic fallback regex (`[A-Z0-9]{6,}` between whitespace) was matching plain English words - "ThinkBook", "Windows" - as if they were model numbers. Two completely unrelated products that both happened to mention "ThinkBook" prominently would tier-1 "exact match" merge, at whatever wildly different prices they actually had.
2. The Mac-format model-number pattern (`[A-Z]\d{4}`) was matching inside screen-resolution strings - "1920**x1080**" parsed as model number "X1080". Every product mentioning that common resolution was at risk of merging with every other one.

Both were caught by manually inspecting multi-platform matches for price-spread sanity (a $900 product "matching" a $4,800 product is an obvious tell) after the transitive-closure change made the damage more visible/aggregated than greedy matching had. **This is worth flagging as a methodology point for the next reviewer**: neither of these would show up from reading the matching logic in isolation - they only surface by running it against real data and eyeballing outliers. No automated test would have caught them either, since there is no test suite (still true, still a real gap - see §9).

### A second-order bug the fix itself introduced (and fixed)

Requiring `model_name` to match, combined with now *preferring* each platform's own structured data (see next section) over regex-only extraction, immediately became too strict: Jarir's structured RAM field reads `"16 GB RAM"` while our own title-regex produces `"16GB"` - same value, different string, so exact-equality comparison silently failed almost every cross-platform pair. Added format-aware normalizers (`_normalize_capacity` for RAM/storage, `_processors_match` for processor SKUs with descriptive suffixes stripped, gated fuzzy comparison for `model_name`). Net effect on this dataset: multi-platform matches went 1 → 6, including two pairs with **identical prices across platforms** (strong external confirmation the match is correct, not coincidental).

### Data-quality fix independent of the review (direct user feedback)

The user separately reported missing model names/processors/RAM/storage despite the data "being right there in the title." Root cause: `merge_products()` called `extract_specs_from_title()` unconditionally for every product, which **discarded** whatever clean structured data a scraper had already attached (Jarir's Constructor.io metadata, Noon's `plp_specifications`) and replaced it with a fresh regex-only extraction from the title string. This is a real architectural bug, not a coverage gap - the good data existed and was being thrown away. Fixed: `extract_specs()` now prefers structured fields already on the product record and only falls back to title-regex for genuinely missing ones. Field coverage on the next run: brand 65%→94%, processor 65%→89%, storage 71%→90%, graphics_card 47%→65%.

### New this round

- **Extra.com scraper** (`src/scrapers/extra_scraper.py`): unlike Noon, Extra doesn't block plain HTTP or bot-detect headless browsers - it just needs a longer Firecrawl `wait_for` (6s) for the client-rendered product grid to hydrate. Parses by splitting markdown on each product card's boundary marker rather than a backward lookback-window from each product URL - the lookback approach was found to bleed adjacent products' prices into each other when cards were tightly packed (caught the same way as the matching bugs: price-sanity-checking the output).
- **Health checks + structured logging** (`src/utils/health_check.py`): distinguishes healthy / degraded / failed per platform per run. A platform returning ~zero products (both its primary method and any fallback failed) now raises and stops the pipeline loudly instead of silently shipping data missing an entire platform. A low-but-nonzero count (e.g. Jarir's markdown fallback, which only ever surfaces ~12-24 products) logs as degraded and the pipeline continues. Every run appends one JSON line to `data/run_log.jsonl` with platform counts, health status, field coverage, and merge stats - a first step toward the run-history the reviewer correctly noted doesn't exist yet.
- **Jarir markdown fallback**: if the Constructor.io key this integration depends on ever breaks, `jarir_scraper.py` now falls back to scraping the old curated-widget page rather than returning zero Jarir data outright. Degraded (≈12-24 products, not the full ≈345), but alive.
- **Live product search** (`src/utils/live_search.py`, new dashboard tab): user-requested feature, not from the review. Searches the existing scraped catalog instantly (free), plus an opt-in "Search Live" button that hits all four platforms' real search endpoints directly and shows raw results with prices/links - useful when the cached catalog doesn't have a specific item, or for checking current live price/stock.

### Numbers, before / after this round

| Metric | Before | After |
|---|---|---|
| Unique products | 604 (3 platforms) | 875 (4 platforms) |
| brand coverage | 65% | 94% |
| processor coverage | 65% | 89% |
| storage coverage | 71% | 90% |
| graphics_card coverage | 47% | 65% |
| Multi-platform matches | 261 (many verifiably wrong - 3-6x price spreads) | 6 (spot-checked correct, 2 with identical cross-platform prices) |
| Noon gap analysis | 148/434 exact match (34.1%) - **now known to include false-positive matches from the bugs above, so this figure was unreliable** | 22/487 exact match (4.5%) - lower, but each one verified plausible |

The multi-platform match count dropping sharply (261 → 6) while coverage/correctness went up is the point, not a regression: the 261 figure was inflated by the two false-positive bugs described above. 6 correctness-checked matches is a truer (if smaller) number than 261 partly-wrong ones. That said, 6 out of 875 is very low for what should be a meaningfully overlapping market (the same popular laptop models being sold on multiple sites) - see open item below.

### Still open (unchanged from original report unless noted)

1. **`similar_available` gap-analysis bucket still returns 0%.** Unclear if this is a residual scoring/threshold issue or a genuine finding that Noon's near-miss inventory (same brand, different config, not exact SKU) is empty in this sample. Not diagnosed further this round given time constraints - flagged, not fixed.
2. **Cross-platform match rate (6/875) seems low even accounting for the false-positive cleanup.** Worth investigating with fresh eyes whether platforms genuinely carry disjoint SKU sets in this sample, or whether matching is still too conservative somewhere not yet found.
3. **No automated test suite** - still true, and per this round's experience, the two false-positive bugs are a concrete argument for at least a small regression suite (a handful of known match/no-match pairs) rather than relying on manual price-sanity spot-checks after every change.
4. **Gap analysis "universe" still doesn't include Extra.com data in a validated way** - Extra was added this round but the gap analysis wasn't re-validated against it beyond the pipeline run completing without errors.
5. **Legal/compliance, repo privacy, SQLite migration, Excel summary sheet** - all still open exactly as stated in the original report; not addressed this round by explicit user decision (repo privacy) or scope (the rest).
6. **Brand casing inconsistency** noticed in passing (`"HP"` and `"Hp"` both appear as distinct entries in gap-analysis brand breakdowns) - cosmetic, not diagnosed or fixed.

*End of addendum.*

---

*End of report.*
