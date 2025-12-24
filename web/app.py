"""
M3U2strm3 Web Interface
FastAPI application providing a web interface for the M3U2strm3 command-line tool.
"""

import os
import json
import logging
import asyncio
import threading
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocket, WebSocketDisconnect

from api.models import ProcessingConfig, ProcessingStatus, ProcessingResult
from utils.web_progress_tracker import WebProgressTracker
from utils.file_handler import FileHandler
from background_tasks import ProcessingManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="M3U2strm3 Web Interface",
    description="Web interface for M3U2strm3 IPTV playlist processor",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="web/templates")

# Global instances
progress_tracker: Optional[WebProgressTracker] = None
file_handler: Optional[FileHandler] = None
processing_manager: Optional[ProcessingManager] = None


@app.on_event("startup")
async def startup_event():
    """Initialize global components on startup."""
    global progress_tracker, file_handler, processing_manager
    
    # Create necessary directories
    Path("web/uploads").mkdir(exist_ok=True)
    Path("web/configs").mkdir(exist_ok=True)
    Path("web/logs").mkdir(exist_ok=True)
    
    # Initialize components
    progress_tracker = WebProgressTracker()
    file_handler = FileHandler(upload_dir="web/uploads", config_dir="web/configs")
    processing_manager = ProcessingManager(progress_tracker, file_handler)
    
    logger.info("M3U2strm3 Web Interface started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    global processing_manager
    
    if processing_manager:
        await processing_manager.shutdown()
    
    logger.info("M3U2strm3 Web Interface shutdown complete")


# Routes

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "title": "M3U2strm3 Dashboard"
    })


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Configuration management page."""
    return templates.TemplateResponse("config.html", {
        "request": request,
        "title": "Configuration"
    })


@app.get("/processing", response_class=HTMLResponse)
async def processing_page(request: Request):
    """Processing interface page."""
    return templates.TemplateResponse("processing.html", {
        "request": request,
        "title": "Processing"
    })


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """Logs viewing page."""
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "title": "Logs"
    })


# API Endpoints

@app.get("/api/status")
async def get_status():
    """Get current system status."""
    if not processing_manager:
        raise HTTPException(status_code=500, detail="System not initialized")
    
    return {
        "status": "running",
        "current_job": processing_manager.get_current_job(),
        "queue_length": processing_manager.get_queue_length(),
        "system_info": {
            "uptime": "N/A",  # Would track actual uptime
            "version": "1.0.0"
        }
    }


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    if not file_handler:
        raise HTTPException(status_code=500, detail="File handler not initialized")
    
    config = file_handler.load_config()
    return config


@app.post("/api/config")
async def save_config(config: ProcessingConfig):
    """Save configuration."""
    if not file_handler:
        raise HTTPException(status_code=500, detail="File handler not initialized")
    
    try:
        file_handler.save_config(config.dict())
        return {"message": "Configuration saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload")
async def upload_m3u_file(file: UploadFile = File(...)):
    """Upload M3U playlist file."""
    if not file_handler:
        raise HTTPException(status_code=500, detail="File handler not initialized")
    
    try:
        file_info = await file_handler.save_upload(file)
        return {
            "message": "File uploaded successfully",
            "filename": file_info["filename"],
            "size": file_info["size"],
            "path": file_info["path"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/process")
async def start_processing(config: ProcessingConfig):
    """Start processing with given configuration."""
    if not processing_manager:
        raise HTTPException(status_code=500, detail="Processing manager not initialized")
    
    try:
        job_id = await processing_manager.submit_job(config)
        return {
            "message": "Processing started",
            "job_id": job_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/progress")
async def get_progress():
    """Get current processing progress."""
    if not progress_tracker:
        raise HTTPException(status_code=500, detail="Progress tracker not initialized")
    
    return progress_tracker.get_web_progress()


@app.get("/api/logs")
async def get_logs(level: str = "INFO", limit: int = 100):
    """Get recent log entries."""
    # This would integrate with the actual logging system
    return {
        "logs": [],
        "total": 0,
        "level": level,
        "limit": limit
    }


@app.post("/api/stop")
async def stop_processing():
    """Stop current processing."""
    if not processing_manager:
        raise HTTPException(status_code=500, detail="Processing manager not initialized")
    
    try:
        await processing_manager.stop_current_job()
        return {"message": "Processing stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """WebSocket endpoint for real-time progress updates."""
    await websocket.accept()
    
    try:
        while True:
            if progress_tracker:
                progress_data = progress_tracker.get_web_progress()
                await websocket.send_json(progress_data)
            
            await asyncio.sleep(1)  # Send updates every second
            
    except WebSocketDisconnect:
        logger.info("Client disconnected from progress WebSocket")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()
    
    try:
        while True:
            # This would stream actual log entries
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "message": "Log streaming placeholder"
            }
            await websocket.send_json(log_entry)
            await asyncio.sleep(2)
            
    except WebSocketDisconnect:
        logger.info("Client disconnected from logs WebSocket")
    except Exception as e:
        logger.error(f"WebSocket logs error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8280,
        reload=True,
        log_level="info"
    )
