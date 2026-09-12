FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 nexora
COPY __init__.py api.py admin.py settings.py store.py prompt.py ./nexora_backend/
RUN mkdir -p /var/data && chown -R nexora:nexora /var/data /app
USER nexora
ENV NEXORA_DATABASE=/var/data/nexora.sqlite3
EXPOSE 8000
CMD ["uvicorn", "nexora_backend.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--no-proxy-headers", "--limit-concurrency", "32"]
