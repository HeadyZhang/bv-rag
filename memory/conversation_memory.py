"""Redis-based conversation memory with industrial-grade coreference resolution."""
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field

import anthropic
import httpx
import redis

from generation.generator import record_llm_usage
from generation.prompts import SUMMARIZE_PROMPT

logger = logging.getLogger(__name__)

REFERENCE_PATTERNS_ZH = [
    "这个", "那个", "该", "它的", "上面", "刚才", "之前",
    "同一个", "相同的", "这条", "那条", "此",
]
REFERENCE_PATTERNS_EN = [
    "this", "that", "it", "its", "the above", "same",
    "this regulation", "that requirement", "the said",
    "aforementioned", "these",
]

CITED_PATTERN = re.compile(
    r"\[(SOLAS|MARPOL|MSC|MEPC|ISM|ISPS|LSA|FSS|Resolution)[^\]]*\]"
)

SHIP_TYPES = {
    "bulk carrier": "散货船",
    "oil tanker": "油轮",
    "passenger ship": "客船",
    "container ship": "集装箱船",
    "fpso": "FPSO",
    "chemical tanker": "化学品船",
    "gas carrier": "气体运输船",
    "roro": "滚装船",
    "cargo ship": "货船",
    "fishing vessel": "渔船",
}


@dataclass
class ConversationTurn:
    turn_id: str
    role: str
    content: str
    timestamp: float
    input_mode: str
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionContext:
    session_id: str
    user_id: str
    turns: list = field(default_factory=list)
    active_regulations: list = field(default_factory=list)
    active_topics: list = field(default_factory=list)
    active_ship_type: str | None = None


class ConversationMemory:
    def __init__(
        self,
        redis_url: str,
        anthropic_api_key: str,
        max_turns: int = 10,
        session_ttl_hours: int = 24,
    ):
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.anthropic_client = anthropic.Anthropic(
            api_key=anthropic_api_key,
            max_retries=3,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        self.max_turns = max_turns
        self.session_ttl = session_ttl_hours * 3600
        self.fast_model = "claude-haiku-4-5-20251001"
        logger.info("ConversationMemory Anthropic client: max_retries=3, timeout=120s")

    def create_session(
        self, user_id: str = "anonymous", session_id: str | None = None,
    ) -> SessionContext:
        session = SessionContext(
            session_id=session_id or str(uuid.uuid4()),
            user_id=user_id,
        )
        self._save_session(session)
        logger.info(
            f"[Memory] Created session: {session.session_id} for user={user_id}"
        )
        return session

    def get_session(self, session_id: str) -> SessionContext | None:
        key = f"session:{session_id}"
        data = self.redis_client.get(key)
        if not data:
            return None
        raw = json.loads(data)
        turns = [ConversationTurn(**t) for t in raw.get("turns", [])]
        return SessionContext(
            session_id=raw["session_id"],
            user_id=raw["user_id"],
            turns=turns,
            active_regulations=raw.get("active_regulations", []),
            active_topics=raw.get("active_topics", []),
            active_ship_type=raw.get("active_ship_type"),
        )

    def add_turn(
        self,
        session: SessionContext,
        role: str,
        content: str,
        input_mode: str = "text",
        metadata: dict | None = None,
    ) -> SessionContext:
        turn = ConversationTurn(
            turn_id=str(uuid.uuid4()),
            role=role,
            content=content,
            timestamp=time.time(),
            input_mode=input_mode,
            metadata=metadata or {},
        )
        new_turns = [*session.turns, turn]
        new_regs = list(session.active_regulations)
        new_topics = list(session.active_topics)
        new_ship_type = session.active_ship_type

        if role == "assistant" and metadata:
            # Track retrieved regulations from the retrieval pipeline
            regs = metadata.get("retrieved_regulations", [])
            for reg in regs:
                if reg and reg not in new_regs:
                    new_regs.append(reg)
            new_regs = new_regs[-20:]

            # Extract cited regulations from answer text
            cited = CITED_PATTERN.findall(content)
            for c in cited:
                if c not in new_regs:
                    new_regs.append(c)

            # Also track citation objects
            citations = metadata.get("citations", [])
            for c in citations:
                citation_text = c.get("citation", "")
                if citation_text and citation_text not in new_regs:
                    new_regs.append(citation_text)

        if role == "user":
            content_lower = content.lower()
            for eng, chn in SHIP_TYPES.items():
                if eng in content_lower or chn in content:
                    new_ship_type = eng
                    if eng not in new_topics:
                        new_topics.append(eng)
                    break

        new_session = SessionContext(
            session_id=session.session_id,
            user_id=session.user_id,
            turns=new_turns,
            active_regulations=new_regs[-20:],
            active_topics=new_topics,
            active_ship_type=new_ship_type,
        )
        logger.info(
            f"[Memory] add_turn: role={role}, session={session.session_id}, "
            f"turns_after={len(new_turns)}, active_regs={new_regs[-5:]}"
        )
        self._save_session(new_session)
        return new_session

    def build_llm_context(
        self,
        session: SessionContext,
        current_query: str,
    ) -> tuple[list[dict], str]:
        recent_turns = session.turns[-(self.max_turns * 2):]

        messages = []
        if len(session.turns) > self.max_turns * 2:
            early_turns = session.turns[:-(self.max_turns * 2)]
            summary = self._summarize(early_turns)
            messages.append({
                "role": "user",
                "content": f"[Earlier conversation summary: {summary}]",
            })
            messages.append({
                "role": "assistant",
                "content": "I understand the context from our earlier discussion.",
            })

        for turn in recent_turns:
            messages.append({"role": turn.role, "content": turn.content})

        enhanced_query = self._resolve_references(current_query, session)

        return messages, enhanced_query

    def _resolve_references(self, query: str, session: SessionContext) -> str:
        """
        Industrial-grade coreference resolution with 3-layer strategy:
        1. Rule layer: fast regex detection, zero latency
        2. Context prefix injection: no query rewriting, attach context prefix
        3. LLM layer: Haiku fallback for complex cases only
        """
        # === Layer 1: detect whether resolution is needed ===
        logger.info(f"[Coreference] Query: {query}")
        logger.info(f"[Coreference] Active regulations: {session.active_regulations}")
        logger.info(f"[Coreference] Session turns count: {len(session.turns)}")

        query_lower = query.lower()
        has_reference = any(
            p in query_lower
            for p in REFERENCE_PATTERNS_ZH + REFERENCE_PATTERNS_EN
        )
        logger.info(f"[Coreference] Has reference: {has_reference}")

        if not has_reference:
            return query

        if not session.active_regulations:
            logger.info("[Coreference] No active regulations, skipping resolution")
            return query

        # === Layer 2: context prefix injection (zero API calls) ===

        # Find the last assistant turn's retrieved regulations
        last_regulations = []
        for turn in reversed(session.turns):
            if turn.role == "assistant":
                last_regulations = turn.metadata.get("retrieved_regulations", [])
                break

        logger.info(f"[Coreference] Last assistant regs: {last_regulations}")

        if last_regulations:
            reg_context = ", ".join(last_regulations[:3])
            enhanced = f"[Context: the previous question was about {reg_context}] {query}"
            logger.info(f"[Coreference] Enhanced query (Layer 2a): {enhanced}")
            return enhanced

        # Fallback to session-level active_regulations
        if session.active_regulations:
            reg_context = ", ".join(session.active_regulations[-3:])
            enhanced = f"[Context: this conversation has discussed {reg_context}] {query}"
            logger.info(f"[Coreference] Enhanced query (Layer 2b): {enhanced}")
            return enhanced

        # === Layer 3: LLM resolution (only if layers 1-2 cannot handle) ===
        if session.turns:
            recent_summary = []
            for turn in session.turns[-6:]:
                content_preview = turn.content[:150]
                if turn.role == "assistant" and turn.metadata:
                    regs = turn.metadata.get("retrieved_regulations", [])
                    if regs:
                        content_preview += f" [Cited: {', '.join(regs[:3])}]"
                recent_summary.append(f"{turn.role}: {content_preview}")

            context_str = "\n".join(recent_summary)

            try:
                response = self.anthropic_client.messages.create(
                    model=self.fast_model,
                    max_tokens=150,
                    messages=[{
                        "role": "user",
                        "content": (
                            "You are resolving pronoun references in a maritime regulation Q&A.\n\n"
                            f"Recent conversation:\n{context_str}\n\n"
                            f"Active regulations discussed: {', '.join(session.active_regulations[-5:])}\n\n"
                            f'New user query: "{query}"\n\n'
                            "Task: Rewrite the query to be fully self-contained by replacing pronouns/references "
                            '("this regulation", "这个规定", "it", "that") with the specific regulation they refer to.\n'
                            "Keep the SAME language as the original query.\n"
                            "If the query is already clear, return it unchanged.\n\n"
                            "IMPORTANT: The reference most likely points to regulations from the LAST assistant response.\n"
                            "Only output the rewritten query, nothing else."
                        ),
                    }],
                )
                record_llm_usage(
                    model=self.fast_model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    query_preview=f"[coreference] {query}",
                )
                result = response.content[0].text.strip().strip("\"'")
                if len(result) < len(query) * 3 and len(result) > 5:
                    logger.info(f"[Coreference] Enhanced query (Layer 3 LLM): {result}")
                    return result
            except Exception as e:
                logger.warning(f"LLM coreference resolution failed: {e}")

        return query

    def _summarize(self, turns: list[ConversationTurn]) -> str:
        conversation_text = "\n".join(
            f"{t.role}: {t.content[:300]}" for t in turns
        )
        try:
            response = self.anthropic_client.messages.create(
                model=self.fast_model,
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"{SUMMARIZE_PROMPT}\n\n{conversation_text}",
                }],
            )
            record_llm_usage(
                model=self.fast_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                query_preview="[summarize]",
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return "Previous maritime regulation discussion."

    def update_user_profile(self, user_id: str, session: SessionContext):
        key = f"user_profile:{user_id}"
        existing = self.redis_client.get(key)
        profile = json.loads(existing) if existing else {
            "total_queries": 0,
            "regulation_counts": {},
            "ship_types": {},
        }

        profile["total_queries"] = profile.get("total_queries", 0) + len(
            [t for t in session.turns if t.role == "user"]
        )

        for reg in session.active_regulations:
            profile["regulation_counts"][reg] = profile["regulation_counts"].get(reg, 0) + 1

        if session.active_ship_type:
            st = session.active_ship_type
            profile["ship_types"][st] = profile["ship_types"].get(st, 0) + 1

        self.redis_client.set(key, json.dumps(profile))

    def get_user_context(self, user_id: str) -> str:
        key = f"user_profile:{user_id}"
        data = self.redis_client.get(key)
        if not data:
            return ""

        profile = json.loads(data)
        reg_counts = profile.get("regulation_counts", {})
        if not reg_counts:
            return ""

        top_regs = sorted(reg_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        parts = [f"{reg}({count}次)" for reg, count in top_regs]
        return f"用户常查法规: {', '.join(parts)}"

    def _save_session(self, session: SessionContext):
        key = f"session:{session.session_id}"
        data = {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "turns": [asdict(t) for t in session.turns],
            "active_regulations": session.active_regulations,
            "active_topics": session.active_topics,
            "active_ship_type": session.active_ship_type,
        }
        self.redis_client.setex(key, self.session_ttl, json.dumps(data, ensure_ascii=False))
