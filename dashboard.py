#!/usr/bin/env python3
"""
Saudi Laptop Price Comparison - Streamlit Dashboard
Lightweight, password-protected web interface for price comparison.
Deployable to Streamlit Community Cloud for access from any computer.
"""

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import os
import io

# Page config
st.set_page_config(
    page_title="SA Laptop Prices",
    page_icon="💻",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR = Path(__file__).parent


def get_secret(key: str, default: str = None):
    """Get config value from Streamlit secrets (cloud) or env var (local)."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


# ============= PASSWORD PROTECTION =============

def check_password():
    """Check if password is correct."""
    correct_password = get_secret("DASHBOARD_PASSWORD", "demo")

    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if not st.session_state.password_correct:
        st.text_input(
            "Enter password:",
            type="password",
            on_change=password_entered,
            key="passwd",
            placeholder=f"Hint: try '{correct_password}'" if correct_password == "demo" else ""
        )

        if st.session_state.get("password_correct") is False and "passwd" in st.session_state and st.session_state.passwd:
            st.error("❌ Wrong password")

        return False

    return True


def password_entered():
    """Callback for password input."""
    correct_password = get_secret("DASHBOARD_PASSWORD", "demo")
    st.session_state.password_correct = st.session_state.passwd == correct_password


# ============= DATA LOADING =============

def load_data():
    """Load merged products from JSON."""
    data_path = BASE_DIR / "data" / "merged_products.json"

    if not data_path.exists():
        return None

    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            products = json.load(f)
        return pd.DataFrame(products)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None


def get_latest_excel_path():
    """Find the most recently generated Excel report."""
    output_dir = BASE_DIR / "output"
    if not output_dir.exists():
        return None

    excel_files = sorted(output_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return excel_files[0] if excel_files else None


def load_gap_analysis():
    """Load Noon gap analysis results from JSON."""
    gap_path = BASE_DIR / "data" / "noon_gap_analysis.json"
    if not gap_path.exists():
        return None, None
    try:
        with open(gap_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return pd.DataFrame(data.get('rows', [])), data.get('summary', {})
    except Exception as e:
        st.error(f"Error loading gap analysis: {e}")
        return None, None


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Fallback: build a simple Excel file in-memory from the filtered dataframe."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Price Comparison')
    return buffer.getvalue()


# ============= MAIN APP =============

def main():
    """Main Streamlit app."""

    st.title("🌏 Saudi Laptop Price Comparison")
    st.markdown("Compare laptop & desktop prices across Amazon.sa, Jarir, Extra, & Noon")

    if not check_password():
        st.stop()

    # Load data
    df = load_data()

    if df is None or len(df) == 0:
        st.warning("📊 No data available yet. Run the scraper first: `python3 main.py`")
        st.info("""
        Steps to get started:
        1. Run: `python3 main.py`
        2. This will scrape products and generate data
        3. Refresh this page to see results
        """)
        return

    tab_prices, tab_gap, tab_search = st.tabs(
        ["📊 Price Comparison", "🎯 Noon Assortment Gap", "🔎 Product Search"]
    )

    with tab_prices:
        render_price_comparison(df)

    with tab_gap:
        render_gap_analysis()

    with tab_search:
        render_product_search(df)


def render_price_comparison(df):
    """Renders the price comparison table, filters, and downloads."""
    # Sidebar filters
    st.sidebar.markdown("## 🔍 Filters")

    # Category filter (Laptop / Desktop)
    if 'category' in df.columns:
        categories = ['All'] + sorted(df['category'].dropna().unique().tolist())
        selected_category = st.sidebar.selectbox("Category", categories)

        if selected_category != 'All':
            df = df[df['category'] == selected_category]

    # Subtype filter (Gaming / 2-in-1 / Business / etc.)
    if 'subtype' in df.columns:
        subtypes = ['All'] + sorted(df['subtype'].dropna().unique().tolist())
        selected_subtype = st.sidebar.selectbox("Subtype", subtypes)

        if selected_subtype != 'All':
            df = df[df['subtype'] == selected_subtype]

    # Brand filter
    brands = ['All'] + sorted(df['brand'].dropna().unique().tolist())
    selected_brand = st.sidebar.selectbox("Brand", brands)

    if selected_brand != 'All':
        df = df[df['brand'] == selected_brand]

    # AI classification filter
    if 'ai_classification' in df.columns:
        ai_options = ['All'] + sorted(df['ai_classification'].dropna().unique().tolist())
        selected_ai = st.sidebar.selectbox("AI Classification", ai_options)

        if selected_ai != 'All':
            df = df[df['ai_classification'] == selected_ai]

    # Price range filter
    if not df.empty and 'best_price' in df.columns:
        price_col = df['best_price'].dropna()
        if len(price_col) > 0:
            min_price, max_price = st.sidebar.slider(
                "Price Range (SAR)",
                float(price_col.min()),
                float(price_col.max()),
                (float(price_col.min()), float(price_col.max()))
            )
            df = df[(df['best_price'] >= min_price) & (df['best_price'] <= max_price)]

    # Platform availability filter
    platforms = st.sidebar.multiselect(
        "Available On",
        ["Amazon.sa", "Jarir", "Extra", "Noon"],
        default=["Amazon.sa", "Jarir", "Extra", "Noon"]
    )

    platform_cols = {
        "Amazon.sa": "amazon_sa_price",
        "Jarir": "jarir_price",
        "Extra": "extra_price",
        "Noon": "noon_price"
    }

    selected_cols = [platform_cols[p] for p in platforms if platform_cols.get(p) in df.columns]
    if selected_cols:
        df = df[df[selected_cols].notna().any(axis=1)]
    elif platforms == []:
        df = df.iloc[0:0]  # nothing selected -> show nothing

    # Main content area
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Products", len(df))

    with col2:
        if not df.empty and 'best_price' in df.columns:
            avg_price = df['best_price'].dropna().mean()
            st.metric("Average Price", f"SAR {avg_price:,.0f}" if pd.notna(avg_price) else "N/A")

    with col3:
        platforms_available = sum(1 for p in platforms if p in platform_cols and platform_cols[p] in df.columns and df[platform_cols[p]].notna().any())
        st.metric("Platforms", platforms_available)

    with col4:
        excel_path = get_latest_excel_path()
        if excel_path:
            last_updated = datetime.fromtimestamp(excel_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            st.metric("Last Updated", last_updated)

    # Display table
    st.markdown("## 📊 Price Comparison Table")

    if not df.empty:
        # Select columns to display
        display_cols = [
            'title', 'category', 'subtype', 'brand', 'model_name',
            'processor', 'processor_full', 'cpu_power', 'ram', 'storage',
            'graphics_card', 'ai_classification', 'npu_tops',
            'amazon_sa_price', 'jarir_price', 'extra_price', 'noon_price',
            'best_price', 'best_price_platform'
        ]

        column_labels = {
            'title': 'Title',
            'category': 'Category',
            'subtype': 'Subtype',
            'brand': 'Brand',
            'model_name': 'Model',
            'processor': 'Processor',
            'processor_full': 'Processor (Full)',
            'cpu_power': 'CPU Clock',
            'ram': 'RAM',
            'storage': 'Storage',
            'graphics_card': 'GPU',
            'ai_classification': 'AI',
            'npu_tops': 'NPU TOPS',
            'amazon_sa_price': 'Amazon.sa',
            'jarir_price': 'Jarir',
            'extra_price': 'Extra',
            'noon_price': 'Noon',
            'best_price': 'Best Price',
            'best_price_platform': 'Best On',
        }

        available_cols = [col for col in display_cols if col in df.columns]
        display_df = df[available_cols].copy()

        # Format price columns for display
        formatted_df = display_df.copy()
        for col in ['amazon_sa_price', 'jarir_price', 'extra_price', 'noon_price', 'best_price']:
            if col in formatted_df.columns:
                formatted_df[col] = formatted_df[col].apply(
                    lambda x: f"SAR {x:,.0f}" if pd.notna(x) else "N/A"
                )

        formatted_df = formatted_df.fillna('N/A')
        formatted_df = formatted_df.rename(columns=column_labels)

        st.dataframe(
            formatted_df,
            use_container_width=True,
            height=500
        )

        # ============= DOWNLOAD SECTION =============
        st.markdown("### 📥 Download Report")
        dl_col1, dl_col2, dl_col3 = st.columns([1, 1, 2])

        with dl_col1:
            excel_path = get_latest_excel_path()
            if excel_path:
                with open(excel_path, "rb") as f:
                    excel_bytes = f.read()
                st.download_button(
                    label="📊 Full Excel Report",
                    data=excel_bytes,
                    file_name=f"saudi_laptop_prices_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="Downloads the complete formatted Excel report (with Raw Data sheet)"
                )
            else:
                # Fallback: build Excel on-the-fly from filtered view
                excel_bytes = dataframe_to_excel_bytes(display_df)
                st.download_button(
                    label="📊 Excel (filtered view)",
                    data=excel_bytes,
                    file_name=f"laptop_prices_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        with dl_col2:
            csv = display_df.to_csv(index=False)
            st.download_button(
                label="📥 CSV",
                data=csv,
                file_name=f"laptop_prices_{datetime.now().strftime('%Y-%m-%d')}.csv",
                mime="text/csv"
            )

        with dl_col3:
            if st.button("🔄 Refresh Page"):
                st.rerun()

    else:
        st.info("No products match the selected filters.")

    # Info section
    st.markdown("---")
    st.markdown("### ℹ️ About")
    st.markdown("""
    - **Data Source**: Amazon.sa, Jarir.com, Noon.com, Extra.com
    - **Categories**: Laptops & Desktops
    - **Access this dashboard from any device** at this page's URL
    """)


def render_gap_analysis():
    """Renders the Noon assortment gap analysis view."""
    gap_df, summary = load_gap_analysis()

    if gap_df is None or len(gap_df) == 0:
        st.warning("📊 No gap analysis available yet. Run `python3 main.py` to generate it.")
        return

    st.markdown("## 🎯 Noon Assortment Gap Analysis")
    st.markdown(
        "Compares the full product universe (everything found on Amazon.sa, Jarir, and Extra) "
        "against Noon's catalog, to identify SKUs Noon is missing or only partially covers."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Universe Size", summary.get('total_universe_products', 0))
    with col2:
        st.metric("Exact Match on Noon", f"{summary.get('exact_match_count', 0)} ({summary.get('exact_match_pct', 0)}%)")
    with col3:
        st.metric("Similar Available", f"{summary.get('similar_available_count', 0)} ({summary.get('similar_available_pct', 0)}%)")
    with col4:
        st.metric("Missing from Noon", f"{summary.get('not_available_count', 0)} ({summary.get('not_available_pct', 0)}%)",
                  delta_color="inverse")

    # Missing-by-brand breakdown
    missing_by_brand = summary.get('missing_by_brand', {})
    if missing_by_brand:
        st.markdown("### 📉 Brand-Level Coverage")
        brand_df = pd.DataFrame(list(missing_by_brand.items()), columns=['Brand', 'Missing SKUs']).head(10)
        st.bar_chart(brand_df.set_index('Brand'))

    # Model-series level breakdown within a selected brand (e.g. ThinkPad
    # vs IdeaPad coverage within Lenovo, not just "Lenovo" as a whole)
    st.markdown("### 🔬 Model-Series Level Coverage")
    st.caption(
        "Pick a brand to see coverage broken down by model line/series - "
        "brand-level numbers can hide that one series is fully covered "
        "while another is completely missing."
    )

    brand_options = sorted(gap_df['brand'].dropna().unique().tolist()) if 'brand' in gap_df.columns else []
    if brand_options:
        selected_series_brand = st.selectbox("Brand", brand_options, key="series_brand_select")
        series_df = gap_df[gap_df['brand'] == selected_series_brand].copy()

        def _extract_series(model_name):
            if not model_name or not isinstance(model_name, str):
                return 'Unknown'
            first_word = model_name.split()[0] if model_name.split() else 'Unknown'
            return first_word

        series_df['series'] = series_df['model_name'].apply(_extract_series)

        series_summary = series_df.groupby(['series', 'noon_status']).size().unstack(fill_value=0)
        for status in ['Exact Match', 'Similar Available', 'Not Available']:
            if status not in series_summary.columns:
                series_summary[status] = 0
        series_summary = series_summary[['Exact Match', 'Similar Available', 'Not Available']]
        series_summary['Total'] = series_summary.sum(axis=1)
        series_summary = series_summary.sort_values('Total', ascending=False)

        st.bar_chart(series_summary[['Exact Match', 'Similar Available', 'Not Available']])
        st.dataframe(series_summary, use_container_width=True)
    else:
        st.info("No brand data available for series breakdown.")

    st.markdown("### 🔍 Filter")
    status_options = ['All', 'Not Available', 'Similar Available', 'Exact Match']
    selected_status = st.selectbox("Noon Status", status_options)

    filtered = gap_df.copy()
    if selected_status != 'All':
        filtered = filtered[filtered['noon_status'] == selected_status]

    if 'category' in filtered.columns:
        categories = ['All'] + sorted(filtered['category'].dropna().unique().tolist())
        selected_cat = st.selectbox("Category", categories, key="gap_category")
        if selected_cat != 'All':
            filtered = filtered[filtered['category'] == selected_cat]

    st.markdown(f"### 📋 Results ({len(filtered)} products)")

    display_cols = [
        'title', 'category', 'brand', 'model_name', 'processor', 'ram', 'storage',
        'available_on', 'best_price_elsewhere', 'noon_status',
        'noon_price', 'noon_similar_product', 'match_confidence'
    ]
    available_cols = [c for c in display_cols if c in filtered.columns]
    show_df = filtered[available_cols].copy().fillna('N/A')

    st.dataframe(show_df, use_container_width=True, height=500)

    csv = show_df.to_csv(index=False)
    st.download_button(
        label="📥 Download Gap Analysis (CSV)",
        data=csv,
        file_name=f"noon_gap_analysis_{datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv"
    )

    st.info(
        "**Exact Match**: Noon carries the identical SKU/spec combination.  \n"
        "**Similar Available**: Noon carries something close (same brand, overlapping specs) "
        "but not the exact SKU - a partial gap.  \n"
        "**Not Available**: No reasonable match found on Noon - a genuine assortment gap."
    )


def render_product_search(df):
    """Search for a specific product by title/model/brand/config.
    Step 1 searches the already-scraped catalog (instant, free). Step 2
    is an opt-in live search that hits each platform's real search
    endpoint directly - slower, and consumes Firecrawl credits for the
    platforms that need it (Amazon, Noon, Extra), so it only runs when
    the user explicitly asks for it."""
    st.markdown("## 🔎 Search for a Specific Product")
    st.markdown(
        "Type a title, model name, model number, or configuration (e.g. "
        "\"Dell Latitude 7440\", \"i7 16GB 512GB\", \"MacBook Air M5\")."
    )

    query = st.text_input("Search query", key="product_search_query", placeholder="e.g. ThinkPad T14 16GB")

    if not query:
        st.info("Enter a search term above to get started.")
        return

    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).parent / 'src'))
    from utils.live_search import search_local

    st.markdown("### 📚 Results from existing scraped data")
    local_results = search_local(query, df.to_dict('records'), max_results=30)

    if local_results:
        local_df = pd.DataFrame(local_results)
        display_cols = [
            'title', 'category', 'brand', 'model_name', 'processor', 'ram', 'storage',
            'amazon_sa_price', 'jarir_price', 'extra_price', 'noon_price', 'best_price'
        ]
        available_cols = [c for c in display_cols if c in local_df.columns]
        st.dataframe(local_df[available_cols].fillna('N/A'), use_container_width=True, height=350)
    else:
        st.warning("No matches in the existing scraped catalog.")

    st.markdown("---")
    st.markdown("### 🌐 Live Search (checks the actual websites right now)")
    st.caption(
        "Slower (10-30s) and uses live scraping credits - only runs when you click the button. "
        "Useful when the catalog above doesn't have what you're looking for, or you want "
        "current live prices/stock for a specific item."
    )

    if st.button("🔍 Search Live Across All Platforms"):
        with st.spinner(f"Searching Jarir, Amazon.sa, Noon, and Extra for \"{query}\"..."):
            from utils.live_search import search_live
            try:
                live_results = search_live(query, max_per_platform=5)
            except Exception as e:
                st.error(f"Live search failed: {e}")
                live_results = {}

        for platform, products in live_results.items():
            st.markdown(f"**{platform}** ({len(products)} results)")
            if products:
                rows = [{
                    'Title': p.get('raw_title', p.get('title', '')),
                    'Price (SAR)': p.get('price'),
                    'Link': p.get('product_url'),
                } for p in products]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, height=min(250, 50 + 35 * len(rows)))
            else:
                st.caption("No results.")


if __name__ == '__main__':
    main()
