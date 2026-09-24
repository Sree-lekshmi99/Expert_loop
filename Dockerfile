FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 EXPERTLOOP_DATA_DIR=/app/state
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/state && chown appuser:appuser /app/state
COPY --chown=appuser:appuser expertloop ./expertloop
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["python", "-m", "expertloop", "serve", "--host", "0.0.0.0", "--port", "8000"]
