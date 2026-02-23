"""Tests for missing tables logger — Section 9.2 of the ingestion plan."""

import json

from generation.missing_tables_logger import (
    _extract_possible_table_refs,
    log_if_missing_table,
)


class TestExtractPossibleTableRefs:
    def test_table_ref(self):
        refs = _extract_possible_table_refs("Table 9.5 数据")
        assert "Table 9.5" in refs

    def test_regulation_ref(self):
        refs = _extract_possible_table_refs("Reg 21 救生设备")
        assert any("Reg 21" in r for r in refs)

    def test_no_ref(self):
        refs = _extract_possible_table_refs("no references here")
        assert refs == []


class TestLogIfMissingTable:
    def test_no_missing_pattern(self):
        result = log_if_missing_table(
            query="油轮防火等级",
            answer="根据 SOLAS II-2/Reg 9, Table 9.7, A-0",
        )
        assert result is False

    def test_detects_chinese_missing(self):
        result = log_if_missing_table(
            query="散货船甲板防火等级 Table 9.6",
            answer="未检索到 Table 9.6 的完整数据",
        )
        assert result is True

    def test_detects_not_found(self):
        result = log_if_missing_table(
            query="test query",
            answer="未找到相关法规内容",
        )
        assert result is True

    def test_detects_model_knowledge(self):
        result = log_if_missing_table(
            query="test query",
            answer="基于模型知识，答案是...",
        )
        assert result is True

    def test_writes_jsonl(self, tmp_path, monkeypatch):
        log_file = tmp_path / "test_log.jsonl"
        monkeypatch.setattr(
            "generation.missing_tables_logger.LOG_FILE",
            log_file,
        )
        log_if_missing_table(
            query="Table 9.8 油轮甲板防火",
            answer="未检索到 Table 9.8 相关数据",
            session_id="test-session",
        )
        assert log_file.exists()
        record = json.loads(log_file.read_text().strip())
        assert record["missing_reference"] == "Table 9.8"
        assert record["session_id"] == "test-session"
        assert "timestamp" in record
