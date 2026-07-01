FROM python:3.11-slim

# No build tools needed for the pure-Python deps; keep the image small.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Artifacts and (optional) mock tenant live under /app; mount volumes to persist.
EXPOSE 8000

# DefaultAzureCredential picks up a Managed Identity in Azure, or a service
# principal via AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_CLIENT_SECRET env vars.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
