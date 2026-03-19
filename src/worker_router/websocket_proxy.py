from __future__ import annotations

import logging
from asyncio import gather
from urllib.parse import urlsplit, urlunsplit

from fastapi import WebSocket
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from worker_router.proxy import UpstreamConfig

logger = logging.getLogger("worker_router")


def websocket_target(base_url: str, path: str, query: str) -> str:
    parts = urlsplit(f"{base_url.rstrip('/')}/{path.lstrip('/')}")
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, parts.path, query, ""))


async def proxy_websocket(
    websocket: WebSocket,
    upstream: UpstreamConfig,
    path: str,
) -> None:
    target = websocket_target(upstream.base_url, path, websocket.url.query)
    subprotocols = list(websocket.scope.get("subprotocols", []))
    headers = [
        (key, value)
        for key, value in websocket.headers.items()
        if key.lower()
        not in {
            "host",
            "connection",
            "upgrade",
            "sec-websocket-key",
            "sec-websocket-version",
            "sec-websocket-extensions",
        }
    ]
    headers.extend(upstream.headers.items())
    try:
        async with connect(
            target,
            additional_headers=headers,
            subprotocols=subprotocols,
        ) as upstream_ws:
            await websocket.accept(subprotocol=upstream_ws.subprotocol)
            await gather(
                _forward_client_to_upstream(websocket, upstream_ws),
                _forward_upstream_to_client(upstream_ws, websocket),
            )
    except ConnectionClosed:
        await websocket.close()
    except Exception:
        logger.exception(
            "proxy_websocket_error upstream=%s path=%s",
            upstream.name,
            websocket.url.path,
        )
        await websocket.close(code=1011)


async def _forward_client_to_upstream(
    websocket: WebSocket,
    upstream_ws: ClientConnection,
) -> None:
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            await upstream_ws.close()
            return
        if message.get("text") is not None:
            await upstream_ws.send(message["text"])
        elif message.get("bytes") is not None:
            await upstream_ws.send(message["bytes"])


async def _forward_upstream_to_client(
    upstream_ws: ClientConnection,
    websocket: WebSocket,
) -> None:
    while True:
        message = await upstream_ws.recv()
        if isinstance(message, bytes):
            await websocket.send_bytes(message)
        else:
            await websocket.send_text(message)
