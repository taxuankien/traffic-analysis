"""WebSocket endpoint cho session progress events.

Client connect:  ws://host/ws/sessions/{session_id}
Server gửi (1 chiều): JSON events từ ``JobManager`` broadcast queue.

Events: progress | interval | completed | failed | cancelled | artifact_ready
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.adapters.input.web.jobs import JobManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def session_progress(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    jobs: JobManager | None = websocket.app.state.jobs
    if jobs is None:
        await websocket.send_json({"type": "error", "detail": "JobManager chưa khởi động."})
        await websocket.close()
        return

    try:
        queue, last_event = jobs.subscribe(session_id)
    except KeyError:
        await websocket.send_json(
            {"type": "error", "detail": f"Session '{session_id}' không có hoặc đã kết thúc."}
        )
        await websocket.close()
        return

    if last_event is not None:
        try:
            await websocket.send_json(last_event)
        except Exception:  # noqa: BLE001
            jobs.unsubscribe(session_id, queue)
            return

    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("type") in ("completed", "failed", "cancelled"):
                # Continue forwarding artifact_ready events queued after completed.
                # Drain queue with short timeout so client gets all post-completion events.
                try:
                    while True:
                        extra = await asyncio.wait_for(queue.get(), timeout=2.0)
                        await websocket.send_json(extra)
                except asyncio.TimeoutError:
                    break
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("WS error session=%s: %s", session_id, exc)
    finally:
        jobs.unsubscribe(session_id, queue)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
