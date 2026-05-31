FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy Excel data files for first-run import
COPY ./data /app/data

# Expose the port
EXPOSE 8888

# Run with gunicorn for production
# Use DATABASE_PATH env or default to /app/data/clinic.db
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8888} --workers 2 --timeout 120 'app:app'"]
