"""
FastAPI Server for GCP VM Management
Main application entry point with SSE support
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uvicorn
import logging
import os
from datetime import datetime
from contextlib import asynccontextmanager
import sys

# Import our custom modules
from core.vm_cache import VMCache
from core.operation_logger import OperationLogger
from core.vm_operations_handler import VMOperationsHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "fastapi.log"))
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting application...")
    try:
        await vm_cache.initialize()
        cache_status = vm_cache.get_status()
        logger.info(f"VM cache initialized with {cache_status['cached_vms']} VMs")
        
        if cache_status['cached_vms'] == 0:
            logger.warning("VM cache is empty. Forcing refresh...")
            await vm_cache.update_cache()
            cache_status = vm_cache.get_status()
            logger.info(f"VM cache refreshed, now contains {cache_status['cached_vms']} VMs")
    except Exception as e:
        logger.error(f"Error during startup initialization: {str(e)}", exc_info=True)
        logger.warning("Application will continue but VM operations may fail until cache is updated")
    
    logger.info("Application startup complete")
    yield  # Server is running here
    
    # Shutdown
    logger.info("Shutting down application...")
    if hasattr(vm_cache, 'stop_refresh_task'):
        vm_cache.stop_refresh_task()
    try:
        vm_cache._save_to_pickle()
        logger.info("Final cache state saved to disk")
    except Exception as e:
        logger.error(f"Error saving cache during shutdown: {e}")
    logger.info("Application shutdown complete")

app = FastAPI(
    title="GCP VM Manager",
    description="API for managing GCP VM instances with real-time status updates",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
vm_cache = VMCache()
operation_logger = OperationLogger()
vm_ops_handler = VMOperationsHandler(vm_cache, operation_logger)

@app.get("/gcp-action/")
async def handle_vm_operation(
    request: Request,
    vmname: str,
    operation: str = "status",
    zone: Optional[str] = None,
    format: str = "sse"  # Parameter to control response format
):
    """
    Handle VM operations with SSE updates or JSON response
    
    Args:
        request: FastAPI request object
        vmname: Name of the VM
        operation: Operation to perform (status/start/stop/suspend/resume)
        zone: Optional zone parameter
        format: Response format - "sse" (streaming) or "json" (single response)
    
    Returns:
        EventSourceResponse for SSE or dict for JSON
    """
    logger.info(f"Received request: {operation} for VM {vmname}, format={format}")
    
    # Validate operation
    valid_operations = ["status", "start", "stop", "suspend", "resume"]
    if operation not in valid_operations:
        logger.warning(f"Invalid operation requested: {operation}")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid operation: {operation}. Valid operations are: {', '.join(valid_operations)}"
        )

    # Get client IP
    client_ip = request.client.host
    logger.info(f"Request from client IP: {client_ip}")

    try:
        # If JSON format is requested
        if format.lower() == "json":
            # For JSON format, we use a dedicated handler that doesn't stream
            return await vm_ops_handler.execute_operation_json(
                vmname=vmname,
                operation=operation,
                zone=zone,
                client_ip=client_ip
            )
        else:
            # For SSE format, use the streaming handler
            return await vm_ops_handler.stream_operation(
                vmname=vmname,
                operation=operation,
                zone=zone,
                client_ip=client_ip
            )
    except HTTPException as he:
        # Properly propagate HTTPExceptions with their status codes
        logger.error(f"HTTP exception: {he.status_code}: {he.detail}")
        raise
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Get VM cache status
        cache_status = vm_cache.get_status() if vm_cache else {"status": "unavailable"}
        
        # List restricted VMs 
        # Access as a module attribute rather than instance attribute
        allowed_vms = getattr(vm_ops_handler, "ALLOWED_VMS", [])
        # Fallback to the module constant if instance doesn't have it
        if not allowed_vms and "ALLOWED_VMS" in globals():
            allowed_vms = ALLOWED_VMS
            
        # Get restricted operations
        restricted_ops = getattr(vm_ops_handler, "RESTRICTED_OPERATIONS", ["stop", "suspend"])
        # Fallback to hardcoded values if not available
        if not restricted_ops:
            restricted_ops = ["stop", "suspend"]
            
        # Create operations dictionary dynamically
        operations_info = {}
        for op in ["status", "start", "stop", "suspend", "resume"]:
            if op in restricted_ops:
                operations_info[op] = f"Restricted to whitelisted VMs"
            else:
                operations_info[op] = "Available for all VMs"
                
        # Add allowed VMs information separately for clarity
        whitelist_info = {"allowed_vms": allowed_vms} if allowed_vms else {"allowed_vms": "No whitelist configured"}
        
        status = {
            "status": "healthy",
            "server_version": "2.0.0",
            "cache_status": cache_status,
            "supported_operations": operations_info,
            "whitelist": whitelist_info,
            "timestamp": datetime.now().isoformat()
        }
        logger.debug(f"Health check: {status}")
        return status
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}", exc_info=True)
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api-docs")
async def api_docs():
    """API documentation"""
    docs = {
        "api_version": "2.0.0",
        "endpoints": {
            "/gcp-action/": {
                "description": "Perform operations on GCP VMs",
                "methods": ["GET"],
                "parameters": {
                    "vmname": {
                        "description": "Name of the VM (required)",
                        "example": "guedfocanoop01"
                    },
                    "operation": {
                        "description": "Operation to perform",
                        "default": "status",
                        "options": ["status", "start", "stop", "suspend", "resume"],
                        "restrictions": "stop and suspend operations are restricted to whitelisted VMs"
                    },
                    "zone": {
                        "description": "GCP zone (optional, will be auto-detected if not provided)",
                        "example": "us-east4-a"
                    },
                    "format": {
                        "description": "Response format",
                        "default": "sse",
                        "options": ["sse", "json"],
                        "example": "format=json for single JSON response"
                    }
                },
                "examples": [
                    "/gcp-action/?vmname=guedfocanoop01&operation=status",
                    "/gcp-action/?vmname=guedfocanoop01&operation=start&format=json",
                    "/gcp-action/?vmname=guedfocanoop01&operation=suspend&zone=us-east4-a"
                ]
            },
            "/health": {
                "description": "Health check endpoint",
                "methods": ["GET"]
            },
            "/api-docs": {
                "description": "This documentation",
                "methods": ["GET"]
            }
        }
    }
    return docs

if __name__ == "__main__":
    uvicorn.run(
        "fastserver:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
