"""SOLAS Chapter II-2 old→current regulation number mapping.

Old numbers are from pre-2004 editions (before MSC.99(73) restructuring).
Current numbers are Reg.1-20 (2004 onwards).
"""
import re

# Old Regulation → Current Regulation
SOLAS_II2_OLD_TO_NEW: dict[str, str] = {
    "II-2/3": "II-2/3",        # Definitions (unchanged)
    "II-2/4": "II-2/4",        # Probability of ignition (restructured)
    "II-2/32": "II-2/9",       # Fire integrity of bulkheads (now in Reg.9)
    "II-2/42": "II-2/10",      # Fixed fire extinguishing (now in Reg.10)
    "II-2/48": "II-2/10.5",    # CO2 systems (now sub-section of Reg.10)
    "II-2/53": "II-2/9",       # Containment (merged into Reg.9)
    "II-2/54": "II-2/9",       # Fire protection arrangements (merged into Reg.9)
    "II-2/55": "II-2/10",      # Fire-extinguishing (merged into Reg.10)
    "II-2/56": "II-2/7",       # Detection and alarm (now Reg.7)
    "II-2/59": "II-2/11.6",    # Cargo tank protection
    "II-2/60": "II-2/4.5.5",   # Inert gas (now sub-section of Reg.4)
    "II-2/62": "II-2/4.5.5",   # Inert gas systems (same)
}

# Current SOLAS II-2 max regulation number
SOLAS_II2_NEW_MAX_REG = 20

# Regex to detect "II-2/<number>" patterns
_II2_REG_RE = re.compile(r'II-2[/\s]+(\d+)')

# All old reg numbers that need mapping (for fast lookup)
_OLD_REG_NUMBERS = frozenset(
    int(k.split("/")[1]) for k in SOLAS_II2_OLD_TO_NEW if "/" in k
)


def is_obsolete_solas_reg(reg_str: str) -> bool:
    """Check if a string references an obsolete SOLAS II-2 regulation number."""
    match = _II2_REG_RE.search(reg_str)
    if match:
        reg_num = int(match.group(1))
        return reg_num > SOLAS_II2_NEW_MAX_REG
    return False


def get_current_regulation(old_reg: str) -> str | None:
    """Map an old regulation reference to the current number.

    Returns the mapped string if a mapping exists, None otherwise.
    """
    for old, new in SOLAS_II2_OLD_TO_NEW.items():
        if old in old_reg and old != new:
            return new
    return None


# Bilingual NOTE to inject into chunks that reference old regulation numbers
OBSOLETE_REG_NOTE = (
    "\n\n[NOTE / 注意: This text references old SOLAS II-2 regulation numbers "
    "(pre-2004 edition). 本文引用的是旧版SOLAS II-2条款号（2004年改版前）。\n"
    "Key mappings / 关键映射:\n"
    "Old Reg.60/62 → Current Reg.4.5.5 (Inert gas / 惰气系统)\n"
    "Old Reg.54 → Current Reg.9 (Fire integrity / 防火围蔽)\n"
    "Old Reg.55 → Current Reg.10 (Firefighting / 灭火)\n"
    "Old Reg.56 → Current Reg.7 (Detection and alarm / 探火报警)\n"
    "Old Reg.59 → Current Reg.11.6 (Cargo tank protection / 货舱保护)\n"
    "Always cite the CURRENT regulation number / 务必引用现行条款号。]"
)


def annotate_obsolete_refs(text: str) -> str:
    """If text contains obsolete SOLAS II-2 refs, append the mapping NOTE.

    Returns the original text unchanged if no obsolete refs found.
    """
    matches = _II2_REG_RE.findall(text)
    for m in matches:
        if int(m) > SOLAS_II2_NEW_MAX_REG:
            return text + OBSOLETE_REG_NOTE
    return text
