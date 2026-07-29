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

    # Sidebar filters
    st.sidebar.markdown("## 🔍 Filters")

    # Brand filter
    brands = ['All'] + sorted(df['brand'].dropna().unique().tolist())
    selected_brand = st.sidebar.selectbox("Brand", brands)

    if selected_brand != 'All':
        df = df[df['brand'] == selected_brand]

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

    for platform, col in platform_cols.items():
        if col in df.columns:
            if platform not in platforms:
                df = df[df[col].isna()]
            else:
                df = df[df[col].notna()]

    # Main content area
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Products", len(df))

    with col2:
        if not df.empty and 'best_price' in df.columns:
            avg_price = df['best_price'].dropna().mean()
            st.metric("Average Price", f"₪{avg_price:,.0f}" if pd.notna(avg_price) else "N/A")

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
            'brand', 'model_name', 'processor', 'ram', 'storage',
            'amazon_sa_price', 'jarir_price', 'extra_price', 'noon_price',
            'best_price', 'best_price_platform'
        ]

        available_cols = [col for col in display_cols if col in df.columns]
        display_df = df[available_cols].copy()

        # Format price columns for display
        formatted_df = display_df.copy()
        for col in ['amazon_sa_price', 'jarir_price', 'extra_price', 'noon_price', 'best_price']:
            if col in formatted_df.columns:
                formatted_df[col] = formatted_df[col].apply(
                    lambda x: f"₪{x:,.0f}" if pd.notna(x) else "N/A"
                )

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
    - **Data Source**: Amazon.sa, Jarir.com, Extra.com, Noon.com
    - **Categories**: Laptops & Desktops
    - **Access this dashboard from any device** at this page's URL
    """)


if __name__ == '__main__':
    main()
