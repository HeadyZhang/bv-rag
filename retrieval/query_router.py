"""Query intent router for selecting retrieval strategy."""
import re

CONVENTIONS = [
    "SOLAS", "MARPOL", "STCW", "COLREG", "Load Lines", "Tonnage",
    "CLC", "OPRC", "AFS", "BWM", "SAR", "SUA",
]
CODES = [
    "ISM", "ISPS", "LSA", "FSS", "FTP", "IBC", "IGC", "IGF",
    "IMDG", "CSS", "CTU", "HSC", "MODU", "ESP", "Grain", "NOx",
    "OSV", "Polar", "SPS", "IMSBC",
]
CONCEPTS = [
    "fire safety", "pollution prevention", "navigation safety",
    "life saving", "stability", "machinery", "electrical installations",
    "maritime security", "ISM audit", "port state control",
    "oil tanker", "bulk carrier", "passenger ship", "cargo ship",
    "chemical tanker", "gas carrier", "container ship", "ro-ro ship",
    "fishing vessel", "high-speed craft", "MODU", "FPSO",
    "offshore supply vessel",
]

EXACT_REF_PATTERN = re.compile(
    r"(SOLAS|MARPOL|STCW|COLREG|ISM|ISPS|LSA|FSS|FTP|IBC|IGC|IGF)\s*"
    r"(regulation|chapter|annex|rule|part|section)\s*"
    r"[IVXLC\d\-/.]+",
    re.IGNORECASE,
)

RELATION_KEYWORDS = [
    "哪些", "所有", "all related", "which", "修改", "amend",
    "解释", "interpret", "引用", "reference", "适用于", "apply to",
    "相关", "related", "涉及",
]


class QueryRouter:
    def route(self, query: str) -> dict:
        strategy = "hybrid"
        entities = {
            "document_filter": None,
            "concept": None,
            "regulation_ref": None,
        }

        ref_match = EXACT_REF_PATTERN.search(query)
        if ref_match:
            strategy = "keyword"
            entities["regulation_ref"] = ref_match.group(0)

        query_lower = query.lower()
        for conv in CONVENTIONS:
            if conv.lower() in query_lower:
                entities["document_filter"] = conv
                break
        if not entities["document_filter"]:
            for code in CODES:
                if code.lower() in query_lower:
                    entities["document_filter"] = code
                    break

        for concept in CONCEPTS:
            if concept.lower() in query_lower:
                entities["concept"] = concept
                break

        if any(kw.lower() in query_lower for kw in RELATION_KEYWORDS):
            strategy = "hybrid"

        return {"strategy": strategy, "entities": entities}
