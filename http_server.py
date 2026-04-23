#!/usr/bin/env python3
"""
HTTP wrapper for MemPalace MCP Server
Provides HTTP endpoint for MCP stdio server
"""
import subprocess
import json
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MemPalace MCP HTTP Server")

# Start MCP server as subprocess
mcp_process = None

@app.on_event("startup")
async def startup():
    global mcp_process
    logger.info("Starting MemPalace MCP server...")
    mcp_process = subprocess.Popen(
        ["python3", "-m", "mempalace.mcp_server", "--vector-store", "qdrant"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0
    )
    logger.info(f"MCP server started with PID {mcp_process.pid}")

@app.on_event("shutdown")
async def shutdown():
    global mcp_process
    if mcp_process:
        mcp_process.terminate()
        mcp_process.wait()
        logger.info("MCP server stopped")

async def call_mcp(method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Send request to MCP server via stdin/stdout"""
    global mcp_process
    
    if not mcp_process or mcp_process.poll() is not None:
        raise Exception("MCP server not running")
    
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {}
    }
    
    try:
        # Send request
        request_json = json.dumps(request) + "\n"
        mcp_process.stdin.write(request_json)
        mcp_process.stdin.flush()
        
        # Read response
        response_line = mcp_process.stdout.readline()
        if not response_line:
            raise Exception("No response from MCP server")
        
        response = json.loads(response_line.strip())
        return response
    except Exception as e:
        logger.error(f"Error calling MCP: {e}")
        raise

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "mcp_running": mcp_process is not None and mcp_process.poll() is None
    }

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP HTTP endpoint"""
    try:
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {})
        
        response = await call_mcp(method, params)
        return JSONResponse(content=response)
    except Exception as e:
        logger.error(f"Error handling MCP request: {e}")
        return JSONResponse(
            status_code=500,
            content={"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3002)