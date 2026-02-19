"""URL mappings for BV Rules and IMO regulations.

Used by the reference link generator to produce clickable source links.
"""
import re

BV_RULES_URLS: dict[str, dict] = {
    "NR467": {
        "name": "Rules for the Classification of Steel Ships",
        "base_url": "https://marine-offshore.bureauveritas.com/nr467-rules-classification-steel-ships",
    },
    "NR670": {
        "name": "Rules for the Classification of Methanol-fuelled Ships",
        "base_url": "https://marine-offshore.bureauveritas.com/nr670-rules-classification-methanol-fuelled-ships",
    },
    "NR217": {
        "name": "Rules for the Classification of Inland Navigation Vessels",
        "base_url": "https://marine-offshore.bureauveritas.com/nr217",
    },
    "NR529": {
        "name": "Gas-Fuelled Ships",
        "base_url": "https://marine-offshore.bureauveritas.com/nr529",
    },
    "NR216": {
        "name": "Rules on Materials and Welding",
        "base_url": "https://marine-offshore.bureauveritas.com/nr216",
    },
}

IMO_URLS: dict[str, str] = {
    "SOLAS": "https://www.imorules.com",
    "MARPOL": "https://www.imorules.com",
    "ICLL": "https://www.imorules.com",
    "STCW": "https://www.imorules.com",
    "COLREG": "https://www.imorules.com",
    "LSA": "https://www.imorules.com",
    "FSS": "https://www.imorules.com",
    "ISM": "https://www.imorules.com",
    "ISPS": "https://www.imorules.com",
    "MSC": "https://www.imorules.com",
    "MEPC": "https://www.imorules.com",
}

_NR_PATTERN = re.compile(r"NR\s*(\d+)", re.IGNORECASE)


def generate_reference_url(regulation_ref: str) -> str:
    """Generate a clickable URL for a regulation reference.

    Examples:
        "BV NR467 Part C, 2.7.6(g)" -> BV website NR467 page
        "SOLAS II-2/9 Table 9.5"    -> imorules.com
        "NR999"                      -> BV search page
    """
    nr_match = _NR_PATTERN.search(regulation_ref)
    if nr_match:
        nr_num = f"NR{nr_match.group(1)}"
        if nr_num in BV_RULES_URLS:
            return BV_RULES_URLS[nr_num]["base_url"]
        return (
            f"https://marine-offshore.bureauveritas.com/rules-guidelines?search={nr_num}"
        )

    for imo_key, url in IMO_URLS.items():
        if imo_key.lower() in regulation_ref.lower():
            return url

    return ""
