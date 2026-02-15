"""Voice and text query API routes."""
import base64
import json
import logging

from fastapi import APIRouter, Form, Request, UploadFile, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


@router.post("/query")
async def voice_query(
    request: Request,
    audio: UploadFile,
    session_id: str = Form(default=None),
    language: str = Form(default=None),
):
    pipeline = request.app.state.pipeline
    audio_data = await audio.read()

    result = await pipeline.process_voice_query(
        audio_data=audio_data,
        session_id=session_id,
        audio_format=audio.filename.split(".")[-1] if audio.filename else "webm",
        language=language,
    )

    return result


@router.post("/text-query")
async def text_query(
    request: Request,
    text: str = Form(...),
    session_id: str = Form(default=None),
    generate_audio: bool = Form(default=True),
):
    pipeline = request.app.state.pipeline
    result = await pipeline.process_text_query(
        text=text,
        session_id=session_id,
        generate_audio=generate_audio,
    )
    return result


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
                if msg_type == "audio":
                    audio_b64 = msg.get("audio", "")
                    audio_data = base64.b64decode(audio_b64)
                    result = await pipeline.process_voice_query(
                        audio_data=audio_data,
                        session_id=session_id,
                    )
                else:
                    text = msg.get("text", "")
                    result = await pipeline.process_text_query(
                        text=text,
                        session_id=session_id,
                    )

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
