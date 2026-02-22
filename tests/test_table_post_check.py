"""Tests for table lookup post-check validation — badcase 260222 fix."""


from generation.table_post_check import (
    extract_categories_from_answer,
    extract_fire_rating_from_answer,
    extract_ship_type_from_text,
    extract_table_references,
    post_check_table_lookup,
)


class TestExtractShipTypeFromText:
    """Ship type detection from combined query + answer text."""

    def test_tanker_from_chinese(self):
        assert extract_ship_type_from_text("油轮的防火等级") == "tanker"

    def test_tanker_from_english(self):
        assert extract_ship_type_from_text("oil tanker fire integrity") == "tanker"

    def test_tanker_from_flammable(self):
        assert extract_ship_type_from_text("运输可燃液体货物") == "tanker"

    def test_passenger(self):
        assert extract_ship_type_from_text("客船走廊") == "passenger_ship"

    def test_cargo(self):
        assert extract_ship_type_from_text("散货船控制站") == "cargo_ship_non_tanker"

    def test_none(self):
        assert extract_ship_type_from_text("something unrelated") is None


class TestExtractTableReferences:
    """Table reference extraction from answer text."""

    def test_single_table(self):
        assert extract_table_references("根据 Table 9.7，A-0") == ["7"]

    def test_multiple_tables(self):
        refs = extract_table_references("Table 9.5 和 Table 9.7 都适用")
        assert "5" in refs
        assert "7" in refs

    def test_no_table(self):
        assert extract_table_references("没有引用表格") == []


class TestExtractCategories:
    """Category pair extraction from answer text."""

    def test_parenthesized(self):
        assert extract_categories_from_answer("(1)×(2) = A-0") == (1, 2)

    def test_chinese_parentheses(self):
        assert extract_categories_from_answer("（1）×（2）= A-0") == (1, 2)

    def test_category_keyword(self):
        result = extract_categories_from_answer(
            "Category (1) control stations and Category (2) corridors"
        )
        assert result == (1, 2)

    def test_no_categories(self):
        assert extract_categories_from_answer("no categories here") is None


class TestExtractFireRating:
    """Fire rating extraction from answer text."""

    def test_bold_rating(self):
        assert extract_fire_rating_from_answer("答案是 **A-0**") == "A-0"

    def test_plain_rating(self):
        assert extract_fire_rating_from_answer("结果为 A-60") == "A-60"

    def test_prefers_bold(self):
        text = "A-60 是机舱要求，但本场景答案是 **A-0**"
        assert extract_fire_rating_from_answer(text) == "A-0"

    def test_no_rating(self):
        assert extract_fire_rating_from_answer("没有防火等级") is None


class TestPostCheckTableLookup:
    """Integration tests for the full post-check pipeline."""

    def test_no_table_reference(self):
        """No table in answer → no check needed."""
        result = post_check_table_lookup(
            answer="根据SOLAS，需要A-60防火等级",
            query="油轮防火等级",
        )
        assert result["has_table_lookup"] is False
        assert result["should_regenerate"] is False

    def test_tanker_using_table_95_triggers_error(self):
        """Tanker citing Table 9.5 instead of 9.7 → ERROR."""
        result = post_check_table_lookup(
            answer="根据 Table 9.5，Category (1) × Category (2) = **A-0**",
            query="油轮走廊和控制站之间的舱壁防火等级",
        )
        assert result["has_table_lookup"] is True
        assert result["should_regenerate"] is True
        assert any(w["type"] == "table_ship_type_mismatch" for w in result["warnings"])

    def test_tanker_using_table_97_no_error(self):
        """Tanker correctly citing Table 9.7 → no error."""
        result = post_check_table_lookup(
            answer="根据 Table 9.7，Category (1) × Category (2) = **A-0**",
            query="油轮走廊和控制站之间的舱壁防火等级",
        )
        assert result["has_table_lookup"] is True
        assert not any(w["type"] == "table_ship_type_mismatch" for w in result["warnings"])

    def test_cargo_using_table_97_triggers_error(self):
        """Cargo ship citing Table 9.7 instead of 9.5 → ERROR."""
        result = post_check_table_lookup(
            answer="根据 Table 9.7，Category (1) × Category (2) = **A-0**",
            query="散货船走廊和控制站之间的舱壁防火等级",
        )
        assert result["should_regenerate"] is True
        assert any(w["type"] == "table_ship_type_mismatch" for w in result["warnings"])

    def test_known_value_mismatch_triggers_error(self):
        """Answer says A-60 but known value is A-0 → ERROR."""
        result = post_check_table_lookup(
            answer="根据 Table 9.7，(1)×(2) = **A-60**",
            query="油轮走廊和控制站之间的舱壁防火等级",
        )
        assert result["should_regenerate"] is True
        assert any(w["type"] == "table_value_mismatch" for w in result["warnings"])
        assert "A-0" in result["correction_context"]

    def test_known_value_correct_no_error(self):
        """Answer matches known value → no error."""
        result = post_check_table_lookup(
            answer="根据 Table 9.7，(1)×(2) = **A-0**",
            query="油轮走廊和控制站之间的舱壁防火等级",
        )
        assert not any(w["type"] == "table_value_mismatch" for w in result["warnings"])

    def test_bad_case_original_scenario(self):
        """The exact bad case: tanker, Table 9.5, A-60 → double ERROR."""
        result = post_check_table_lookup(
            answer=(
                "根据 SOLAS II-2/Reg 9，Table 9.5 中 Category (1) 控制站 "
                "与 Category (2) 走廊之间的舱壁防火等级为 **A-60**。"
                "消防控制站作为关键安全设施，与走廊之间必须保持最高防火等级。"
            ),
            query="根据SOLAS，对于运输可燃液体货物的轮船，走廊和消防控制站之间的舱壁应该是什么防火等级？",
        )
        assert result["should_regenerate"] is True
        # Should catch BOTH: wrong table AND wrong value
        error_types = {w["type"] for w in result["warnings"] if w["level"] == "ERROR"}
        assert "table_ship_type_mismatch" in error_types
        assert "table_value_mismatch" in error_types

    def test_correction_context_format(self):
        """Correction context should be human-readable for injection."""
        result = post_check_table_lookup(
            answer="根据 Table 9.5，(1)×(2) = **A-60**",
            query="油轮控制站和走廊",
        )
        assert result["correction_context"]
        assert "CORRECTION" in result["correction_context"]
