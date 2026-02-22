"""Tests for ship type extraction from queries — badcase 260222 fix."""

import pytest

from retrieval.query_enhancer import QueryEnhancer


@pytest.fixture
def enhancer():
    return QueryEnhancer()


class TestExtractShipTypeFromQuery:
    """extract_ship_type_from_query must correctly classify ship types."""

    # --- Tanker detection ---

    @pytest.mark.parametrize(
        "query",
        [
            "油轮走廊和控制站之间的舱壁防火等级",
            "对于oil tanker，控制站和走廊之间的舱壁防火等级",
            "化学品船的机舱和居住区之间",
            "运输可燃液体货物的轮船，走廊和消防控制站之间",
            "成品油轮需要配备惰气系统吗",
            "chemical tanker fire integrity requirements",
            "flammable liquid cargo vessel fire rating",
        ],
    )
    def test_tanker_detection(self, enhancer, query):
        result = enhancer.extract_ship_type_from_query(query)
        assert result == "tanker", f"Expected 'tanker' for: {query}"

    # --- Passenger ship detection ---

    @pytest.mark.parametrize(
        "query",
        [
            "客船走廊和控制站之间的防火等级",
            "passenger ship corridor fire integrity",
            "邮轮防火分隔要求",
        ],
    )
    def test_passenger_detection(self, enhancer, query):
        result = enhancer.extract_ship_type_from_query(query)
        assert result == "passenger_ship", f"Expected 'passenger_ship' for: {query}"

    # --- Non-tanker cargo ship detection ---

    @pytest.mark.parametrize(
        "query",
        [
            "散货船控制站和走廊之间的防火等级",
            "集装箱船机舱和居住区之间的防火分隔",
            "bulk carrier corridor fire integrity",
            "杂货船防火等级要求",
            "货船走廊和控制站之间的舱壁防火等级",
        ],
    )
    def test_cargo_non_tanker_detection(self, enhancer, query):
        result = enhancer.extract_ship_type_from_query(query)
        assert result == "cargo_ship_non_tanker", f"Expected 'cargo_ship_non_tanker' for: {query}"

    # --- Unknown / no ship type ---

    @pytest.mark.parametrize(
        "query",
        [
            "走廊和控制站之间的防火等级是多少",
            "SOLAS对防火分隔的要求",
            "fire integrity requirements",
        ],
    )
    def test_no_ship_type(self, enhancer, query):
        result = enhancer.extract_ship_type_from_query(query)
        assert result is None, f"Expected None for: {query}"

    # --- Critical bad case: "运输可燃液体货物的轮船" must be tanker ---

    def test_bad_case_flammable_liquid_cargo(self, enhancer):
        """The original bad case query that triggered this entire fix."""
        query = "根据SOLAS，对于运输可燃液体货物的轮船，走廊和消防控制站之间的舱壁应该是什么防火等级？"
        result = enhancer.extract_ship_type_from_query(query)
        assert result == "tanker"


class TestFireDivisionTableInjection:
    """Query enhancement should inject correct fire tables per ship type."""

    def test_tanker_fire_query_injects_table_97(self, enhancer):
        result = enhancer.enhance("油轮走廊和控制站之间的防火等级")
        assert "Table 9.7" in result
        assert "Table 9.5" not in result

    def test_cargo_fire_query_injects_table_95(self, enhancer):
        result = enhancer.enhance("散货船走廊和控制站之间的防火等级")
        assert "Table 9.5" in result
        assert "Table 9.7" not in result

    def test_passenger_fire_query_injects_table_91(self, enhancer):
        result = enhancer.enhance("客船走廊和控制站之间的防火等级")
        assert "Table 9.1" in result

    def test_generic_fire_query_injects_multiple_tables(self, enhancer):
        """Without ship type, should inject broad table coverage."""
        result = enhancer.enhance("走廊和控制站之间的防火等级")
        # Should include tables for multiple ship types
        assert "Table 9.5" in result or "Table 9.7" in result or "Table 9.1" in result
