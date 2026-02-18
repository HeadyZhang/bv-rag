"""Voice and text query API routes."""
import asyncio
import base64
import json
import logging
import time

from fastapi import APIRouter, Form, Request, UploadFile, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

# === Concurrency control ===
MAX_CONCURRENT_REQUESTS = 10
_request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
_active_requests = 0
_start_time = time.time()


@router.post("/query")
async def voice_query(
    request: Request,
    audio: UploadFile,
    session_id: str = Form(default=None),
    language: str = Form(default=None),
):
    global _active_requests
    _active_requests += 1
    logger.info(f"[CONCURRENCY] Voice query queued ({_active_requests}/{MAX_CONCURRENT_REQUESTS})")
    try:
        async with _request_semaphore:
            logger.info(f"[CONCURRENCY] Voice query processing ({_active_requests}/{MAX_CONCURRENT_REQUESTS})")
            pipeline = request.app.state.pipeline
            audio_data = await audio.read()

            return await pipeline.process_voice_query(
                audio_data=audio_data,
                session_id=session_id,
                audio_format=audio.filename.split(".")[-1] if audio.filename else "webm",
                language=language,
            )
    finally:
        _active_requests -= 1


@router.post("/text-query")
async def text_query(
    request: Request,
    text: str = Form(...),
    session_id: str = Form(default=None),
    generate_audio: bool = Form(default=False),
    input_mode: str = Form(default="text"),
):
    global _active_requests
    _active_requests += 1
    logger.info(f"[CONCURRENCY] Text query queued ({_active_requests}/{MAX_CONCURRENT_REQUESTS})")
    try:
        async with _request_semaphore:
            logger.info(f"[CONCURRENCY] Text query processing ({_active_requests}/{MAX_CONCURRENT_REQUESTS})")
            pipeline = request.app.state.pipeline
            return await pipeline.process_text_query(
                text=text,
                session_id=session_id,
                generate_audio=generate_audio,
            )
    finally:
        _active_requests -= 1


@router.post("/tts")
async def generate_tts(
    request: Request,
    text: str = Form(..., description="Text to convert to speech"),
):
    """On-demand TTS endpoint - called when user clicks Play Audio."""
    from voice.tts_service import TTSService

    tts = request.app.state.tts
    tts_text = TTSService.prepare_tts_text(text)
    if not tts_text:
        return {"answer_audio_base64": None, "audio_format": "mp3"}

    try:
        audio_bytes = tts.synthesize(tts_text)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {"answer_audio_base64": audio_b64, "audio_format": "mp3"}
    except Exception as e:
        logger.error(f"TTS generation error: {e}")
        return {"answer_audio_base64": None, "error": str(e)}


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    pipeline = websocket.app.state.pipeline

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "text")

            try:
                global _active_requests
                _active_requests += 1
                logger.info(f"[CONCURRENCY] WS query queued ({_active_requests}/{MAX_CONCURRENT_REQUESTS})")
                try:
                    async with _request_semaphore:
                        logger.info(f"[CONCURRENCY] WS query processing ({_active_requests}/{MAX_CONCURRENT_REQUESTS})")
                        if msg_type == "audio":
                            audio_b64 = msg.get("audio", "")
                            audio_data = base64.b64decode(audio_b64)
                            result = await pipeline.process_voice_query(
                                audio_data=audio_data,
                                session_id=session_id,
                            )
                        elif msg_type == "clarify_response":
                            original = msg.get("original_query", "")
                            supplement = msg.get("supplement", "")
                            merged = f"{original}（补充信息：{supplement}）"
                            result = await pipeline.process_text_query(
                                text=merged,
                                session_id=session_id,
                            )
                        else:
                            ws_text = msg.get("text", "")
                            result = await pipeline.process_text_query(
                                text=ws_text,
                                session_id=session_id,
                            )
                finally:
                    _active_requests -= 1

                await websocket.send_json({
                    "type": "response",
                    **result,
                })
            except Exception as e:
                logger.error(f"WebSocket processing error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                })
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
