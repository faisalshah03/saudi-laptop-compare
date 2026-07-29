# 🚀 Deployment Guide - Saudi Laptop Price Comparison

Deploy your dashboard & API to the cloud so it's accessible from **anywhere**.

---

## 📋 Quick Comparison

| Platform | Cost | Setup | Best For |
|----------|------|-------|----------|
| **Streamlit Cloud** | Free (tier 1) | 5 min | Dashboard only |
| **Railway** | $5/mo | 10 min | Full stack (API + Dashboard) |
| **Render** | Free (tier) | 10 min | Full stack, good performance |
| **Heroku** | $7/mo | 10 min | Reliable, established |
| **Vercel** | Free | 5 min | Frontend only (need backend) |

---

## 🎯 RECOMMENDED: Railway + Streamlit Cloud (Hybrid)

**Best combination for your needs**:
- 🎨 **Dashboard**: Streamlit Cloud (free, easy)
- 🔧 **API/Scraping**: Railway ($5/mo, reliable)
- 📊 **Data Storage**: Local → JSON (free)

---

## 1️⃣ Option A: Railway (Recommended for API + Background Tasks)

### Setup (10 minutes)

**Step 1: Push to GitHub**
```bash
cd /Users/faisals/Documents/saudi-laptop-compare
git init
git add .
git commit -m "Initial commit: Saudi laptop price comparison"
git remote add origin https://github.com/YOUR_USERNAME/saudi-laptop-compare.git
git push -u origin main
```

**Step 2: Create Railway Project**
1. Go to https://railway.app
2. Click "New Project" → "Deploy from GitHub"
3. Select your repository
4. Railway auto-detects the Dockerfile

**Step 3: Add Environment Variables**
In Railway dashboard:
- `FIRECRAWL_API_KEY` = your-api-key

**Step 4: Deploy**
- Railway automatically deploys on push
- Your API is live at: `https://your-project.up.railway.app`

### Access Your System
- **API Docs**: https://your-project.up.railway.app/docs
- **Trigger Scrape**: `POST https://your-project.up.railway.app/scrape`
- **Download Excel**: `GET https://your-project.up.railway.app/download/excel`
- **Status**: `GET https://your-project.up.railway.app/status`

---

## 2️⃣ Option B: Streamlit Cloud (Dashboard Only - Easiest)

### Setup (5 minutes)

**Step 1: Push to GitHub** (same as above)

**Step 2: Deploy to Streamlit Cloud**
1. Go to https://share.streamlit.io
2. Click "New app" → Select GitHub repo and `dashboard.py`
3. Add secrets:
   ```
   FIRECRAWL_API_KEY = "your-key"
   DASHBOARD_PASSWORD = "demo"
   ```

**Step 3: Done!**
- Dashboard is live at: `https://app-name.streamlit.app`
- Automatically updates on GitHub push

### Limitations
- ⚠️ No background tasks (scraping blocks UI)
- ⚠️ Data lost on app restart
- ✅ Free & easy for testing

**Solution**: Connect to Railway API backend instead of local scraping

---

## 3️⃣ Hybrid Setup (Best Practice)

Streamlit Cloud Dashboard + Railway API Backend

### Architecture
```
┌─────────────────────────────────────────────┐
│   Streamlit Cloud (Dashboard)               │
│   https://app.streamlit.app                 │
│   - Display products                        │
│   - Filters & sorting                       │
│   - Download buttons                        │
│   ↓ API calls ↓                            │
│                                             │
│   Railway Backend (API)                     │
│   https://api.up.railway.app                │
│   - /status → check scraping status         │
│   - /scrape → trigger background scraping   │
│   - /products → get data                    │
│   - /download/excel → get report            │
│   ↓ stores ↓                                │
│                                             │
│   Cloud Storage (Data)                      │
│   - JSON data files                         │
│   - Excel reports                           │
└─────────────────────────────────────────────┘
```

### Update Dashboard for Remote API

Edit `dashboard.py`:
```python
import os

# Get API URL from environment
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Replace direct function calls with API calls
def get_products():
    import requests
    response = requests.get(f"{API_URL}/products")
    return response.json()["products"]

def download_excel():
    import requests
    response = requests.get(f"{API_URL}/download/excel")
    if response.status_code == 200:
        with open("report.xlsx", "wb") as f:
            f.write(response.content)
        st.download_button("📥 Download Excel", response.content)
```

---

## 4️⃣ Local Alternative: ngrok (for testing)

### Quick Local Testing
```bash
# Terminal 1: Run API
python3 -m uvicorn api:app --reload

# Terminal 2: Share with ngrok
ngrok http 8000
# Public URL: https://xxxxxxx.ngrok.io
```

Then access from anywhere:
- Dashboard: http://localhost:8501
- API: https://xxxxxxx.ngrok.io

---

## 📦 Deployment Checklist

- [ ] GitHub repo created & pushed
- [ ] Environment variables configured
- [ ] Dockerfile builds successfully
- [ ] API responds to `/health` check
- [ ] Dashboard connects to API (if hybrid)
- [ ] Test scraping endpoint (`/scrape`)
- [ ] Test download endpoint (`/download/excel`)
- [ ] Monitor logs for errors

---

## 🔒 Security for Production

### 1. Secure API with Authentication
Add to `api.py`:
```python
from fastapi.security import HTTPBearer, HTTPAuthCredentials

security = HTTPBearer()

@app.get("/status")
async def get_status(credentials: HTTPAuthCredentials = Depends(security)):
    if credentials.credentials != "your-secret-key":
        raise HTTPException(status_code=403)
    # ...
```

### 2. Rate Limiting
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/scrape")
@limiter.limit("5/hour")
async def trigger_scrape(...):
    # ...
```

### 3. HTTPS Only
Railway & Streamlit Cloud provide HTTPS by default ✅

### 4. Secrets Management
Never commit API keys! Use environment variables:
- Streamlit Cloud: Dashboard → Settings → Secrets
- Railway: Project → Variables
- GitHub: Settings → Secrets & variables

---

## 💾 Persistent Data Storage

### Option 1: Local (Railway)
Data persists in `/data` and `/output` directories

### Option 2: Google Drive (Free)
```python
from google.colab import auth
from googleapiclient.discovery import build

# Upload to Drive after scraping
drive_service = build('drive', 'v3', credentials=credentials)
```

### Option 3: AWS S3 ($1/mo)
```python
import boto3

s3 = boto3.client('s3')
s3.upload_file('report.xlsx', 'bucket-name', 'reports/')
```

### Option 4: Firebase Firestore (Free tier)
```python
from firebase_admin import firestore

db = firestore.client()
db.collection('products').add(product_data)
```

---

## 🔧 Post-Deployment Testing

### Test API Endpoints
```bash
# Health check
curl https://your-api.up.railway.app/health

# Get status
curl https://your-api.up.railway.app/status

# List products
curl https://your-api.up.railway.app/products?limit=5

# Trigger scrape
curl -X POST https://your-api.up.railway.app/scrape

# Download Excel
curl https://your-api.up.railway.app/download/excel -o report.xlsx
```

### Monitor Logs
- **Railway**: Project → Logs tab
- **Streamlit Cloud**: App → Logs
- **Heroku**: `heroku logs --tail`

---

## 🚨 Troubleshooting Deployments

### "Module not found" errors
```bash
# Ensure all imports in api.py use absolute paths
# Fix: python3 -m pip install -r requirements.txt
```

### API timeout
```bash
# Increase timeout in client
# Railway default: 120s, sufficient for scraping
```

### Dashboard can't connect to API
```python
# Check CORS in api.py
# Verify API_URL environment variable is correct
import os
print(os.getenv("API_URL"))
```

### Out of memory
```bash
# Railway free tier: 512MB
# Split scraping into smaller batches
# Limit max_products to 20 per platform
```

---

## 📊 Monitoring & Alerts

### Add Uptime Monitoring
```bash
# UptimeRobot (free)
# Monitor: https://your-api.up.railway.app/health
# Alert if down for 5+ minutes
```

### Add Error Logging
```python
# Add to api.py
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.post("/scrape")
async def trigger_scrape(...):
    try:
        # scraping code
    except Exception as e:
        logger.error(f"Scrape failed: {e}")
        # Send alert to email/Slack
```

---

## 🎯 Next Steps

1. **Choose deployment platform** (Railway recommended)
2. **Push to GitHub** with deployment configs
3. **Deploy & test** endpoints
4. **Monitor** first scrape run
5. **Set up automatic scheduled scraping** (optional)

---

## 💬 Support

If deployment fails:
1. Check logs in platform dashboard
2. Verify FIRECRAWL_API_KEY is set
3. Test locally: `python3 -m uvicorn api:app`
4. Review error messages in build output

---

**Total Cost for Production**:
- Streamlit Cloud: **FREE** (dashboard)
- Railway: **$5/month** (API + storage)
- Domain: **$10-15/year** (optional)
- **Total: ~$5/month** ✅

Ready to deploy? Pick Railway, push to GitHub, and you're live in 10 minutes!
