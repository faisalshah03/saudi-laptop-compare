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


def inject_css():
    """Injects custom CSS for a distinct visual identity - a data/analyst
    tool feel (deep teal/navy, custom icon KPI cards, underline tabs)
    rather than a generic indigo SaaS-gradient look."""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

        :root {
            --ink: #0B1220;
            --muted: #64748B;
            --canvas: #F4F6F7;
            --card: #FFFFFF;
            --border: #E2E8ED;
            --teal: #0F766E;
            --teal-light: #14B8A6;
            --amber: #D97706;
            --blue: #2563EB;
            --rose: #E11D48;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        [data-testid="stAppViewContainer"] > .main {
            background: var(--canvas);
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        /* Hero header - deep teal/navy instead of indigo-purple gradient,
        with a subtle dot-grid texture and a live-status pill */
        .hero-banner {
            position: relative;
            background: linear-gradient(135deg, #0B3B36 0%, #0F766E 55%, #115E59 100%);
            background-image:
                radial-gradient(circle at 1px 1px, rgba(255,255,255,0.09) 1px, transparent 0),
                linear-gradient(135deg, #0B3B36 0%, #0F766E 55%, #115E59 100%);
            background-size: 18px 18px, 100% 100%;
            border-radius: 18px;
            padding: 1.75rem 2rem;
            margin-bottom: 1.75rem;
            box-shadow: 0 10px 30px rgba(15, 118, 110, 0.28);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
        }
        .hero-banner h1 {
            color: #FFFFFF;
            font-size: 1.6rem;
            font-weight: 800;
            margin: 0 0 0.3rem 0;
            letter-spacing: -0.02em;
        }
        .hero-banner p {
            color: rgba(255, 255, 255, 0.82);
            font-size: 0.92rem;
            margin: 0;
            font-weight: 500;
        }
        .hero-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.22);
            color: #E6FFFA;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            padding: 6px 12px;
            border-radius: 999px;
            white-space: nowrap;
        }
        .hero-badge .dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #34D399;
            box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.25);
        }

        /* Custom KPI cards (replaces st.metric for full icon/accent control) */
        .kpi-card {
            display: flex;
            align-items: center;
            gap: 0.85rem;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1rem 1.1rem;
            box-shadow: 0 1px 2px rgba(15, 23, 32, 0.04);
            transition: box-shadow 0.15s ease, transform 0.15s ease;
        }
        .kpi-card:hover {
            box-shadow: 0 8px 20px rgba(15, 23, 32, 0.08);
            transform: translateY(-2px);
        }
        .kpi-icon {
            flex: none;
            width: 42px;
            height: 42px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
        }
        .kpi-label {
            font-size: 0.76rem;
            font-weight: 600;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.03em;
            margin-bottom: 0.15rem;
        }
        .kpi-value {
            font-size: 1.35rem;
            font-weight: 800;
            color: var(--ink);
            font-family: 'JetBrains Mono', 'Inter', monospace;
            line-height: 1.1;
        }

        /* Tabs - underline indicator instead of pill segmented control */
        .stTabs [data-baseweb="tab-list"] {
            gap: 1.5rem;
            background: transparent;
            border-bottom: 2px solid var(--border);
            padding: 0;
        }
        .stTabs [data-baseweb="tab"] {
            font-weight: 600;
            color: var(--muted);
            padding: 0.6rem 0.1rem;
            background: transparent;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
        }
        .stTabs [aria-selected="true"] {
            background: transparent !important;
            color: var(--teal) !important;
            border-bottom: 2px solid var(--teal) !important;
            box-shadow: none;
        }

        /* Sidebar */
        [data-testid="stSidebar"] {
            background: #FBFCFC;
            border-right: 1px solid var(--border);
        }
        [data-testid="stSidebar"] h2 {
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--ink);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 2px solid var(--teal);
            padding-bottom: 0.4rem;
            display: inline-block;
        }
        [data-testid="stSidebar"] label p {
            font-size: 0.82rem;
            font-weight: 600;
            color: var(--muted);
        }

        /* Buttons */
        .stButton button, .stDownloadButton button {
            border-radius: 9px;
            font-weight: 600;
            border: 1px solid var(--border);
            transition: all 0.15s ease;
        }
        .stButton button:hover, .stDownloadButton button:hover {
            border-color: var(--teal);
            color: var(--teal);
        }

        /* Dataframe / table container */
        [data-testid="stDataFrame"] {
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid var(--border);
        }

        /* Section headings */
        h2, h3 {
            font-weight: 700;
            letter-spacing: -0.01em;
            color: var(--ink);
        }

        /* Info/warning/error boxes */
        .stAlert {
            border-radius: 10px;
        }
    </style>
    """, unsafe_allow_html=True)


def kpi_card(icon: str, label: str, value: str, accent: str = "#0F766E"):
    """Renders a custom icon KPI card (replaces st.metric for design control)."""
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon" style="background:{accent}1A; color:{accent};">{icon}</div>
        <div>
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


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


def load_gap_analyses():
    """Load all cross-platform gap analysis comparisons from JSON.
    Returns a dict of {key: {'rows': DataFrame, 'summary': dict}} for
    each of universe/jarir/extra/amazon_sa vs Noon."""
    gap_path = BASE_DIR / "data" / "gap_analyses.json"
    if not gap_path.exists():
        return None
    try:
        with open(gap_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            key: {'rows': pd.DataFrame(val.get('rows', [])), 'summary': val.get('summary', {})}
            for key, val in data.items()
        }
    except Exception as e:
        st.error(f"Error loading gap analyses: {e}")
        return None


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Fallback: build a simple Excel file in-memory from the filtered dataframe."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Price Comparison')
    return buffer.getvalue()


# ============= MAIN APP =============

def main():
    """Main Streamlit app."""

    inject_css()

    st.markdown("""
    <div class="hero-banner">
        <div>
            <h1>💻 Saudi Laptop Price Comparison</h1>
            <p>Compare laptop &amp; desktop prices across Amazon.sa, Jarir, Extra, &amp; Noon</p>
        </div>
        <span class="hero-badge"><span class="dot"></span>Live Data</span>
    </div>
    """, unsafe_allow_html=True)

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

    # Condition filter (New / Renewed / Refurbished / Open Box / Used)
    if 'condition' in df.columns:
        condition_options = ['All'] + sorted(df['condition'].dropna().unique().tolist())
        selected_condition = st.sidebar.selectbox("Condition", condition_options)

        if selected_condition != 'All':
            df = df[df['condition'] == selected_condition]

    # Processor filter
    if 'processor' in df.columns:
        processor_options = ['All'] + sorted(df['processor'].dropna().unique().tolist())
        selected_processor = st.sidebar.selectbox("Processor", processor_options)

        if selected_processor != 'All':
            df = df[df['processor'] == selected_processor]

    # RAM filter
    if 'ram' in df.columns:
        ram_options = ['All'] + sorted(df['ram'].dropna().unique().tolist(), key=lambda x: str(x))
        selected_ram = st.sidebar.selectbox("RAM", ram_options)

        if selected_ram != 'All':
            df = df[df['ram'] == selected_ram]

    # Storage filter
    if 'storage' in df.columns:
        storage_options = ['All'] + sorted(df['storage'].dropna().unique().tolist(), key=lambda x: str(x))
        selected_storage = st.sidebar.selectbox("Storage", storage_options)

        if selected_storage != 'All':
            df = df[df['storage'] == selected_storage]

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
        kpi_card("📦", "Total Products", f"{len(df):,}", accent="#0F766E")

    with col2:
        avg_display = "N/A"
        if not df.empty and 'best_price' in df.columns:
            avg_price = df['best_price'].dropna().mean()
            avg_display = f"SAR {avg_price:,.0f}" if pd.notna(avg_price) else "N/A"
        kpi_card("💰", "Average Price", avg_display, accent="#D97706")

    with col3:
        platforms_available = sum(1 for p in platforms if p in platform_cols and platform_cols[p] in df.columns and df[platform_cols[p]].notna().any())
        kpi_card("🌐", "Platforms", str(platforms_available), accent="#2563EB")

    with col4:
        excel_path = get_latest_excel_path()
        last_updated = "N/A"
        if excel_path:
            last_updated = datetime.fromtimestamp(excel_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        kpi_card("🕒", "Last Updated", last_updated, accent="#7C3AED")

    # Display table
    st.markdown("## 📊 Price Comparison Table")

    if not df.empty:
        # Select columns to display
        display_cols = [
            'title', 'category', 'subtype', 'condition', 'brand', 'model_name', 'model_number',
            'manufacturer_number', 'processor', 'processor_full', 'cpu_power', 'ram', 'storage',
            'graphics_card', 'ai_classification', 'npu_tops',
            'amazon_sa_price', 'amazon_sa_link',
            'jarir_price', 'jarir_link',
            'extra_price', 'extra_link',
            'noon_price', 'noon_link',
            'best_price', 'best_price_platform'
        ]

        link_cols = ['amazon_sa_link', 'jarir_link', 'extra_link', 'noon_link']

        column_labels = {
            'title': 'Title',
            'category': 'Category',
            'subtype': 'Subtype',
            'condition': 'Condition',
            'brand': 'Brand',
            'model_name': 'Model',
            'model_number': 'Model Number',
            'manufacturer_number': 'Manufacturer Number',
            'processor': 'Processor',
            'processor_full': 'Processor (Full)',
            'cpu_power': 'CPU Clock',
            'ram': 'RAM',
            'storage': 'Storage',
            'graphics_card': 'GPU',
            'ai_classification': 'AI',
            'npu_tops': 'NPU TOPS',
            'amazon_sa_price': 'Amazon.sa',
            'amazon_sa_link': 'Amazon.sa Link',
            'jarir_price': 'Jarir',
            'jarir_link': 'Jarir Link',
            'extra_price': 'Extra',
            'extra_link': 'Extra Link',
            'noon_price': 'Noon',
            'noon_link': 'Noon Link',
            'best_price': 'Best Price',
            'best_price_platform': 'Best On',
        }

        available_cols = [col for col in display_cols if col in df.columns]
        display_df = df[available_cols].copy().reset_index(drop=True)

        # Format price columns for display
        formatted_df = display_df.copy()
        for col in ['amazon_sa_price', 'jarir_price', 'extra_price', 'noon_price', 'best_price']:
            if col in formatted_df.columns:
                formatted_df[col] = formatted_df[col].apply(
                    lambda x: f"SAR {x:,.0f}" if pd.notna(x) else "N/A"
                )

        # Link columns stay as raw URLs (or NaN) for st.column_config.LinkColumn
        # to render as clickable - fillna('N/A') would make them invalid links.
        non_link_cols = [c for c in formatted_df.columns if c not in link_cols]
        formatted_df[non_link_cols] = formatted_df[non_link_cols].fillna('N/A')
        formatted_df = formatted_df.rename(columns=column_labels)

        link_column_config = {
            column_labels[c]: st.column_config.LinkColumn(column_labels[c], display_text="🔗 Open")
            for c in link_cols if c in display_df.columns
        }

        st.caption("👆 Click on a row to get one-click links to that product on each platform (the link cells in the table need two clicks - select the cell, then click its small icon).")

        table_event = st.dataframe(
            formatted_df,
            use_container_width=True,
            height=500,
            column_config=link_column_config,
            on_select="rerun",
            selection_mode="single-row",
            key="price_comparison_table"
        )

        selected_rows = table_event.get("selection", {}).get("rows", []) if table_event else []
        if selected_rows:
            row = display_df.iloc[selected_rows[0]]
            with st.container(border=True):
                st.markdown(f"**Selected: {row.get('title', 'Untitled')}**")
                link_row_cols = st.columns(4)
                platform_defs = [
                    ('Amazon.sa', 'amazon_sa_price', 'amazon_sa_link'),
                    ('Jarir', 'jarir_price', 'jarir_link'),
                    ('Extra', 'extra_price', 'extra_link'),
                    ('Noon', 'noon_price', 'noon_link'),
                ]
                for col, (label, price_key, link_key) in zip(link_row_cols, platform_defs):
                    with col:
                        price = row.get(price_key)
                        link = row.get(link_key)
                        if isinstance(link, str) and link:
                            has_price = price is not None and pd.notna(price)
                            text = f"{label} · SAR {price:,.0f}" if has_price else f"Open on {label}"
                            st.link_button(text, link, use_container_width=True)
                        else:
                            st.caption(f"{label}: N/A")

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
    """Renders the cross-platform assortment gap analysis view, with a
    selector for which base platform to compare against Noon."""
    comparisons = load_gap_analyses()

    if not comparisons:
        st.warning("📊 No gap analysis available yet. Run `python3 main.py` to generate it.")
        return

    st.markdown("## 🎯 Assortment Gap Analysis (vs Noon)")

    comparison_options = {
        'universe': 'Universe (Amazon.sa + Jarir + Extra combined) vs Noon',
        'jarir': 'Jarir vs Noon',
        'extra': 'Extra vs Noon',
        'amazon_sa': 'Amazon.sa vs Noon',
    }
    available_keys = [k for k in comparison_options if k in comparisons and len(comparisons[k]['rows']) > 0]

    if not available_keys:
        st.warning("No comparison data available.")
        return

    selected_key = st.selectbox(
        "Comparison", available_keys, format_func=lambda k: comparison_options[k]
    )

    gap_df = comparisons[selected_key]['rows']
    summary = comparisons[selected_key]['summary']
    base_label = 'Universe' if selected_key == 'universe' else comparison_options[selected_key].split(' vs')[0]

    st.markdown(
        f"Compares **{base_label}**'s products against Noon's catalog, to identify SKUs "
        f"Noon is missing or only partially covers."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi_card("📚", f"{base_label} Size", f"{summary.get('total_base_products', 0):,}", accent="#0F766E")
    with col2:
        kpi_card("✅", "Exact Match on Noon", f"{summary.get('exact_match_count', 0)} ({summary.get('exact_match_pct', 0)}%)", accent="#2563EB")
    with col3:
        kpi_card("🟡", "Similar Available", f"{summary.get('similar_available_count', 0)} ({summary.get('similar_available_pct', 0)}%)", accent="#D97706")
    with col4:
        kpi_card("⚠️", "Missing from Noon", f"{summary.get('not_available_count', 0)} ({summary.get('not_available_pct', 0)}%)", accent="#E11D48")

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

        series_summary = series_df.groupby(['series', 'compare_status']).size().unstack(fill_value=0)
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
    selected_status = st.selectbox("Noon Status", status_options, key="gap_status_select")

    filtered = gap_df.copy()
    if selected_status != 'All':
        filtered = filtered[filtered['compare_status'] == selected_status]

    if 'category' in filtered.columns:
        categories = ['All'] + sorted(filtered['category'].dropna().unique().tolist())
        selected_cat = st.selectbox("Category", categories, key="gap_category")
        if selected_cat != 'All':
            filtered = filtered[filtered['category'] == selected_cat]

    st.markdown(f"### 📋 Results ({len(filtered)} products)")

    display_cols = [
        'title', 'category', 'brand', 'model_name', 'processor', 'processor_full',
        'ram', 'storage', 'graphics_card', 'ai_classification',
        'available_on', 'base_price', 'base_link', 'compare_status',
        'compare_price', 'compare_link', 'compare_similar_product', 'match_confidence'
    ]
    available_cols = [c for c in display_cols if c in filtered.columns]
    show_df = filtered[available_cols].copy().reset_index(drop=True)

    # Format price columns to strings BEFORE fillna - fillna('N/A') on a
    # raw numeric column leaves a MIXED float/string column (real prices
    # stay as floats, only the NaN cells become the string 'N/A'), which
    # crashes Streamlit's PyArrow serialization entirely
    # (ArrowTypeError: "Expected bytes, got a 'float' object") the
    # moment this table renders - this took the live app down on every
    # visit to this tab since the row-selection change was deployed.
    for price_col in ('base_price', 'compare_price'):
        if price_col in show_df.columns:
            show_df[price_col] = show_df[price_col].apply(
                lambda x: f"SAR {x:,.0f}" if pd.notna(x) else "N/A"
            )

    gap_link_cols = [c for c in ('base_link', 'compare_link') if c in show_df.columns]
    non_link_cols = [c for c in show_df.columns if c not in gap_link_cols]
    show_df[non_link_cols] = show_df[non_link_cols].fillna('N/A')

    st.caption("👆 Click on a row to get one-click links to that product.")

    gap_table_event = st.dataframe(
        show_df,
        use_container_width=True,
        height=500,
        column_config={
            'base_link': st.column_config.LinkColumn('base_link', display_text="🔗 Open"),
            'compare_link': st.column_config.LinkColumn('compare_link', display_text="🔗 Open"),
        },
        on_select="rerun",
        selection_mode="single-row",
        key="gap_analysis_table"
    )

    gap_selected_rows = gap_table_event.get("selection", {}).get("rows", []) if gap_table_event else []
    if gap_selected_rows:
        row = show_df.iloc[gap_selected_rows[0]]
        with st.container(border=True):
            st.markdown(f"**Selected: {row.get('title', 'Untitled')}**")
            link_row_cols = st.columns(2)
            for col, (label, link_key) in zip(link_row_cols, [('Base Platform', 'base_link'), ('Compare Platform (Noon)', 'compare_link')]):
                with col:
                    link = row.get(link_key)
                    if isinstance(link, str) and link:
                        st.link_button(f"Open on {label}", link, use_container_width=True)
                    else:
                        st.caption(f"{label}: N/A")

    csv = show_df.to_csv(index=False)
    st.download_button(
        label="📥 Download Gap Analysis (CSV)",
        data=csv,
        file_name=f"gap_analysis_{selected_key}_{datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
        key="gap_csv_download"
    )

    st.info(
        "**Exact Match**: Noon carries the identical SKU/spec combination.  \n"
        "**Similar Available**: Noon carries something close (same brand, overlapping specs) "
        "but not the exact SKU - a partial gap.  \n"
        "**Not Available**: No reasonable match found on Noon - a genuine assortment gap."
    )


def _render_product_card(p: dict):
    """Renders one search result as a compact single-line list row
    (title/specs on the left, one real one-click st.link_button per
    platform on the right) rather than a full bordered card, so a page
    of 30 results reads as a scannable list, not a stack of boxes.
    st.dataframe's LinkColumn technically supports links, but requires
    clicking into the cell first to reveal a small link icon before it
    opens - confusing/easy to miss, especially on Streamlit Cloud.
    st.link_button is a genuine single-click anchor."""
    title_col, amazon_col, jarir_col, extra_col, noon_col = st.columns([3, 1, 1, 1, 1])

    with title_col:
        st.markdown(f"**{p.get('title', 'Untitled')}**")
        specs = ' · '.join(str(v) for v in [p.get('brand'), p.get('processor'), p.get('ram'), p.get('storage')] if v)
        condition = p.get('condition')
        if condition and condition != 'New':
            specs = f"{specs} · 🔄 {condition}" if specs else f"🔄 {condition}"
        if specs:
            st.caption(specs)

    platforms = [
        (amazon_col, 'Amazon.sa', p.get('amazon_sa_price'), p.get('amazon_sa_link')),
        (jarir_col, 'Jarir', p.get('jarir_price'), p.get('jarir_link')),
        (extra_col, 'Extra', p.get('extra_price'), p.get('extra_link')),
        (noon_col, 'Noon', p.get('noon_price'), p.get('noon_link')),
    ]
    for col, label, price, link in platforms:
        with col:
            # link/price can come back as float NaN (not None) once a
            # column has passed through a DataFrame with an all-missing
            # subset - `if link:` alone is True for NaN, which then
            # crashes st.link_button expecting a URL string.
            has_link = isinstance(link, str) and link
            if has_link:
                has_price = price is not None and pd.notna(price)
                text = f"SAR {price:,.0f}" if has_price else "Open"
                st.link_button(text, link, use_container_width=True)
            else:
                st.caption(f"{label}: N/A")

    st.divider()


def render_product_search(df):
    """Search for a specific product by title/model/brand/config.
    Step 1 searches the already-scraped catalog (instant, free). Step 2
    is an opt-in live search that hits each platform's real search
    endpoint directly - slower, and consumes Firecrawl credits for the
    platforms that need it (Amazon, Noon, Extra), so it only runs when
    the user explicitly asks for it."""
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).parent / 'src'))

    st.markdown("## 🔎 Search for a Specific Product")
    st.markdown(
        "Narrow by brand/spec below for an exact match within that brand, or leave them "
        "on **All** and just type free text to browse across brands (e.g. \"i7 16GB 512GB\")."
    )

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
    with filter_col1:
        brand_choices = ['All'] + sorted(df['brand'].dropna().unique().tolist()) if 'brand' in df.columns else ['All']
        search_brand = st.selectbox("Brand", brand_choices, key="search_brand_select")
    with filter_col2:
        ram_choices = ['All'] + sorted(df['ram'].dropna().unique().tolist(), key=lambda x: str(x)) if 'ram' in df.columns else ['All']
        search_ram = st.selectbox("RAM", ram_choices, key="search_ram_select")
    with filter_col3:
        storage_choices = ['All'] + sorted(df['storage'].dropna().unique().tolist(), key=lambda x: str(x)) if 'storage' in df.columns else ['All']
        search_storage = st.selectbox("Storage", storage_choices, key="search_storage_select")
    with filter_col4:
        processor_choices = ['All'] + sorted(df['processor'].dropna().unique().tolist()) if 'processor' in df.columns else ['All']
        search_processor = st.selectbox("Processor", processor_choices, key="search_processor_select")

    query = st.text_input(
        "Search text (optional if using the dropdowns above)",
        key="product_search_query",
        placeholder="e.g. M5 Max 48GB, ThinkPad T14, i7 16GB 512GB"
    )

    st.markdown("---")
    st.markdown("## 🔍 Search the Catalog")

    no_filters_set = all(v == 'All' for v in (search_brand, search_ram, search_storage, search_processor))
    local_results = []

    if not query and no_filters_set:
        st.info("Enter a search term or pick a brand/spec filter above to get started.")
    else:
        from utils.live_search import search_local

        st.markdown("### 📚 Results from existing scraped data")
        local_results = search_local(
            query, df.to_dict('records'), max_results=30,
            brand=search_brand, ram=search_ram, storage=search_storage, processor=search_processor
        )

        if local_results:
            header_cols = st.columns([3, 1, 1, 1, 1])
            with header_cols[0]:
                st.caption("PRODUCT")
            for col, label in zip(header_cols[1:], ["Amazon.sa", "Jarir", "Extra", "Noon"]):
                with col:
                    st.caption(label.upper())
            for p in local_results:
                _render_product_card(p)
        else:
            st.warning("No matches in the existing scraped catalog.")

        st.markdown("---")
        st.markdown("### 🌐 Live Search (checks the actual websites right now)")
        st.caption(
            "Slower (10-30s) and uses live scraping credits - only runs when you click the button. "
            "Useful when the catalog above doesn't have what you're looking for, or you want "
            "current live prices/stock for a specific item."
        )

        live_query = query.strip() or ' '.join(
            v for v in (search_brand, search_processor, search_ram, search_storage) if v and v != 'All'
        )

        if not local_results:
            st.info("Not in our existing catalog? Search the 4 sites live right now:")

        if st.button(
            "🔍 Search Live Across All Platforms",
            disabled=not live_query,
            type="primary" if not local_results else "secondary"
        ):
            with st.spinner(f"Searching Jarir, Amazon.sa, Noon, and Extra for \"{live_query}\"..."):
                from utils.live_search import search_live
                try:
                    live_results = search_live(live_query, max_per_platform=5)
                except Exception as e:
                    st.error(f"Live search failed: {e}")
                    live_results = {}

            for platform, products in live_results.items():
                st.markdown(f"**{platform}** ({len(products)} results)")
                if products:
                    for p in products:
                        price = p.get('price')
                        label = p.get('raw_title', p.get('title', 'View product'))
                        if price and pd.notna(price):
                            label = f"SAR {price:,.0f} · {label}"
                        url = p.get('product_url')
                        if url:
                            st.link_button(label[:90], url, use_container_width=True)
                        else:
                            st.caption(label)
                else:
                    st.caption("No results.")

    st.markdown("---")
    st.markdown("### 📎 Check a Specific Product Link")
    st.caption(
        "Found a SKU on Amazon.sa, Jarir, Extra, or Noon that isn't in the catalog above "
        "(e.g. missed by the last scrape/refresh)? Paste its product page link(s) below - "
        "one per line - and we'll fetch the price directly."
    )

    pasted_urls = st.text_area(
        "Product link(s), one per line",
        key="pasted_product_urls",
        placeholder="https://www.jarir.com/sa-en/...\nhttps://www.amazon.sa/dp/...",
        height=100
    )

    if st.button("📎 Check These Links", key="check_links_button", disabled=not pasted_urls.strip()):
        urls = [u.strip() for u in pasted_urls.splitlines() if u.strip()]
        with st.spinner(f"Checking {len(urls)} link(s)..."):
            from utils.live_search import check_product_urls
            try:
                link_results = check_product_urls(urls)
            except Exception as e:
                st.error(f"Link check failed: {e}")
                link_results = []

        for entry in link_results:
            with st.container(border=True):
                title = entry.get('title') or '(title not detected)'
                st.markdown(f"**{title}**")
                st.caption(f"Platform: {entry.get('platform', 'Unknown')}")

                price = entry.get('price')
                label = f"Open · SAR {price:,.0f}" if price else "Open Product Page"
                st.link_button(label, entry['url'], use_container_width=False)

                if entry.get('error'):
                    st.caption(f"⚠️ {entry['error']}")


if __name__ == '__main__':
    main()
