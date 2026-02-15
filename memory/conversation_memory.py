"""Redis-based conversation memory with coreference resolution."""
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field

import anthropic
import redis

from generation.prompts import COREFERENCE_PROMPT, SUMMARIZE_PROMPT

logger = logging.getLogger(__name__)

PRONOUN_INDICATORS = [
    "这个", "那个", "该", "它", "上面", "之前",
    "this", "that", "it", "the above", "same", "these", "those",
    "其", "此",
]


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
        self.anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.max_turns = max_turns
        self.session_ttl = session_ttl_hours * 3600
        self.fast_model = "claude-haiku-4-5-20251001"

    def create_session(self, user_id: str = "anonymous") -> SessionContext:
        session = SessionContext(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
        )
        self._save_session(session)
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

        if metadata and role == "assistant":
            citations = metadata.get("citations", [])
            for c in citations:
                citation_text = c.get("citation", "")
                if citation_text and citation_text not in session.active_regulations:
                    new_regs = [*session.active_regulations, citation_text]
                else:
                    new_regs = list(session.active_regulations)
            if not citations:
                new_regs = list(session.active_regulations)
        else:
            new_regs = list(session.active_regulations)

        new_session = SessionContext(
            session_id=session.session_id,
            user_id=session.user_id,
            turns=new_turns,
            active_regulations=new_regs[-10:],
            active_topics=list(session.active_topics),
            active_ship_type=session.active_ship_type,
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

        enhanced_query = self._resolve_coreferences(session, current_query)

        return messages, enhanced_query

    def _resolve_coreferences(self, session: SessionContext, query: str) -> str:
        query_lower = query.lower()
        has_pronoun = any(p in query_lower for p in PRONOUN_INDICATORS)

        if not has_pronoun or not session.active_regulations:
            return query

        last_exchanges = []
        for turn in session.turns[-6:]:
            last_exchanges.append(f"{turn.role}: {turn.content[:200]}")

        prompt = COREFERENCE_PROMPT.format(
            regulations=session.active_regulations[-5:],
            exchanges="\n".join(last_exchanges),
            query=query,
        )

        try:
            response = self.anthropic_client.messages.create(
                model=self.fast_model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            rewritten = response.content[0].text.strip()
            if rewritten and len(rewritten) > 5:
                logger.info(f"Coreference resolved: '{query}' → '{rewritten}'")
                return rewritten
        except Exception as e:
            logger.warning(f"Coreference resolution failed: {e}")

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
