import sys
import asyncio

# Fix Windows Proactor socket reset abort issues
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Aegis — Flood Detection & Response System - AI Backend",
    description="FastAPI service for SegFormer MiT-B2 satellite image inference, RAG generation, and LangGraph agent alerts.",
    version="1.0.0"
)

# Set up CORS for mobile client access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to mobile app domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and attach endpoints
from app.api.endpoints import router as api_router
app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {
        "status": "ONLINE",
        "service": "Flood Detection & Response System API",
        "documentation": "/docs"
    }

if __name__ == "__main__":
    # Get port from environment or default to 8000
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on http://localhost:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
