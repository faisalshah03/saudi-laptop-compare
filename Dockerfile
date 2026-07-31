# Multi-stage build for Saudi Laptop Comparison System

# Stage 1: Python runtime
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY api.py dashboard.py main.py ./

# Copy pre-scraped data so the dashboard has real data on first load
RUN mkdir -p data output
COPY data/ data/
COPY output/ output/

# Expose port (Railway injects $PORT at runtime)
EXPOSE 8501

# Run the Streamlit dashboard (Railway overrides this via railway.toml startCommand,
# this CMD is the fallback for plain `docker run`)
CMD ["sh", "-c", "streamlit run dashboard.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.headless true"]
