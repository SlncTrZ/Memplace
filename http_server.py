#!/usr/bin/env python3
"""
HTTP wrapper for MemPalace MCP Server — with SSE transport, static files + Qdrant query API.
Wing: tcdserver | Topic: mempalace | Updated: 2026-06-26
"""
import subprocess
import json
import asyncio
import os
import uuid
from pathlib import Path
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from sse_starlette.sse import EventSourceResponse
from typing import Dict, Any, Optional
import logging
import itertools
from mempalace.backends import get_backend
from qdrant_client.models import Filter as QdrantFilter, FieldCondition, MatchValue

_mcp_request_id = itertools.count(start=1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MemPalace MCP HTTP Server (SSE)")

LANDING_DIR = Path(__file__).parent / "landing"
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
mcp_process: Optional[subprocess.Popen] = None

# MCP SSE state
_pending_responses: Dict[int, asyncio.Future] = {}
_sse_streams: Dict[str, asyncio.Queue] = {}
_sse_lock = asyncio.Lock()
_process_lock = asyncio.Lock()
_stdout_reader_task: Optional[asyncio.Task] = None



def _get_qdrant_backend():
    """Lazy-init QdrantBackend from mempalace.backends registry."""
    return get_backend("qdrant")  # noqa: F821


async def _mcp_stdout_reader():
    """Background task: read subprocess stdout and dispatch JSON-RPC responses."""
    global mcp_process
    loop = asyncio.get_event_loop()
    reader_count = 0
    logger.info("MCP stdout reader started")
    while mcp_process and mcp_process.poll() is None:
        try:
            line = await loop.run_in_executor(None, mcp_process.stdout.readline)
            if not line:
                reader_count += 1
                if reader_count > 10:
                    logger.warning("MCP stdout returned 10 empty lines -- process may have exited")
                    await asyncio.sleep(2)
                else:
                    await asyncio.sleep(0.2)
                continue
            reader_count = 0
            response = json.loads(line.strip())
            req_id = response.get("id")
            logger.info(f"MCP stdout: id={req_id} method={response.get('method','?')}")

            if req_id is not None and req_id in _pending_responses:
                future = _pending_responses.pop(req_id)
                logger.info(f"Resolved future for id={req_id}")
                if not future.done():
                    future.set_result(response)

            async with _sse_lock:
                for session_id, queue in list(_sse_streams.items()):
                    try:
                        await queue.put(response)
                    except Exception:
                        _sse_streams.pop(session_id, None)
        except (json.JSONDecodeError, asyncio.CancelledError):
            continue
        except Exception as e:
            logger.error(f"MCP stdout reader error: {e}")
            await asyncio.sleep(1)
    logger.info("MCP stdout reader stopped")


async def call_mcp(method: str, params: Dict[str, Any] = None, request_id: Any = None) -> Dict[str, Any]:
    """Write JSON-RPC to subprocess stdin, await response via background reader.

    Args:
        method: JSON-RPC method name
        params: Method parameters
        request_id: Optional explicit request ID. If None, auto-generates one.
                     Pass the client's original ID to preserve request-response matching.
    """
    global mcp_process
    if not mcp_process or mcp_process.poll() is not None:
        raise Exception("MCP server not running")

    is_notification = method.startswith("notifications/")
    if request_id is None and not is_notification:
        request_id = next(_mcp_request_id)

    request = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if request_id is not None:
        request["id"] = request_id

    future: Optional[asyncio.Future] = None
    if request_id is not None:
        future = asyncio.get_event_loop().create_future()
        _pending_responses[request_id] = future

    request_json = json.dumps(request) + "\n"
    logger.info(f"MCP call: {method} id={request_id} future={future is not None}")

    async with _process_lock:
        mcp_process.stdin.write(request_json)
        mcp_process.stdin.flush()
        logger.info(f"MCP write done: {method}")

    if future is None:
        return {"jsonrpc": "2.0"}

    try:
        result = await asyncio.wait_for(future, timeout=60.0)
        logger.info(f"MCP response received for {method} id={request_id}")
        return result
    except asyncio.TimeoutError:
        _pending_responses.pop(request_id, None)
        logger.error(f"MCP request {request_id} ({method}) timed out after 60s")
        raise Exception(f"MCP request {request_id} ({method}) timed out after 60s")


@app.on_event("startup")
async def startup():
    global mcp_process, _stdout_reader_task
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
    _stdout_reader_task = asyncio.create_task(_mcp_stdout_reader())


@app.on_event("shutdown")
async def shutdown():
    global mcp_process, _stdout_reader_task
    if _stdout_reader_task:
        _stdout_reader_task.cancel()
        try:
            await _stdout_reader_task
        except asyncio.CancelledError:
            pass
    if mcp_process:
        mcp_process.terminate()
        try:
            mcp_process.wait(timeout=5)
        except Exception:
            mcp_process.kill()
        logger.info("MCP server stopped")


# --- Legacy POST /mcp (direct JSON-RPC bridge) ---

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """Legacy JSON-RPC endpoint: returns response directly (not via SSE)."""
    try:
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id")
        
        # Handle initialize in-process to avoid subprocess startup race
        if method == "initialize":
            from mempalace.version import __version__
            _SUPPORTED_VERSIONS = ["2025-03-26", "2024-11-05"]
            cv = params.get("protocolVersion", _SUPPORTED_VERSIONS[-1])
            neg = cv if cv in _SUPPORTED_VERSIONS else _SUPPORTED_VERSIONS[0]
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": neg,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mempalace", "version": __version__},
                },
            })
        
        if method == "ping":
            return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {}})
        
        response = await call_mcp(method, params, request_id=req_id)
        return JSONResponse(content=response)
    except Exception as e:
        logger.error(f"Error handling MCP request: {e}")
        return JSONResponse(
            status_code=500,
            content={"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}
        )



# --- SSE Transport (MCP Standard) ---

@app.get("/sse")
async def sse_endpoint(request: Request):
    """SSE transport endpoint for MCP protocol."""
    from sse_starlette.sse import EventSourceResponse
    
    async def event_generator():
        session_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        async with _sse_lock:
            _sse_streams[session_id] = queue
        try:
            yield {"event": "endpoint", "data": "/sse"}
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {"event": "message", "data": data}
                except asyncio.TimeoutError:
                    yield {"event": "keepalive", "data": ""}
        except asyncio.CancelledError:
            pass
        finally:
            async with _sse_lock:
                _sse_streams.pop(session_id, None)
    
    return EventSourceResponse(event_generator())


@app.post("/sse")
async def sse_post(request: Request):
    """POST to SSE endpoint — MCP SDK sends JSON-RPC here."""
    try:
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id")
        response = await call_mcp(method, params, request_id=req_id)
        return JSONResponse(content=response)
    except Exception as e:
        logger.error(f"SSE POST error: {e}")
        return JSONResponse(
            status_code=500,
            content={"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}
        )

    """
    MCP SSE transport endpoint.
    Client opens GET /sse -> receives endpoint event -> POSTs JSON-RPC to that URL.
    Responses arrive as SSE 'message' events.
    """
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()

    async with _sse_lock:
        _sse_streams[session_id] = queue

    logger.info(f"SSE session opened: {session_id}")

    async def event_generator():
        try:
            yield {
                "event": "endpoint",
                "data": f"/messages/{session_id}"
            }

            while True:
                if await request.is_disconnected():
                    break
                try:
                    response = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": "message",
                        "data": json.dumps(response)
                    }
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            async with _sse_lock:
                _sse_streams.pop(session_id, None)
            logger.info(f"SSE session closed: {session_id}")

    return EventSourceResponse(event_generator())


@app.post("/messages/{session_id}")
async def mcp_messages(session_id: str, request: Request):
    """
    Receive JSON-RPC messages from MCP client over SSE transport.
    Returns 202 Accepted; actual response goes through the SSE stream.
    """
    try:
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id")
        logger.info(f"SSE message: {method} id={req_id} (session={session_id[:8]}...)")
        await call_mcp(method, params, request_id=req_id)
        return JSONResponse(
            content={"jsonrpc": "2.0", "result": "accepted"},
            status_code=202
        )
    except Exception as e:
        logger.error(f"Error handling SSE message: {e}")
        return JSONResponse(
            status_code=500,
            content={"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}
        )


# --- Existing API routes ---

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "mcp_running": mcp_process is not None and mcp_process.poll() is None
    }


@app.get("/api/graph-data")
async def get_graph_data():
    """Build graph data structure from all Qdrant wings discovered dynamically."""
    backend = _get_qdrant_backend()
    client = backend._lazy_client
    collections_info = client.get_collections()

    result_wings = []
    result_entities = []
    for col_info in collections_info.collections:
        name = col_info.name
        if not name.startswith("meilin_"):
            continue
        wing_id = name[len("meilin_"):]
        try:
            records, _ = client.scroll(
                collection_name=name, limit=80,
                with_payload=["entity_name", "topic", "content", "importance", "version"],
                with_vector=False,
            )
            topics_map = {}
            entities_list = []
            for p in records:
                pl = p.payload or {}
                en = pl.get("entity_name", "") or ""
                tp = pl.get("topic", "general") or "general"
                if en and en not in [e.get("name") for e in entities_list]:
                    entities_list.append({"name": en, "type": tp.split("_")[-1] if "_" in tp else "doc", "topic": tp, "wing": wing_id})
                if tp not in topics_map:
                    topics_map[tp] = []
                if en and en not in topics_map[tp]:
                    topics_map[tp].append(en)
            result_wings.append({
                "id": wing_id, "points": len(records),
                "topics": list(topics_map.keys())
            })
            result_entities.extend(entities_list)
        except Exception as e:
            logger.error(f"Error scrolling {name}: {e}")
            result_wings.append({"id": wing_id, "points": 0, "topics": []})
    return {"wings": result_wings, "entities": result_entities}


@app.get("/api/entity")
async def get_entity(wing: str = Query(...), name: str = Query(...)):
    """Query actual Qdrant points by wing + entity name."""
    collection_name = f"meilin_{wing}"
    backend = _get_qdrant_backend()
    client = backend._lazy_client
    try:
        records, _ = client.scroll(
            collection_name=collection_name, limit=10,
            with_payload=True, with_vector=False,
            scroll_filter=QdrantFilter(
                must=[FieldCondition(key="entity_name", match=MatchValue(value=name))]
            ),
        )
    except Exception as e:
        logger.error(f"Qdrant scroll error for {collection_name}: {e}")
        return JSONResponse(status_code=404, content={"error": f"Collection not found: {collection_name}"})
    results = []
    for p in records:
        payload = p.payload or {}
        results.append({
            "id": str(p.id),
            "score": getattr(p, "score", None),
            "version": payload.get("version", 1),
            "content": payload.get("content", ""),
            "topic": payload.get("topic", ""),
            "importance": payload.get("importance", "medium"),
        })
    return {"entity": name, "wing": wing, "points": results, "count": len(results)}


@app.get("/")
async def landing_page():
    index = LANDING_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse(status_code=404, content={"error": "landing page not found"})


@app.get("/graph")
async def graph_page():
    graph = LANDING_DIR / "graph.html"
    if graph.exists():
        return FileResponse(str(graph))
    return JSONResponse(status_code=404, content={"error": "graph page not found"})


@app.get("/{path:path}")
async def serve_static(path: str):
    file_path = LANDING_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    return JSONResponse(status_code=404, content={"error": "not found"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3002)
