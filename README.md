# 🌏 Saudi Arabia Laptop & Desktop Price Comparison System

A comprehensive web scraping system that automatically collects, merges, and visualizes laptop and desktop prices from multiple Saudi Arabian e-commerce platforms.

## 📊 Features

✅ **Multi-Platform Scraping**
- Amazon.sa
- Jarir.com (✓ Implemented)
- Extra.com
- Noon.com

✅ **Intelligent Product Matching**
- Exact SKU matching
- Brand + Model + Specs matching
- Fuzzy matching with 80%+ confidence threshold
- Automatic deduplication

✅ **Excel Export**
- Formatted comparison tables
- Color-coded pricing (best price in green, unavailable in red)
- Auto-filtering and frozen headers
- "Raw Data" sheet for reference

✅ **Web Dashboard**
- Password-protected Streamlit interface
- Sort/filter by brand, price range, platform availability
- One-click Excel export
- Responsive design

✅ **Automation**
- Scheduled scraping (every 12 hours)
- Price history tracking
- Price drop alerts (planned)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 2. Set Firecrawl API Key

```bash
export FIRECRAWL_API_KEY='your-key-here'
```

Or it will auto-load from `~/.zshrc` if already defined there.

### 3. Run the Full Pipeline

```bash
python3 main.py
```

This will:
1. Scrape all platforms
2. Merge duplicate products
3. Generate Excel file in `output/`
4. Display summary statistics

### 4. View the Web Dashboard

```bash
streamlit run dashboard.py
```

Then open http://localhost:8501 in your browser.

Default password: `demo`

## 📂 Project Structure

```
saudi-laptop-compare/
├── src/
│   ├── config/
│   │   └── config.py              # Global configuration
│   ├── scrapers/
│   │   └── jarir_scraper.py       # Jarir.com scraper (implemented)
│   │   └── amazon_scraper.py      # Amazon.sa scraper (template)
│   │   └── extra_scraper.py       # Extra.com scraper (template)
│   │   └── noon_scraper.py        # Noon.com scraper (template)
│   └── utils/
│       ├── firecrawl_helper.py    # Firecrawl API wrapper
│       ├── product_matcher.py     # Intelligent product matching
│       └── excel_exporter.py      # Excel file generator
│
├── data/                          # Raw scraped data (JSON)
├── output/                        # Generated Excel files
│
├── main.py                        # Main orchestration script
├── dashboard.py                   # Streamlit dashboard
├── test_jarir.py                  # Test Jarir scraper
├── inspect_html.py                # Debug HTML structure
│
└── requirements.txt               # Python dependencies
```

## 🔄 Pipeline Phases

### Phase 1: Data Extraction
Scrapes product listings from each platform, extracting:
- Title, Price, Original Price
- URL, Image, Rating, Review Count
- Availability status

**Status**: ✅ Jarir (11 laptops, pending desktops)

### Phase 2: Intelligent Matching
Matches identical products across platforms using:
1. **Tier 1**: Exact model number/SKU match
2. **Tier 2**: Brand + Model + Processor + RAM + Storage (80%+ match)
3. **Tier 3**: Fuzzy string matching on cleaned title

**Status**: ✅ Implemented, tested

### Phase 3: Excel Export
Creates formatted Excel file with:
- Master SKU for each unique product
- Specifications extracted from titles
- Platform-specific prices and links
- "Best Price" column (green highlight)
- "Raw Data" sheet for validation

**Status**: ✅ Implemented

### Phase 4: Web Dashboard
Streamlit interface with:
- Password-protected login
- Dynamic filtering (brand, price, platform)
- Sortable comparison table
- One-click CSV/Excel export
- Refresh button to re-scrape

**Status**: ✅ Ready to test

## 📋 Extracted Product Fields

For each product, the system captures:

| Field | Example | Source |
|-------|---------|--------|
| `master_sku` | LENOVO-IDEAPAD-SLIM-16GB | Generated |
| `brand` | Lenovo | Extracted from title |
| `model_name` | IdeaPad Slim 3 | Extracted from title |
| `processor` | Intel Core i5-1355U | Extracted from title |
| `ram` | 16GB | Extracted from title |
| `storage` | 512GB SSD | Extracted from title |
| `graphics_card` | Intel Iris Xe | Extracted from title |
| `amazon_sa_price` | 1999.00 | Scraped |
| `jarir_price` | 1799.00 | Scraped |
| `best_price` | 1799.00 | Calculated |
| `best_price_platform` | Jarir | Calculated |
| `last_updated` | 2026-07-27T... | Auto |

## 🛠️ Adding New Platforms

To add a new platform (e.g., Zid.sa):

1. **Create Scraper** (`src/scrapers/zid_scraper.py`):

```python
from utils.firecrawl_helper import FirecrawlHelper

class ZidScraper:
    def __init__(self):
        self.firecrawl = FirecrawlHelper(FIRECRAWL_API_KEY)
        self.platform_name = 'Zid.sa'
    
    def scrape_laptops(self):
        # Use firecrawl.scrape_page() to fetch content
        # Parse and return list of products
        pass
```

2. **Update Config** (`src/config/config.py`):

```python
PLATFORMS = {
    'zid': {
        'name': 'Zid.sa',
        'laptop_url': 'https://zid.sa/...',
        ...
    }
}
```

3. **Integrate in main.py**:

```python
def phase_1_scrape():
    # ... existing platforms ...
    zid = ZidScraper()
    zid_products = zid.scrape_all()
    all_products.extend(zid_products)
```

## 🔐 Security & Privacy

- **Firecrawl API Key**: Stored in `~/.zshrc` (not in code)
- **Dashboard**: Password-protected (default: `demo` for testing)
- **Data**: Scraped data is locally stored, never sent to third parties
- **Rate Limiting**: Respects platform robots.txt via Firecrawl

## 📊 Output Files

- **`output/saudi_laptop_prices_2026-07-27_14-30-45.xlsx`**
  - Main comparison spreadsheet
  - Formatted with colors, filtering, frozen headers

- **`data/raw_products.json`**
  - Unprocessed data from all platforms
  - Useful for debugging/validation

- **`data/merged_products.json`**
  - Deduplicated products with master SKUs
  - Ready for analysis or further processing

## 🔍 Troubleshooting

### No products scraped?

1. Check Firecrawl API key:
   ```bash
   echo $FIRECRAWL_API_KEY
   ```

2. Check internet connection:
   ```bash
   curl https://www.jarir.com/sa-en/computers-laptops/laptops
   ```

3. Inspect HTML structure:
   ```bash
   python3 inspect_html.py
   ```

### Excel file not generated?

- Check `output/` directory exists
- Verify `openpyxl` is installed: `python3 -m pip install openpyxl`
- Check disk space

### Dashboard won't start?

```bash
python3 -m pip install streamlit
streamlit run dashboard.py
```

## 📈 Next Steps

1. **Expand Platform Coverage**
   - Implement Amazon.sa, Extra.com, Noon.com scrapers
   - Test matching logic across platforms

2. **Enhance Price Tracking**
   - Store historical prices in SQLite
   - Generate price trend charts

3. **Smart Notifications**
   - Email/Slack alerts for price drops
   - Configurable thresholds per product

4. **Performance Optimization**
   - Parallel scraping with asyncio
   - Redis caching for faster dashboard loads

5. **Analytics Dashboard**
   - Average prices by brand
   - Availability heatmaps
   - Market share analysis

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review logs in `output/` and `data/`
3. Run `inspect_html.py` to debug scraper issues

## 📄 License

This project is for educational purposes. Always respect platform terms of service and robots.txt.

---

**Last Updated**: 2026-07-27  
**Status**: Phase 1-3 Complete, Phase 4 Ready for Testing
