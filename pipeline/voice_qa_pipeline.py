"""End-to-end voice Q&A pipeline."""
import base64
import logging
import re
import time

from generation.generator import AnswerGenerator
from memory.conversation_memory import ConversationMemory
from retrieval.hybrid_retriever import HybridRetriever
from voice.stt_service import STTService
from voice.tts_service import TTSService

logger = logging.getLogger(__name__)


class VoiceQAPipeline:
    def __init__(
        self,
        stt: STTService,
        tts: TTSService,
        memory: ConversationMemory,
        retriever: HybridRetriever,
        generator: AnswerGenerator,
    ):
        self.stt = stt
        self.tts = tts
        self.memory = memory
        self.retriever = retriever
        self.generator = generator

    async def process_voice_query(
        self,
        audio_data: bytes,
        session_id: str | None = None,
        audio_format: str = "webm",
        language: str | None = None,
        user_id: str = "anonymous",
    ) -> dict:
        timing = {}
        total_start = time.time()

        t0 = time.time()
        stt_result = await self.stt.transcribe(audio_data, audio_format, language)
        transcription = stt_result["text"]
        timing["stt_ms"] = int((time.time() - t0) * 1000)

        result = await self._process_query(
            text=transcription,
            session_id=session_id,
            user_id=user_id,
            input_mode="voice",
            generate_audio=True,
            timing=timing,
        )
        result["transcription"] = transcription
        result["timing"]["total_ms"] = int((time.time() - total_start) * 1000)
        return result

    async def process_text_query(
        self,
        text: str,
        session_id: str | None = None,
        generate_audio: bool = False,
        user_id: str = "anonymous",
    ) -> dict:
        timing = {}
        total_start = time.time()

        result = await self._process_query(
            text=text,
            session_id=session_id,
            user_id=user_id,
            input_mode="text",
            generate_audio=generate_audio,
            timing=timing,
        )
        result["transcription"] = text
        result["timing"]["total_ms"] = int((time.time() - total_start) * 1000)
        return result

    @staticmethod
    def _extract_regulation_ref(meta: dict) -> str:
        """Extract a meaningful regulation reference from chunk metadata.

        The regulation_number field is often empty or too generic (just "SOLAS").
        This extracts specific references like "SOLAS II-1/3-6" from the title.
        """
        title = meta.get("title", "")
        # Try to extract specific regulation references from title
        # e.g. "1 SOLAS Regulation II-1/3-6 – Access to..." → "SOLAS Regulation II-1/3-6"
        pattern = r"(SOLAS|MARPOL|STCW|COLREG|ISM|ISPS|LSA|FSS|IBC|IGC|MSC|MEPC)\s*(?:Regulation\s*)?[\w\-\/\.]+"
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(0).strip()

        # Fall back to document + regulation_number if specific enough
        doc = meta.get("document", "")
        reg_num = meta.get("regulation_number", "")
        if reg_num and reg_num != doc and len(reg_num) > 3:
            return reg_num

        # Fall back to document + condensed title
        if doc and title:
            clean_title = title.strip()[:60].strip()
            return f"{doc}: {clean_title}"

        return ""

    async def _process_query(
        self,
        text: str,
        session_id: str | None,
        user_id: str,
        input_mode: str,
        generate_audio: bool,
        timing: dict,
    ) -> dict:
        t0 = time.time()
        session = None
        if session_id:
            session = self.memory.get_session(session_id)
        if not session:
            session = self.memory.create_session(
                user_id=user_id, session_id=session_id,
            )
        logger.info(
            f"[Pipeline] session={session.session_id}, "
            f"turns={len(session.turns)}, regs={session.active_regulations}"
        )

        messages, enhanced_query = self.memory.build_llm_context(session, text)
        timing["memory_ms"] = int((time.time() - t0) * 1000)

        t0 = time.time()
        retrieved_chunks = self.retriever.retrieve(enhanced_query, top_k=5)
        timing["retrieval_ms"] = int((time.time() - t0) * 1000)

        t0 = time.time()
        user_context = self.memory.get_user_context(session.user_id)
        gen_result = self.generator.generate(
            query=enhanced_query,
            retrieved_chunks=retrieved_chunks,
            conversation_history=messages if messages else None,
            user_context=user_context if user_context else None,
        )
        timing["generation_ms"] = int((time.time() - t0) * 1000)

        answer_audio_base64 = None
        if generate_audio and input_mode == "voice":
            t0 = time.time()
            tts_text = TTSService.prepare_tts_text(gen_result["answer"])
            if tts_text:
                try:
                    audio_bytes = self.tts.synthesize(tts_text)
                    answer_audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
                except Exception as e:
                    logger.error(f"TTS error: {e}")
            timing["tts_ms"] = int((time.time() - t0) * 1000)
        else:
            timing["tts_ms"] = 0

        # Track retrieved regulation references for coreference resolution
        # regulation_number is often empty/generic, so also extract from title
        retrieved_regulations = []
        seen_refs = set()
        for c in retrieved_chunks[:5]:
            meta = c.get("metadata", {})
            ref = self._extract_regulation_ref(meta)
            if ref and ref not in seen_refs:
                seen_refs.add(ref)
                retrieved_regulations.append(ref)
        logger.info(f"[Memory] Saving assistant turn with regs: {retrieved_regulations}")

        session = self.memory.add_turn(
            session, "user", text, input_mode,
            metadata={"enhanced_query": enhanced_query},
        )
        session = self.memory.add_turn(
            session, "assistant", gen_result["answer"], "text",
            metadata={
                "citations": gen_result["citations"],
                "confidence": gen_result["confidence"],
                "retrieved_regulations": retrieved_regulations,
            },
        )

        return {
            "session_id": session.session_id,
            "enhanced_query": enhanced_query,
            "answer_text": gen_result["answer"],
            "answer_audio_base64": answer_audio_base64,
            "citations": gen_result["citations"],
            "confidence": gen_result["confidence"],
            "model_used": gen_result["model_used"],
            "sources": gen_result["sources"],
            "timing": timing,
            "input_mode": input_mode,
        }
