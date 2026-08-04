"""SchemaViz Backend API"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.bigquery import router as bigquery_router
from app.api.catalog import router as catalog_router
from app.api.chat import router as chat_router
from app.api.connection import router as connection_router
from app.api.dataverse import router as dataverse_router
from app.api.diagrams import router as diagrams_router
from app.api.gcs import router as gcs_router
from app.api.postgres import router as postgres_router
from app.api.schema import router as schema_router
from app.api.sharepoint import router as sharepoint_router

app = FastAPI(
    title="SchemaViz API",
    description="ER Diagram Generator Backend",
    version="0.1.0",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for Cloud Run deployment
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-User-ID"],
)

# Register API routers
app.include_router(bigquery_router)
app.include_router(catalog_router)
app.include_router(chat_router)
app.include_router(connection_router)
app.include_router(dataverse_router)
app.include_router(diagrams_router)
app.include_router(gcs_router)
app.include_router(postgres_router)
app.include_router(schema_router)
app.include_router(sharepoint_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
