"""Unit tests for ClarificationChecker — slot-filling for maritime queries."""
import pytest

from retrieval.clarification_checker import ClarificationChecker


@pytest.fixture
def checker():
    return ClarificationChecker()


class TestTopicDetection:
    """Test automatic topic detection from query text."""

    def test_fire_division(self, checker):
        assert checker.detect_topic("防火分隔等级") == "fire_division"

    def test_fire_integrity(self, checker):
        assert checker.detect_topic("fire integrity between galley and corridor") == "fire_division"

    def test_oil_discharge(self, checker):
        assert checker.detect_topic("排油限制") == "oil_discharge"

    def test_odme(self, checker):
        assert checker.detect_topic("ODME系统要求") == "oil_discharge"

    def test_equipment(self, checker):
        assert checker.detect_topic("是否需要配备灭火器") == "equipment_requirement"

    def test_no_topic(self, checker):
        assert checker.detect_topic("什么是SOLAS") is None


class TestClarificationNeeded:
    """Test whether clarification is correctly triggered."""

    def test_fire_division_no_ship_type(self, checker):
        needs, questions = checker.check("applicability", {}, "防火分隔等级", "fire_division")
        assert needs is True
        slots = [q["slot"] for q in questions]
        assert "ship_type" in slots

    def test_fire_division_with_ship_type(self, checker):
        needs, _ = checker.check(
            "applicability",
            {"ship_type": "cargo"},
            "货船防火分隔等级",
            "fire_division",
        )
        assert needs is False

    def test_oil_discharge_no_source(self, checker):
        needs, questions = checker.check("specification", {}, "排油限制", "oil_discharge")
        assert needs is True
        slots = [q["slot"] for q in questions]
        assert "discharge_source" in slots

    def test_oil_discharge_with_keywords(self, checker):
        # "货舱区" satisfies discharge_source, but "specification" also needs ship_type
        # So we pass ship_type in ship_info to isolate the discharge_source test
        needs, _ = checker.check(
            "specification",
            {"type": "tanker"},
            "货舱区排油限制",
            "oil_discharge",
        )
        assert needs is False

    def test_definition_no_clarification(self, checker):
        needs, _ = checker.check("definition", {}, "什么是SOLAS", None)
        assert needs is False

    def test_procedure_no_clarification(self, checker):
        needs, _ = checker.check("procedure", {}, "如何进行检验", None)
        assert needs is False

    def test_supplement_bypass(self, checker):
        needs, _ = checker.check("applicability", {}, "补充信息：货船", None)
        assert needs is False


class TestSlotDetection:
    """Test _has_slot correctly identifies slot values in queries."""

    def test_ship_type_from_info(self, checker):
        assert checker._has_slot("ship_type", {"type": "cargo"}, "货船") is True

    def test_ship_type_from_query(self, checker):
        assert checker._has_slot("ship_type", {}, "这是一艘油轮") is True

    def test_ship_type_missing(self, checker):
        assert checker._has_slot("ship_type", {}, "防火分隔等级") is False

    def test_tonnage_from_query(self, checker):
        assert checker._has_slot("tonnage_or_length", {}, "500总吨") is True

    def test_tonnage_from_length(self, checker):
        assert checker._has_slot("tonnage_or_length", {}, "90米") is True

    def test_discharge_source_cargo_tank(self, checker):
        assert checker._has_slot("discharge_source", {}, "货舱区排油") is True

    def test_discharge_source_bilge(self, checker):
        assert checker._has_slot("discharge_source", {}, "机舱舱底水") is True
