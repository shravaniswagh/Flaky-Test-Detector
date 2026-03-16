# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — Flask Flaky Test Maintenance Tool
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL description="Automated Flaky Test Maintenance Tool"
LABEL version="2.0.0"

# Non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app appuser

WORKDIR /app

# Install Python dependencies (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/main/ ./src/main/
COPY src/test/  ./src/test/

# Create data directory for SQLite persistence
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

# Persistent storage for SQLite database
VOLUME /app/data

USER appuser

EXPOSE 8080

# Health check (fixed: use port 8080, not 5000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENV PYTHONPATH=/app/src/main
ENV FLASK_ENV=production
ENV FLAKYSCAN_DB_PATH=/app/data/flakyscan.db

CMD ["gunicorn", \
     "--chdir", "src/main", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
