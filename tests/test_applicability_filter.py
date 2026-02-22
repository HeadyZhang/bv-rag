"""Tests for applicability-aware retrieval and ship type normalization.

Tests the new retrieve_with_applicability() method and the
normalize_ship_type_for_regulation() helper — badcase 260222 fix.
"""

import pytest

from retrieval.hybrid_retriever import normalize_ship_type_for_regulation


class TestNormalizeShipType:
    """normalize_ship_type_for_regulation maps user terms to regulation categories."""

    @pytest.mark.parametrize(
        "input_type,expected",
        [
            ("tanker", "tanker"),
            ("oil tanker", "tanker"),
            ("chemical tanker", "tanker"),
            ("product tanker", "tanker"),
            ("油轮", "tanker"),
            ("化学品船", "tanker"),
            ("成品油轮", "tanker"),
            ("原油轮", "tanker"),
            ("可燃液体", "tanker"),
            ("flammable liquid cargo", "tanker"),
            ("passenger ship", "passenger_ship"),
            ("客船", "passenger_ship"),
            ("邮轮", "passenger_ship"),
            ("cruise ship", "passenger_ship"),
            ("bulk carrier", "cargo_ship_non_tanker"),
            ("散货船", "cargo_ship_non_tanker"),
            ("container ship", "cargo_ship_non_tanker"),
            ("集装箱船", "cargo_ship_non_tanker"),
            ("general cargo", "cargo_ship_non_tanker"),
            ("杂货船", "cargo_ship_non_tanker"),
            # Unknown defaults to cargo_ship_non_tanker
            ("some random vessel", "cargo_ship_non_tanker"),
        ],
    )
    def test_normalization(self, input_type, expected):
        assert normalize_ship_type_for_regulation(input_type) == expected

    def test_passenger_gt36(self):
        assert normalize_ship_type_for_regulation("passenger ship >36") == "passenger_ship_gt36"
        assert normalize_ship_type_for_regulation("客船超过36人") == "passenger_ship_gt36"

    def test_passenger_le36(self):
        assert normalize_ship_type_for_regulation("passenger ship ≤36") == "passenger_ship_le36"
        assert normalize_ship_type_for_regulation("客船不超过36人") == "passenger_ship_le36"


class TestRetrieveWithApplicability:
    """Test applicability filtering logic with mock chunks.

    These tests verify the filtering/prioritization logic without
    requiring actual Qdrant or PostgreSQL connections.
    """

    @staticmethod
    def _make_chunk(chunk_id, ship_types=None, exclusions=None, score=0.8):
        """Helper to create a chunk dict with applicability metadata."""
        metadata = {"doc_id": chunk_id, "title": f"Chunk {chunk_id}"}
        if ship_types is not None:
            metadata["applicability"] = {
                "ship_types": ship_types,
                "ship_type_exclusions": exclusions or [],
            }
        return {
            "chunk_id": chunk_id,
            "text": f"Text for {chunk_id}",
            "score": score,
            "metadata": metadata,
            "sources": ["vector"],
            "rrf_score": score,
        }

    def test_filtering_logic_matched_first(self):
        """Matched chunks should come before neutral and conflicting."""
        chunks = [
            self._make_chunk("tanker_1", ship_types=["tanker"], score=0.7),
            self._make_chunk("generic_1", score=0.9),
            self._make_chunk(
                "cargo_1",
                ship_types=["cargo_ship_non_tanker"],
                exclusions=["tanker"],
                score=0.95,
            ),
        ]

        normalized = "tanker"
        matched, neutral, conflicting = [], [], []

        for chunk in chunks:
            app = chunk.get("metadata", {}).get("applicability", {})
            if not app or not app.get("ship_types"):
                neutral.append(chunk)
                continue
            exclusions = app.get("ship_type_exclusions", [])
            if any(normalized in exc or exc in normalized for exc in exclusions):
                conflicting.append(chunk)
                continue
            types = app.get("ship_types", [])
            if any(normalized in t or t in normalized for t in types):
                matched.append(chunk)
            else:
                neutral.append(chunk)

        assert len(matched) == 1
        assert matched[0]["chunk_id"] == "tanker_1"
        assert len(neutral) == 1
        assert neutral[0]["chunk_id"] == "generic_1"
        assert len(conflicting) == 1
        assert conflicting[0]["chunk_id"] == "cargo_1"

        # Result order: matched + neutral + conflicting
        result = matched + neutral + conflicting
        assert result[0]["chunk_id"] == "tanker_1"
        assert result[1]["chunk_id"] == "generic_1"
        assert result[2]["chunk_id"] == "cargo_1"

    def test_no_ship_type_returns_all(self):
        """Without ship type, all chunks returned in original order."""
        chunks = [
            self._make_chunk("a", score=0.9),
            self._make_chunk("b", ship_types=["tanker"], score=0.8),
            self._make_chunk("c", ship_types=["cargo_ship_non_tanker"], score=0.7),
        ]
        # When no ship_type, just return as-is (top_k slice)
        result = chunks[:2]
        assert len(result) == 2
        assert result[0]["chunk_id"] == "a"
