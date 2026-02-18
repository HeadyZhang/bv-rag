"""Unit tests for QueryEnhancer — maritime terminology mapping."""
import pytest

from retrieval.query_enhancer import QueryEnhancer


@pytest.fixture
def enhancer():
    return QueryEnhancer()


class TestTerminologyMapping:
    """Test Chinese-to-English terminology expansion."""

    def test_fire_division_terms(self, enhancer):
        result = enhancer.enhance("防火分隔等级")
        assert "fire division" in result.lower() or "fire integrity" in result.lower()
        assert "Table 9.3" in result
        assert "Table 9.5" in result

    def test_galley_corridor(self, enhancer):
        result = enhancer.enhance("厨房和走廊之间")
        assert "galley" in result.lower()
        assert "corridor" in result.lower()

    def test_oil_discharge_terms(self, enhancer):
        result = enhancer.enhance("排油限制")
        assert "oil discharge" in result.lower()
        assert "Regulation 34" in result
        assert "1/30000" in result

    def test_air_pipe_terms(self, enhancer):
        result = enhancer.enhance("透气管高度")
        assert "air pipe" in result.lower()
        assert "760 mm" in result
        assert "450 mm" in result

    def test_liferaft_terms(self, enhancer):
        result = enhancer.enhance("救生筏配置")
        assert "liferaft" in result.lower()
        assert "SOLAS III" in result

    def test_bv_classification(self, enhancer):
        result = enhancer.enhance("入级检验要求")
        assert "classification" in result.lower()
        assert "NR467" in result

    def test_iacs_ur(self, enhancer):
        result = enhancer.enhance("统一要求")
        assert "UR" in result
        assert "IACS" in result

    def test_structural_strength(self, enhancer):
        result = enhancer.enhance("结构强度计算")
        assert "structural strength" in result.lower() or "scantling" in result.lower()

    def test_cyber_security(self, enhancer):
        result = enhancer.enhance("网络安全")
        assert "UR E26" in result or "cyber" in result.lower()


class TestRegulationMapping:
    """Test topic -> regulation chapter injection."""

    def test_fire_division_regs(self, enhancer):
        enhancer.enhance("防火分隔")
        assert "SOLAS II-2/9" in enhancer._last_relevant_regs

    def test_oil_discharge_regs(self, enhancer):
        enhancer.enhance("排油")
        assert "MARPOL Annex I/Reg.34" in enhancer._last_relevant_regs

    def test_air_pipe_regs(self, enhancer):
        enhancer.enhance("透气管")
        assert "Load Lines Reg.20" in enhancer._last_relevant_regs

    def test_bv_classification_regs(self, enhancer):
        enhancer.enhance("入级")
        assert "BV NR467" in enhancer._last_relevant_regs


class TestShipTypeAndLength:
    """Test ship type + length -> configuration logic."""

    def test_cargo_ship_lsa(self, enhancer):
        result = enhancer.enhance("货船的救生筏")
        assert "SOLAS III/31" in result
        assert "davit-launched liferaft" in result.lower()

    def test_passenger_ship(self, enhancer):
        result = enhancer.enhance("客船救生设备")
        assert "SOLAS III/21" in result or "SOLAS III/22" in result

    def test_length_85m_threshold(self, enhancer):
        result = enhancer.enhance("90米船的救生筏")
        assert "85 metres" in result
        assert "SOLAS III/31" in result

    def test_bilateral_query(self, enhancer):
        result = enhancer.enhance("两舷的救生筏配置")
        assert "each side" in result
        assert "throw-overboard" in result.lower()
        assert "SOLAS III/31.1.4" in result


class TestEnhancementFormat:
    """Test the output format of enhanced queries."""

    def test_pipe_separator(self, enhancer):
        result = enhancer.enhance("救生筏")
        assert " | " in result

    def test_original_preserved(self, enhancer):
        original = "救生筏配置"
        result = enhancer.enhance(original)
        assert result.startswith(original)

    def test_no_enhancement_for_unknown(self, enhancer):
        result = enhancer.enhance("hello world")
        assert result == "hello world"
