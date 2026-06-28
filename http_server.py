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
import urllib.request
import urllib.error
from pathlib import Path
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from sse_starlette.sse import EventSourceResponse
from typing import Dict, Any, Optional
import logging
import itertools

_mcp_request_id = itertools.count(start=1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MemPalace MCP HTTP Server (SSE)")

LANDING_DIR = Path(__file__).parent / "landing"
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
mcp_process: Optional[subprocess.Popen] = None

# MCP SSE state
_pending_responses: Dict[int, asyncio.Future] = {}
_sse_streams: Dict[str, asyncio.Queue] = {}
_sse_lock = asyncio.Lock()
_process_lock = asyncio.Lock()
_stdout_reader_task: Optional[asyncio.Task] = None

WING_COLLECTIONS = {
    "tcdserver": "meilin_tcdserver",
    "code_chronicles": "meilin_code_chronicles",
    "openclaw": "meilin_openclaw",
    "robotics": "meilin_robotics",
    "omniscience_wiki": "meilin_omniscience_wiki",
    "conversation": "meilin_conversation",
}


def qdrant_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if QDRANT_API_KEY:
        headers["api-key"] = QDRANT_API_KEY
    return headers


def qdrant_scroll(collection: str, limit: int = 100, offset_id=None) -> tuple:
    """Scroll Qdrant collection points, optionally from an offset."""
    url = f"{QDRANT_URL}/collections/{collection}/points/scroll"
    body = {"limit": limit, "with_payload": ["entity_name", "topic", "content", "importance", "version"], "with_vector": False}
    if offset_id:
        body["offset"] = offset_id
    payload = json.dumps(body).encode()
    try:
        req = urllib.request.Request(url, data=payload, headers=qdrant_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            result = data.get("result", {})
            return result.get("points", []), result.get("next_offset")
    except Exception as e:
        logger.error(f"Qdrant scroll error: {e}")
        return [], None


def query_qdrant_entity(collection: str, entity_name: str, limit: int = 10) -> list:
    """Query Qdrant scroll API for points matching entity_name."""
    url = f"{QDRANT_URL}/collections/{collection}/points/scroll"
    payload = json.dumps({
        "filter": {"must": [{"key": "entity_name", "match": {"value": entity_name}}]},
        "limit": limit, "with_payload": True, "with_vector": False
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, headers=qdrant_headers())
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("result", {}).get("points", [])
    except Exception as e:
        logger.error(f"Qdrant query error: {e}")
        return []


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
        response = await call_mcp(method, params, request_id=req_id)
        return JSONResponse(content=response)
    except Exception as e:
        logger.error(f"Error handling MCP request: {e}")
        return JSONResponse(
            status_code=500,
            content={"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}
        )


@app.get("/mcp")
async def mcp_sse_fallback(request: Request):
    """SSE fallback for MCP SDK reconnect."""
    from sse_starlette.sse import EventSourceResponse
    async def _events():
        yield {"event": "endpoint", "data": "/sse"}
        yield {"event": "close", "data": ""}
    return EventSourceResponse(_events())

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
    """Build graph data structure from all 6 Qdrant wings."""
    result_wings = []
    result_entities = []
    for wing_id, collection in WING_COLLECTIONS.items():
        try:
            pts, _ = qdrant_scroll(collection, limit=80)
            topics_map = {}
            entities_list = []
            for p in pts:
                pl = p.get("payload", {})
                en = pl.get("entity_name", "") or ""
                tp = pl.get("topic", "general") or "general"
                if en and en not in [e.get("name") for e in entities_list]:
                    entities_list.append({"name": en, "type": tp.split("_")[-1] if "_" in tp else "doc", "topic": tp, "wing": wing_id})
                if tp not in topics_map:
                    topics_map[tp] = []
                if en and en not in topics_map[tp]:
                    topics_map[tp].append(en)
            result_wings.append({
                "id": wing_id, "points": len(pts),
                "topics": list(topics_map.keys())
            })
            result_entities.extend(entities_list)
        except Exception as e:
            logger.error(f"Error scrolling {collection}: {e}")
            result_wings.append({"id": wing_id, "points": 0, "topics": []})
    return {"wings": result_wings, "entities": result_entities}


@app.get("/api/entity")
async def get_entity(wing: str = Query(...), name: str = Query(...)):
    """Query actual Qdrant points by wing + entity name."""
    collection = WING_COLLECTIONS.get(wing)
    if not collection:
        return JSONResponse(status_code=400, content={"error": f"Unknown wing: {wing}"})
    points = query_qdrant_entity(collection, name, limit=10)
    results = []
    for p in points:
        payload = p.get("payload", {})
        results.append({
            "id": p.get("id"),
            "score": p.get("score"),
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
