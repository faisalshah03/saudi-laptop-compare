#!/usr/bin/env python3
"""
FastAPI backend for Saudi Laptop Price Comparison System
Provides REST API for scraping, data access, and file downloads
Deployable to Railway, Render, Heroku, etc.
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Setup path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.config import FIRECRAWL_API_KEY, OUTPUT_DIR, DATA_DIR
from scrapers.jarir_scraper import JarirScraper
from utils.product_matcher import ProductMatcher
from utils.excel_exporter import ExcelExporter

# Initialize FastAPI
app = FastAPI(
    title="Saudi Laptop Price Comparison API",
    description="REST API for laptop price scraping and comparison",
    version="1.0.0"
)

# Enable CORS for web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
last_scrape = None
scraping_in_progress = False


# ============= MODELS =============
class ScrapeRequest(BaseModel):
    """Request to trigger scraping"""
    platforms: List[str] = ["jarir"]
    max_products: int = 50


class ScrapeStatus(BaseModel):
    """Response with scrape status"""
    status: str  # "idle", "scraping", "complete", "error"
    last_scrape: Optional[str]
    products_count: int
    message: str


class Product(BaseModel):
    """Product model"""
    master_sku: str
    brand: Optional[str]
    model_name: Optional[str]
    price: float
    best_price: Optional[float]
    best_price_platform: Optional[str]


# ============= HEALTH & STATUS =============

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "api_version": "1.0.0"
    }


@app.get("/status")
async def get_status() -> ScrapeStatus:
    """Get current scraping status"""
    global last_scrape, scraping_in_progress

    # Check if we have data
    products_count = 0
    if Path(DATA_DIR) / "merged_products.json" in Path(DATA_DIR).glob("*"):
        try:
            with open(DATA_DIR / "merged_products.json") as f:
                products_count = len(json.load(f))
        except:
            pass

    status = "scraping" if scraping_in_progress else "idle"

    return ScrapeStatus(
        status=status,
        last_scrape=last_scrape,
        products_count=products_count,
        message="System is ready" if not scraping_in_progress else "Scraping in progress..."
    )


# ============= DATA ENDPOINTS =============

@app.get("/products")
async def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
) -> Dict:
    """Get merged products with pagination"""
    merged_file = Path(DATA_DIR) / "merged_products.json"

    if not merged_file.exists():
        raise HTTPException(status_code=404, detail="No products data available yet")

    try:
        with open(merged_file) as f:
            products = json.load(f)

        total = len(products)
        paginated = products[skip:skip + limit]

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "count": len(paginated),
            "products": paginated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/products/search")
async def search_products(
    brand: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None
) -> Dict:
    """Search/filter products"""
    merged_file = Path(DATA_DIR) / "merged_products.json"

    if not merged_file.exists():
        raise HTTPException(status_code=404, detail="No products data available yet")

    try:
        with open(merged_file) as f:
            products = json.load(f)

        # Filter
        if brand:
            products = [p for p in products if p.get("brand", "").lower() == brand.lower()]

        if min_price:
            products = [p for p in products if p.get("best_price", 0) >= min_price]

        if max_price:
            products = [p for p in products if p.get("best_price", float('inf')) <= max_price]

        return {
            "count": len(products),
            "filters": {
                "brand": brand,
                "min_price": min_price,
                "max_price": max_price
            },
            "products": products
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= SCRAPING ENDPOINTS =============

async def run_scrape(platforms: List[str], max_products: int):
    """Background scraping task"""
    global last_scrape, scraping_in_progress

    try:
        scraping_in_progress = True
        all_products = []

        # Scrape Jarir
        if "jarir" in platforms:
            print("[API] Scraping Jarir...")
            jarir = JarirScraper()
            jarir_products = jarir.scrape_all(max_per_category=max_products)
            all_products.extend(jarir_products)

        if not all_products:
            print("[API] No products scraped")
            return

        # Merge
        print("[API] Merging products...")
        matcher = ProductMatcher()
        unified_products = matcher.merge_products(all_products)

        # Save
        os.makedirs(DATA_DIR, exist_ok=True)

        raw_file = Path(DATA_DIR) / "raw_products.json"
        with open(raw_file, 'w') as f:
            json.dump(all_products, f, ensure_ascii=False, indent=2, default=str)

        merged_file = Path(DATA_DIR) / "merged_products.json"
        with open(merged_file, 'w') as f:
            json.dump(list(unified_products.values()), f, ensure_ascii=False, indent=2, default=str)

        # Generate Excel
        print("[API] Generating Excel...")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        excel_path = f'{OUTPUT_DIR}/saudi_laptop_prices_{timestamp}.xlsx'
        ExcelExporter.merge_data_and_export(list(unified_products.values()), all_products, excel_path)

        last_scrape = datetime.now().isoformat()
        print(f"[API] Scrape complete: {len(all_products)} products → {len(unified_products)} unique")

    except Exception as e:
        print(f"[API] Scrape error: {e}")

    finally:
        scraping_in_progress = False


@app.post("/scrape")
async def trigger_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """Trigger scraping in background"""
    global scraping_in_progress

    if scraping_in_progress:
        raise HTTPException(status_code=409, detail="Scraping already in progress")

    # Start background task
    background_tasks.add_task(run_scrape, request.platforms, request.max_products)

    return {
        "status": "scraping",
        "message": "Scrape started in background",
        "platforms": request.platforms,
        "timestamp": datetime.now().isoformat()
    }


# ============= FILE DOWNLOADS =============

@app.get("/download/excel")
async def download_latest_excel():
    """Download latest Excel report"""
    excel_dir = Path(OUTPUT_DIR)

    if not excel_dir.exists():
        raise HTTPException(status_code=404, detail="No reports generated yet")

    # Find latest Excel file
    excel_files = sorted(excel_dir.glob("*.xlsx"), reverse=True)

    if not excel_files:
        raise HTTPException(status_code=404, detail="No Excel files found")

    latest = excel_files[0]

    return FileResponse(
        path=latest,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"saudi_laptop_prices_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    )


@app.get("/download/json")
async def download_json(format: str = Query("merged", regex="^(raw|merged)$")):
    """Download data as JSON"""
    file_name = f"{format}_products.json"
    json_file = Path(DATA_DIR) / file_name

    if not json_file.exists():
        raise HTTPException(status_code=404, detail=f"No {format} data available")

    return FileResponse(
        path=json_file,
        media_type="application/json",
        filename=f"{file_name}"
    )


@app.get("/files")
async def list_files():
    """List all available reports"""
    excel_files = list(Path(OUTPUT_DIR).glob("*.xlsx")) if Path(OUTPUT_DIR).exists() else []
    json_files = list(Path(DATA_DIR).glob("*_products.json")) if Path(DATA_DIR).exists() else []

    return {
        "excel": [{"name": f.name, "size": f.stat().st_size, "modified": f.stat().st_mtime} for f in excel_files],
        "json": [{"name": f.name, "size": f.stat().st_size, "modified": f.stat().st_mtime} for f in json_files]
    }


# ============= ROOT =============

@app.get("/")
async def root():
    """API documentation"""
    return {
        "name": "Saudi Laptop Price Comparison API",
        "version": "1.0.0",
        "endpoints": {
            "Health": "GET /health",
            "Status": "GET /status",
            "Products": "GET /products",
            "Search": "GET /products/search",
            "Trigger Scrape": "POST /scrape",
            "Download Excel": "GET /download/excel",
            "Download JSON": "GET /download/json",
            "List Files": "GET /files"
        },
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
