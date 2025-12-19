"""
Spike AI Builder Hackathon - Multi-Agent Analytics System
A production-ready AI backend for GA4 Analytics and SEO Analysis
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.orchestrator import Orchestrator
from utils.logger import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    """API Request model"""
    query: str = Field(..., description="Natural language question")
    propertyId: Optional[str] = Field(None, description="GA4 Property ID (required for analytics queries)")


class QueryResponse(BaseModel):
    """API Response model"""
    success: bool
    answer: str
    data: Optional[Any] = None
    agents_used: list[str] = []
    reasoning: Optional[str] = None


# Global orchestrator instance
orchestrator: Optional[Orchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI app"""
    global orchestrator
    logger.info("🚀 Starting Spike AI Multi-Agent System...")
    
    # Initialize orchestrator
    orchestrator = Orchestrator()
    await orchestrator.initialize()
    
    logger.info("✅ System initialized and ready!")
    yield
    
    # Cleanup
    logger.info("👋 Shutting down...")


app = FastAPI(
    title="Spike AI Multi-Agent System",
    description="AI-powered analytics and SEO analysis backend",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Main API endpoint for processing natural language queries.
    Routes to appropriate agents based on intent detection.
    """
    global orchestrator
    
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    try:
        logger.info(f"📥 Received query: {request.query[:100]}...")
        
        # Process through orchestrator
        result = await orchestrator.process(
            query=request.query,
            property_id=request.propertyId
        )
        
        logger.info(f"✅ Query processed successfully. Agents used: {result.get('agents_used', [])}")
        
        return QueryResponse(
            success=True,
            answer=result["answer"],
            data=result.get("data"),
            agents_used=result.get("agents_used", []),
            reasoning=result.get("reasoning")
        )
        
    except ValueError as e:
        logger.warning(f"⚠️ Validation error: {str(e)}")
        return QueryResponse(
            success=False,
            answer=f"Validation error: {str(e)}",
            agents_used=[]
        )
    except Exception as e:
        logger.error(f"❌ Error processing query: {str(e)}", exc_info=True)
        return QueryResponse(
            success=False,
            answer=f"An error occurred while processing your query: {str(e)}",
            agents_used=[]
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info"
    )
