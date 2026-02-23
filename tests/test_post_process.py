"""Tests for generation/post_process.py — source link fixing."""
import pytest

from generation.post_process import fix_source_links


@pytest.fixture
def sample_sources():
    return [
        {
            "chunk_id": "c1",
            "url": "https://www.imorules.com/GUID-5765BBD5-1234.html",
            "breadcrumb": "SOLAS II-2 Fire integrity - Reg 9 Table 9.5",
            "score": 0.9,
        },
        {
            "chunk_id": "c2",
            "url": "https://www.imorules.com/GUID-ABCD-5678.html",
            "breadcrumb": "MARPOL Annex I Regulation 15",
            "score": 0.85,
        },
        {
            "chunk_id": "c3",
            "url": "",
            "breadcrumb": "STCW Chapter II Section A-II/1",
            "score": 0.7,
        },
    ]


class TestFixSourceLinks:
    def test_replaces_generic_imorules_link(self, sample_sources):
        answer = "[SOLAS II-2/Reg 9] → www.imorules.com Fire integrity"
        result = fix_source_links(answer, sample_sources)
        # Generic "www.imorules.com Fire integrity" replaced with specific GUID URL
        assert "GUID-5765BBD5-1234" in result
        assert "Fire integrity" not in result  # trailing text removed
        assert "SOLAS II-2/Reg 9" in result

    def test_replaces_with_specific_url_when_available(self, sample_sources):
        answer = "[SOLAS II-2/Reg 9] → www.imorules.com Fire integrity"
        result = fix_source_links(answer, sample_sources)
        assert "GUID-5765BBD5-1234" in result

    def test_removes_generic_link_when_no_match(self):
        answer = "[Unknown Regulation XYZ] → www.imorules.com something"
        result = fix_source_links(answer, [])
        assert "www.imorules.com" not in result
        assert "[Unknown Regulation XYZ]" in result

    def test_specific_url_not_stripped(self, sample_sources):
        # A specific URL with path should not be treated as generic
        answer = "See regulation at https://www.imorules.com/GUID-REAL-URL.html for details."
        result = fix_source_links(answer, sample_sources)
        # The GUID URL is specific, not generic — should be preserved
        assert "GUID-REAL-URL" in result

    def test_handles_https_prefix(self, sample_sources):
        answer = "[SOLAS II-2/Reg 9] → https://imorules.com general page"
        result = fix_source_links(answer, sample_sources)
        assert "https://imorules.com" not in result or "GUID" in result

    def test_handles_answer_without_links(self, sample_sources):
        answer = "This is a plain answer without any links."
        result = fix_source_links(answer, sample_sources)
        assert result == answer

    def test_handles_multiple_links(self, sample_sources):
        answer = (
            "[SOLAS II-2/Reg 9] → www.imorules.com Fire integrity\n"
            "[MARPOL Annex I/15] → www.imorules.com Oil discharge"
        )
        result = fix_source_links(answer, sample_sources)
        # Generic trailing descriptions should be removed
        assert "Fire integrity" not in result
        assert "Oil discharge" not in result
        # Both refs should still be present with specific URLs
        assert "SOLAS II-2/Reg 9" in result
        assert "MARPOL Annex I/15" in result
        assert "GUID-5765BBD5-1234" in result
        assert "GUID-ABCD-5678" in result

    def test_empty_sources_removes_generic(self):
        answer = "[SOLAS II-2/Reg 9] → www.imorules.com"
        result = fix_source_links(answer, [])
        assert "www.imorules.com" not in result
        assert "[SOLAS II-2/Reg 9]" in result

    def test_none_sources_removes_generic(self):
        answer = "[SOLAS III/31] → www.imorules.com Life-saving"
        result = fix_source_links(answer, None)
        assert "www.imorules.com" not in result
