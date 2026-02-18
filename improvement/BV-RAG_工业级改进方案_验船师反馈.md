# BV-RAG 工业级改进方案：基于验船师反馈的三维升级

## Context

5 道验船师实战题测试暴露了系统的**四类**核心问题：

1. **实务知识库有错误**：T103 的 `free_fall_lifeboat_exemption` 条目说"有 free-fall 就不需要 davit"，但验船师和 SOLAS III/31.1.2.2 原文明确写"The liferafts on **at least one side** of the ship shall be served by launching appliances"——即使有 free-fall，也需要至少一舷 davit。
2. **缺少关键维度分辨**：防火分隔(T101/T102)答案取决于船型(客船>36人/客船≤36人/货船非tanker/tanker)、吨位、建造日期，但系统既没问、也没按条件分支回答。
3. **关键法规检索缺失**：SOLAS II-2/9 Table 9.3/9.5（防火分隔主表）和 MARPOL Annex I Reg.34（排油限制 1/30000）未被检索到。
4. **RAG 锚定效应（最根本问题）**：当检索结果质量差时，RAG 反而比不用 RAG 更差。系统强制 LLM 基于检索结果回答，当检索到的是 MODU Code（海上钻井平台法规）而非 SOLAS II-2/9 时，LLM 被"锚定"到错误法规上编造答案。直接问 Gemini 裸模型（无 RAG）反而能用参数化知识正确回答——因为没有错误上下文的干扰。**本质**：当前系统是 always-retrieve-always-use，缺少"检索质量评估 + 自适应降级"机制。

本方案分 **四个阶段** 实施，优先级从高到低。

---

## Phase 1: 紧急修复 — 实务知识库纠错 + System Prompt 强化

### 1.1 修复错误的实务知识库条目

**文件**: `knowledge/practical/lifesaving.yaml`

**修改内容**:

**(A) `free_fall_lifeboat_exemption` 条目 — 纠正核心错误:**

```yaml
- id: free_fall_lifeboat_exemption
  title: "自由降落救生艇的配置影响"
  correct_interpretation: >
    配备 free-fall lifeboat（容纳100%人员）后，仍需要在每舷配备救生筏，
    且至少一舷的救生筏必须由降落设备(davit)提供服务。
    SOLAS III/31.1.2.2 原文："The liferafts on at least one side of the ship
    shall be served by launching appliances."
    所以正确配置是：free-fall lifeboat + 至少一舷 davit-launched liferaft + 另一舷可 throw-overboard。
  common_mistake: >
    认为有了 free-fall lifeboat 就两舷都不需要 davit。
    错误！即使有 free-fall，仍需至少一舷 davit-launched liferaft。
  typical_configurations:
    - "标准配置：船尾 free-fall lifeboat + 一舷 davit-launched liferaft + 另一舷 throw-overboard liferaft"
    - "无 free-fall：一舷 davit-launched liferaft + 另一舷 throw-overboard liferaft"
  decision_tree:
    - "Step 1: 确认船型（货船 vs 客船）"
    - "Step 2: 确认船长（≥85m 适用 SOLAS III/31.1.4）"
    - "Step 3: 是否有 free-fall lifeboat？"
    - "Step 4: 有 free-fall → 仍需至少一舷 davit-launched liferaft（SOLAS III/31.1.2.2）"
    - "Step 5: 无 free-fall → 一舷必须有 davit-launched，另一舷可 throw-overboard"
```

**(B) `cargo_liferaft_davit` 条目 — 同步纠正"最常见配置":**

```yaml
typical_configurations:
  - "最常见配置：船尾 free-fall lifeboat + 一舷 davit-launched liferaft + 另一舷 throw-overboard liferafts"
  - "无 free-fall 配置：一舷 davit + davit-launched liferaft，另一舷 throw-overboard liferaft"
```

---

**文件**: `knowledge/practical/fire_safety.yaml`

**(C) 新增 `fire_division_table` 条目 — 验船师指出的分隔表条件维度:**

```yaml
- id: fire_division_table
  title: "防火分隔等级查表方法（SOLAS II-2/9 Table 9.3/9.5）"
  keywords: ["防火分隔", "防火等级", "A级", "B级", "舱壁", "甲板", "厨房", "走廊", "驾驶室"]
  terms: ["fire division", "fire integrity", "bulkhead", "deck", "Table 9.3", "Table 9.5"]
  regulations: ["SOLAS II-2/9", "SOLAS II-2/3"]
  ship_types: ["all"]
  correct_interpretation: >
    防火分隔等级必须查 SOLAS II-2/9 的表格，不能凭推测。
    Table 9.1/9.2 = 客船(>36人)的舱壁/甲板分隔；
    Table 9.3/9.4 = 客船(≤36人)及货船的舱壁/甲板分隔；
    Table 9.5/9.6 = 油轮(tanker)的舱壁/甲板分隔。
    首先确定船型和适用哪张表，然后确定两侧处所的类别(category)，查表得到等级。
  common_mistake: >
    不区分船型直接回答防火等级。不同船型(客船>36人/客船≤36人/货船/tanker)使用不同的分隔表，
    答案可能完全不同。如果用户没有指明船型，必须先确认。
  decision_tree:
    - "Step 1: 确认船型 → 客船(>36人)用Table 9.1/9.2, 客船(≤36人)/货船用Table 9.3/9.4, tanker用Table 9.5/9.6"
    - "Step 2: 确认建造日期（合同日期、安放龙骨日期）→ 不同年代的表格版本可能不同"
    - "Step 3: 确定每侧处所的类别(category) → 如控制站=类别(1), 走廊=类别(2), 起居处所=类别(3等), 服务处所=类别(9等)"
    - "Step 4: 在对应表格中交叉查找两个类别 → 得到分隔等级(A-60/A-30/A-15/A-0/B-15/B-0/C)"
    - "Step 5: 垂直分隔(甲板)和水平分隔(舱壁)可能等级不同，需分别查表"
```

---

**文件**: `knowledge/practical/marpol.yaml`

**(D) 新增 `odme_discharge_limit` 条目:**

```yaml
- id: odme_discharge_limit
  title: "油轮货舱区排油限制（MARPOL Annex I Reg.34）"
  keywords: ["排油", "ODME", "油轮", "排放限制", "总排油量"]
  terms: ["oil discharge", "ODME", "cargo tank", "1/30000", "discharge limit"]
  regulations: ["MARPOL Annex I/Reg.34"]
  ship_types: ["tanker", "oil tanker", "油轮"]
  correct_interpretation: >
    油轮货舱区排油必须同时满足以下全部条件(MARPOL Annex I Reg.34)：
    1. 不在特殊区域内；2. 距最近陆地>50海里；3. 航行中；
    4. 瞬时排油速率≤30升/海里；
    5. 总排油量：1979年12月31日后交付的船=不超过该批货油总量的1/30,000；
       1979年12月31日前交付的船=不超过1/15,000；
    6. 船上ODME和污油舱布置正在运行中。
  common_mistake: >
    认为油轮排油只要浓度≤15ppm就行。15ppm是机舱舱底水(OWS)的标准(Reg.15)，
    不是货舱区排油的标准。货舱区排油用的是总量比(1/30,000)和速率(30L/nmile)控制。
  decision_tree:
    - "Step 1: 确认是货舱区排油还是机舱舱底水排油"
    - "Step 2: 货舱区 → MARPOL Reg.34, 总量≤1/30,000, 速率≤30L/nmile"
    - "Step 3: 机舱舱底水 → MARPOL Reg.15, 浓度≤15ppm"
    - "Step 4: 确认船舶交付日期(1979年12月31日前/后)决定1/15,000还是1/30,000"
```

---

### 1.2 System Prompt 强化 — 强制条件分支回答

**文件**: `generation/prompts.py`

在 SYSTEM_PROMPT 的 "### 1. 结论先行" 之后插入新章节：

```markdown
### 1.5 条件维度强制声明（CRITICAL — 必须遵守）
- 海事法规的适用性往往取决于多个条件维度，你必须明确每个维度：
  * **船型**：客船(>36人) / 客船(≤36人) / 货船(非tanker) / tanker(油轮/化学品船/气体船)
  * **吨位/船长**：不同吨位和船长有不同的阈值要求
  * **建造日期**：合同日期(contract date)、安放龙骨日期(keel laying)、交付日期(delivery date)可能触发不同版本的法规
  * **航区**：国际航行 / 国内航行 / 特殊区域(Special Areas)
- 如果用户没有提供这些信息，你必须在回答开头用加粗文字声明你的假设：
  "**以下回答基于：[货船/国际航行/2010年后建造] 的假设。如果您的船舶条件不同，结论可能改变。**"
- 对于防火分隔问题，必须指出使用的是哪张表：
  * 客船(>36人) → Table 9.1(舱壁)/Table 9.2(甲板)
  * 客船(≤36人)及货船 → Table 9.3(舱壁)/Table 9.4(甲板)
  * 油轮(tanker) → Table 9.5(舱壁)/Table 9.6(甲板)
- 对于排油问题，必须区分：
  * 货舱区排油 → MARPOL Annex I Reg.34 (总量 1/30,000, 速率 ≤30L/nmile)
  * 机舱舱底水 → MARPOL Annex I Reg.15 (浓度 ≤15ppm)
- 绝不混淆不同船型或不同法规条款的适用范围

### 1.6 检索质量自评 + 自适应降级（CRITICAL — 解决"RAG 不如裸模型"问题）
- 在回答前，先评估检索到的内容是否真的包含了回答所需的**核心法规条文**
- 如果检索结果中没有直接相关的法规（例如问防火分隔但没有检索到 SOLAS II-2/9 Table 9.3），你应该：
  1. **基于你自身的专业知识回答**，不要从无关法规中拼凑答案
  2. 在回答末尾标注："⚠ 注意：检索结果中未找到直接对应的法规原文（如 SOLAS II-2/9 Table 9.3），以上回答基于模型知识，建议核实原文"
- **绝对禁止**：为了"引用检索结果"而从无关法规（如 MODU Code、SCV Code 等）中强行提取答案
- 判断标准：
  * 检索到的法规标题/breadcrumb 是否与问题直接相关？
  * 是否检索到了核心条文（而不是外围的 Circular 或 Interpretation）？
  * 如果 top-3 的 breadcrumb 全部来自 MODU Code 或 SCV Code 等特殊船型法规，而用户问的是普通商船，说明检索失效
- 宁可承认"检索未命中关键法规"并用自身知识回答，也不要被错误的检索结果带偏
```

---

### 1.3 QueryEnhancer 扩展 — 防火和MARPOL术语映射

**文件**: `retrieval/query_enhancer.py`

在 `TERMINOLOGY_MAP` 中新增：

```python
# Fire safety - structural
"防火分隔": ["fire division", "fire integrity", "A-class division", "B-class division", "structural fire protection"],
"防火等级": ["fire rating", "fire integrity", "structural fire protection"],
"厨房": ["galley", "cooking area", "service space"],
"走廊": ["corridor", "passageway", "escape route"],
"驾驶室": ["wheelhouse", "navigation bridge", "control station"],
"住舱": ["accommodation space", "cabin", "crew quarters"],
# MARPOL - discharge
"排油": ["oil discharge", "ODME", "discharge monitoring", "oily mixture"],
"排放": ["discharge", "disposal"],
# Load Lines - ventilation
"透气管": ["air pipe", "vent pipe", "tank vent"],
"上层建筑": ["superstructure", "superstructure deck"],
```

在 `TOPIC_TO_REGULATIONS` 中新增：

```python
"fire division": ["SOLAS II-2/9", "SOLAS II-2/3"],
"fire integrity": ["SOLAS II-2/9", "SOLAS II-2/3"],
"fire rating": ["SOLAS II-2/9", "SOLAS II-2/3"],
"galley": ["SOLAS II-2/9"],
"corridor": ["SOLAS II-2/9"],
"control station": ["SOLAS II-2/9"],
"oil discharge": ["MARPOL Annex I/Reg.34", "MARPOL Annex I/Reg.15"],
"ODME": ["MARPOL Annex I/Reg.34", "MEPC.108(49)"],
"air pipe": ["Load Lines Reg.20", "ILLC 1966/1988"],
```

---

## Phase 2: 多轮澄清 Agent — 当用户问题缺乏关键维度时主动追问

### 2.1 架构设计

采用 **Anthropic Tool-Use 模式**（不引入 LangGraph 等外部框架），基于现有 Claude API + WebSocket 实现。

核心决策：**不使用 LangGraph**，原因是当前项目已经用 FastAPI + WebSocket + Redis Session 建立了完整的会话管理，引入 LangGraph 会增加不必要的复杂度。直接在现有 pipeline 中插入一个确定性的"槽位检查器"即可。

```
User Query
    ↓
[QueryClassifier] → intent + ship_info + topic
    ↓
[ClarificationChecker] → 检查必需维度是否缺失
    ↓
  [完整] → 正常 RAG 流程 → 回答
  [缺失] → 生成澄清问题 → 返回给前端
                ↓
           用户补充信息
                ↓
           合并到原始查询 → 正常 RAG 流程 → 回答
```

---

### 2.2 新增文件: `retrieval/clarification_checker.py`

#### 完整实现

```python
"""Check if a query needs clarification before retrieval.

Maritime regulatory answers depend on multiple conditional dimensions:
ship type, tonnage, construction date, voyage type, etc.
This module detects when critical dimensions are missing and generates
targeted clarification questions.
"""
import re

# Required dimensional slots per intent type
REQUIRED_SLOTS: dict[str, dict[str, list[str]]] = {
    "applicability": {
        "critical": ["ship_type"],
        "important": ["tonnage_or_length"],
        "optional": ["construction_date", "voyage_type"],
    },
    "specification": {
        "critical": ["ship_type"],
        "important": [],
        "optional": ["tonnage_or_length"],
    },
    "procedure": {
        "critical": [],
        "important": [],
        "optional": ["ship_type"],
    },
    "comparison": {
        "critical": [],
        "important": ["ship_type"],
        "optional": [],
    },
    "definition": {
        "critical": [],
        "important": [],
        "optional": [],
    },
}

# Topic-specific additional slots
TOPIC_EXTRA_SLOTS: dict[str, dict[str, list[str]]] = {
    "fire_division": {
        "critical": ["ship_type"],
        "important": ["construction_date"],
    },
    "oil_discharge": {
        "critical": ["discharge_source"],
        "important": ["delivery_date"],
    },
    "equipment_requirement": {
        "critical": ["ship_type", "tonnage_or_length"],
        "important": ["voyage_type"],
    },
}

# Topic detection patterns
TOPIC_TRIGGERS: dict[str, list[str]] = {
    "fire_division": [
        "防火分隔", "防火等级", "A级", "B级", "A-0", "A-15", "A-30", "A-60",
        "B-0", "B-15", "fire division", "fire integrity", "fire rating",
    ],
    "oil_discharge": [
        "排油", "ODME", "排放.*油", "discharge.*oil", "cargo tank.*discharge",
    ],
    "equipment_requirement": [
        "是否需要配备", "需要多少", "配置要求",
    ],
}

# Clarification question templates
CLARIFICATION_TEMPLATES: dict[str, dict] = {
    "ship_type": {
        "question": "请问您说的是哪类船舶？不同船型的法规要求可能完全不同。",
        "options": ["货船(非tanker)", "客船(>36人)", "客船(≤36人)", "油轮(tanker)", "散货船", "其他"],
    },
    "tonnage_or_length": {
        "question": "请问船舶的总吨位(GT)或船长(m)大约是多少？很多法规有吨位/船长阈值。",
        "options": None,
    },
    "construction_date": {
        "question": "请问船舶大约是什么时候建造的（合同日期或安放龙骨日期）？不同年代适用不同版本的法规。",
        "options": ["2010年之后", "2002-2010年", "1994-2002年", "1994年之前"],
    },
    "voyage_type": {
        "question": "是国际航行还是国内航行？",
        "options": ["国际航行", "国内航行"],
    },
    "discharge_source": {
        "question": "请问您问的是货舱区排油还是机舱舱底水排放？两者的标准完全不同。",
        "options": ["货舱区排油(MARPOL Reg.34)", "机舱舱底水(MARPOL Reg.15)"],
    },
    "delivery_date": {
        "question": "船舶是1979年12月31日之前交付还是之后？这决定排油限制是1/15,000还是1/30,000。",
        "options": ["1979年12月31日之前", "1979年12月31日之后"],
    },
}

# Patterns that indicate a slot is already filled
_SHIP_TYPE_PATTERNS = [
    "货船", "客船", "油轮", "散货船", "集装箱船", "滚装船", "化学品船", "气体船",
    "cargo ship", "passenger ship", "tanker", "bulk carrier", "container",
]
_DIMENSION_PATTERNS = re.compile(r"\d+\s*(米|m|吨|GT|DWT|总吨|载重吨)", re.IGNORECASE)
_DATE_PATTERNS = re.compile(r"(19|20)\d{2}\s*年|built\s*(in|before|after)\s*\d{4}", re.IGNORECASE)
_VOYAGE_PATTERNS = ["国际航行", "国内航行", "international", "domestic"]
_DISCHARGE_PATTERNS = {
    "discharge_source": [
        ("货舱", "cargo tank"), ("机舱", "engine room"), ("舱底水", "bilge"),
    ],
}


class ClarificationChecker:
    """Detect missing dimensional slots and generate clarification questions."""

    def detect_topic(self, query: str) -> str | None:
        """Detect the regulatory topic from query text."""
        query_lower = query.lower()
        for topic, triggers in TOPIC_TRIGGERS.items():
            for trigger in triggers:
                if trigger.lower() in query_lower:
                    return topic
        return None

    def check(
        self,
        intent: str,
        ship_info: dict,
        query: str,
        topic: str | None = None,
    ) -> tuple[bool, list[dict]]:
        """Check if clarification is needed.

        Returns (needs_clarification, questions) where questions is a list of
        dicts with 'slot', 'question', and optional 'options' keys.
        """
        # Merge intent slots + topic-specific slots
        base_slots = REQUIRED_SLOTS.get(intent, {})
        critical = list(base_slots.get("critical", []))
        important = list(base_slots.get("important", []))

        if topic and topic in TOPIC_EXTRA_SLOTS:
            extra = TOPIC_EXTRA_SLOTS[topic]
            for s in extra.get("critical", []):
                if s not in critical:
                    critical.append(s)
            for s in extra.get("important", []):
                if s not in important:
                    important.append(s)

        # Check which critical slots are missing
        missing_critical = [s for s in critical if not self._has_slot(s, ship_info, query)]

        if not missing_critical:
            return False, []

        questions = []
        for slot in missing_critical:
            template = CLARIFICATION_TEMPLATES.get(slot, {})
            questions.append({
                "slot": slot,
                "question": template.get("question", f"请提供 {slot} 信息"),
                "options": template.get("options"),
            })

        return True, questions

    def _has_slot(self, slot: str, ship_info: dict, query: str) -> bool:
        """Check if a dimensional slot is present in ship_info or query text."""
        if slot == "ship_type":
            if ship_info.get("type"):
                return True
            return any(p in query for p in _SHIP_TYPE_PATTERNS)

        if slot == "tonnage_or_length":
            if ship_info.get("tonnage") or ship_info.get("length"):
                return True
            return bool(_DIMENSION_PATTERNS.search(query))

        if slot == "construction_date":
            return bool(_DATE_PATTERNS.search(query))

        if slot == "voyage_type":
            return any(p in query for p in _VOYAGE_PATTERNS)

        if slot == "discharge_source":
            query_lower = query.lower()
            for patterns in _DISCHARGE_PATTERNS.get("discharge_source", []):
                if any(p in query_lower for p in patterns):
                    return True
            return False

        if slot == "delivery_date":
            return bool(re.search(r"197[0-9]|198[0-9]|delivered|交付", query, re.IGNORECASE))

        return False
```

---

### 2.3 Pipeline 集成

**文件**: `pipeline/voice_qa_pipeline.py`

在 `_process_query()` 中，在 retrieval 之前插入澄清检查：

```python
# === 新增：澄清检查 ===
topic = self.clarification_checker.detect_topic(text)
needs_clarification, clarify_questions = self.clarification_checker.check(
    intent=classification["intent"],
    ship_info=classification.get("ship_info", {}),
    query=text,
    topic=topic,
)

if needs_clarification:
    clarify_text = "为了给您更准确的答案，需要确认以下信息：\n\n"
    for i, q in enumerate(clarify_questions, 1):
        clarify_text += f"{i}. {q['question']}\n"
        if q.get("options"):
            clarify_text += f"   选项：{'、'.join(q['options'])}\n"

    # 保存到 session 以便后续合并
    session = self.memory.add_turn(
        session, "assistant", clarify_text, "text",
        metadata={"type": "clarification", "original_query": text, "missing_slots": [q["slot"] for q in clarify_questions]},
    )

    return {
        "session_id": session.session_id,
        "action": "clarify",
        "questions": clarify_questions,
        "answer_text": clarify_text,
        "answer_audio_base64": None,
        "citations": [],
        "confidence": "pending",
        "model_used": "none",
        "sources": [],
        "timing": timing,
        "input_mode": input_mode,
    }
# === 澄清检查结束，继续正常流程 ===
```

---

### 2.4 前端适配

**文件**: `static/index.html`

在响应处理中检测 `action === "clarify"`：

```javascript
if (data.action === "clarify") {
    // 显示澄清问题
    displayClarification(data.questions, data.session_id, originalText);
}

function displayClarification(questions, sessionId, originalQuery) {
    let html = '<div class="clarification-box">';
    html += '<p class="clarify-header">为了给您更准确的答案：</p>';

    questions.forEach((q, i) => {
        html += `<p class="clarify-question">${i+1}. ${q.question}</p>`;
        if (q.options) {
            html += '<div class="clarify-options">';
            q.options.forEach(opt => {
                html += `<button class="clarify-btn" onclick="submitClarification('${sessionId}', '${originalQuery}', '${opt}')">${opt}</button>`;
            });
            html += '</div>';
        }
    });

    html += '</div>';
    appendMessage('assistant', html);
}

function submitClarification(sessionId, originalQuery, supplement) {
    const mergedQuery = `${originalQuery}（补充信息：${supplement}）`;
    sendTextQuery(mergedQuery, sessionId);
}
```

---

### 2.5 WebSocket 多轮支持

**文件**: `api/routes/voice.py`

WebSocket handler 已有 session 管理，无需大改。`clarify` 响应会通过正常的 WebSocket message 发出去，用户补充信息作为新的 text message 发回来，pipeline 会自动将合并后的 query 正常处理。

唯一需要确保的是：当用户补充信息包含"补充信息："前缀时，pipeline 能识别这是澄清回合，不会重复触发澄清。在 `ClarificationChecker.check()` 中加一个短路条件：

```python
# 如果 query 包含"补充信息"，说明是澄清回合，不再重复追问
if "补充信息" in query or "补充：" in query:
    return False, []
```

---

## Phase 3: Reranking 层 — 提升检索精度

### 3.1 方案选择

| 方案 | 类型 | 多语言 | 延迟 | 成本 | 推荐度 |
|------|------|--------|------|------|--------|
| **Cohere Rerank v3.5** | API | 100+语言 | ~200ms | $2/1000次 | **推荐** |
| BGE-reranker-v2-m3 | 自托管 | 100+语言 | ~150ms | GPU算力 | 备选 |
| Jina Reranker v2 | API/自托管 | 100+语言 | ~180ms | API=$1/1000 | 备选 |

**选择 Cohere Rerank**，原因：
- 中文查询→英文法规的跨语言 reranking 是核心场景，Cohere 的多语言模型在此场景下表现最好
- 即插即用，不需要 GPU
- 200ms 延迟对比现有的 1-2s 检索时间可接受
- 支持半结构化数据（表格、JSON），适合法规文本

### 3.2 新增文件: `retrieval/reranker.py`

```python
"""Cross-encoder reranking for improved retrieval precision."""
import logging

import cohere

logger = logging.getLogger(__name__)


class CohereReranker:
    """Rerank retrieved chunks using Cohere's cross-encoder model."""

    def __init__(self, api_key: str, model: str = "rerank-multilingual-v3.0"):
        self.client = cohere.ClientV2(api_key=api_key)
        self.model = model

    def rerank(
        self,
        query: str,
        chunks: list[dict],
        top_n: int = 5,
    ) -> list[dict]:
        """Rerank chunks by cross-encoder relevance score.

        Args:
            query: The user's query text.
            chunks: Retrieved chunks from hybrid search.
            top_n: Number of top results to return.

        Returns:
            Reranked list of chunks with added rerank_score field.
        """
        if not chunks:
            return chunks

        doc_texts = []
        for c in chunks:
            meta = c.get("metadata", {})
            # Include breadcrumb + title for better ranking context
            prefix = f"{meta.get('breadcrumb', '')} - {meta.get('title', '')}"
            text = c.get("text", "")[:1000]
            doc_texts.append(f"{prefix}\n{text}" if prefix.strip(" -") else text)

        try:
            response = self.client.rerank(
                model=self.model,
                query=query,
                documents=doc_texts,
                top_n=min(top_n, len(chunks)),
            )
        except Exception as exc:
            logger.error(f"[Reranker] API error, returning original order: {exc}")
            return chunks[:top_n]

        reranked = []
        for result in response.results:
            original = chunks[result.index]
            reranked.append({
                **original,
                "rerank_score": result.relevance_score,
                "original_rrf_rank": result.index,
            })

        logger.info(
            f"[Reranker] Reranked {len(chunks)} → top {len(reranked)}, "
            f"scores: {[f'{r['rerank_score']:.3f}' for r in reranked[:3]]}"
        )
        return reranked
```

### 3.3 集成位置

**文件**: `retrieval/hybrid_retriever.py`

在 RRF 融合后、graph expansion 前插入 rerank：

```python
sorted_results = sorted(
    all_results.values(),
    key=lambda x: x["rrf_score"],
    reverse=True,
)[:effective_top_k]

# NEW: Cross-encoder reranking
if self.reranker:
    sorted_results = self.reranker.rerank(
        query=query,  # 用原始 query 而不是 enhanced_query，因为 reranker 自己做语义匹配
        chunks=sorted_results,
        top_n=effective_top_k,
    )

# Graph expansion...
```

### 3.4 配置更新

**文件**: `config/settings.py`

```python
cohere_api_key: str = ""
reranker_model: str = "rerank-multilingual-v3.0"
reranker_enabled: bool = True  # 可通过环境变量关闭
```

**文件**: `pyproject.toml`

```
"cohere>=5.0",
```

**文件**: `.env.example`

```
COHERE_API_KEY=your_cohere_api_key_here
```

---

## Phase 4: 查询增强术语扩展 + 持续监控

### 4.1 QueryEnhancer 主题特定增强规则

**文件**: `retrieval/query_enhancer.py`

在 `enhance()` 方法中新增主题特定注入逻辑：

```python
# 防火分隔相关 → 注入表格关键词
if any(kw in query for kw in ["防火分隔", "防火等级"]):
    matched_terms.update([
        "Table 9.3", "Table 9.5", "fire integrity of bulkheads and decks",
        "structural fire protection",
    ])
    relevant_regs.update(["SOLAS II-2/9", "SOLAS II-2/3"])

# 排油相关 → 注入 Reg.34 关键数据
if any(kw in query for kw in ["排油", "ODME"]):
    matched_terms.update([
        "Regulation 34", "1/30000", "discharge limit", "30 litres per nautical mile",
    ])
    relevant_regs.update(["MARPOL Annex I/Reg.34"])

# 透气管相关 → 注入位置分类关键词
if any(kw in query for kw in ["透气管", "air pipe"]):
    matched_terms.update([
        "position 1", "position 2", "760 mm", "450 mm", "freeboard deck",
        "superstructure deck",
    ])
    relevant_regs.update(["Load Lines Reg.20"])
```

### 4.2 诊断日志保持

Phase 1 添加的 `[DIAG]`/`[RETRIEVAL]`/`[ENHANCE]` 日志作为永久功能保留，用于持续质量监控。每次部署后通过 Railway Logs 抽样检查检索质量。

### 4.3 回归测试自动化

建议后续将 T101-T105 五道题固化为自动化回归测试：
- 在 `evaluation/` 目录下维护测试题库
- 每次部署后自动运行，检查关键法规是否出现在 top-5 检索结果中
- 不自动判断 LLM 回答对错（需要人工），但可以检查检索命中率

---

## 修改文件清单

| 文件 | Phase | 修改类型 | 估计行数 |
|------|-------|---------|---------|
| `knowledge/practical/lifesaving.yaml` | 1 | 修正 2 个条目 | ~30行 |
| `knowledge/practical/fire_safety.yaml` | 1 | 新增 1 个条目 | ~20行 |
| `knowledge/practical/marpol.yaml` | 1 | 新增 1 个条目 | ~20行 |
| `generation/prompts.py` | 1 | 强化 SYSTEM_PROMPT | ~20行 |
| `retrieval/query_enhancer.py` | 1+4 | 扩展术语映射 + 主题注入 | ~40行 |
| `retrieval/clarification_checker.py` | 2 | **新建** | ~180行 |
| `retrieval/query_classifier.py` | 2 | 新增 topic 检测 | ~15行 |
| `pipeline/voice_qa_pipeline.py` | 2 | 集成澄清检查 | ~25行 |
| `api/routes/voice.py` | 2 | WebSocket 支持（可能不需改） | ~5行 |
| `static/index.html` | 2 | 前端澄清交互 | ~40行 |
| `retrieval/reranker.py` | 3 | **新建** | ~60行 |
| `retrieval/hybrid_retriever.py` | 3 | 集成 reranker | ~10行 |
| `config/settings.py` | 3 | 新增 Cohere 配置 | ~5行 |
| `pyproject.toml` | 3 | 新增 `cohere>=5.0` | ~1行 |

---

## 验证方案

### Phase 1 验证
1. 重跑 T101-T105 五道题
2. 重点验证：
   - T101: 系统是否声明"以下基于货船假设"并给出 Table 9.3 的正确等级
   - T103: free-fall 配置下是否正确回答"仍需至少一舷 davit"
   - T104: 是否给出 1/30,000 限制并区分 Reg.34 vs Reg.15

### Phase 2 验证
1. 发送"厨房和走廊之间的防火分隔是什么等级？"（无船型信息）
2. 期望：系统返回澄清问题"请问您说的是哪类船舶？"
3. 用户选择"货船(非tanker)" → 系统合并查询，返回带 Table 9.3 引用的正确答案

### Phase 3 验证
1. 对比 rerank 前后 T101-T105 的 top-5 chunk 命中率
2. 目标：SOLAS II-2/9 Table 9.3 和 MARPOL Reg.34 在 rerank 后进入 top-5

### 持续监控
- Railway Logs 中的 `[DIAG]` 日志持续记录每次查询的检索细节
- 定期用验船师新题目做回归测试

---

## 方案自审（可行性评估）

### 可行的部分
- **Phase 1 (实务KB修正 + Prompt强化 + 自适应降级)**: 纯文本修改，零风险，立即可执行，预期效果最大。特别是"检索质量自评"规则——这是解决"RAG 不如裸模型"问题的关键，让 Claude 在检索失效时可以用自身知识回答，而不是被错误 chunk 锚定
- **Phase 2 (澄清Agent)**: 架构上不引入新框架，只在现有 pipeline 中插入一个确定性检查器，风险低。前端改动最小化（按钮式选择）
- **Phase 4 (术语扩展)**: 增量式修改，风险低

### 需要注意的部分
- **Phase 3 (Reranker)**: 需要 Cohere API key + 费用预算。200ms 额外延迟在可接受范围内。如果不想增加 API 依赖，可以用 BGE-reranker 自托管（但需要 GPU）
- **多轮澄清的用户体验**: 如果每个问题都追问，会影响使用流畅度。需要精确控制只对"critical"缺失维度追问，"important"和"optional"维度通过假设声明处理
- **自适应降级的风险**: 允许模型用自身知识回答可能导致"幻觉"——但相比"被错误检索锚定的确定性错误"，这其实是更好的选择。关键是要求模型标注 ⚠ 警告

### 暂不建议做的
- 法规条文的结构化元数据提取（tonnage阈值、适用船型标签）——这需要大量人工标注，ROI 目前不高
- LLM fine-tuning——样本量不足，且 Claude 的 zero-shot 能力已经足够好，问题出在检索和 prompt 而非模型本身
- 完全替换 RAG 为裸模型——RAG 在检索成功时（如 T103）效果明显更好，关键是让系统知道"什么时候检索成功了"

---

## 技术参考来源

| 技术方向 | 关键参考 |
|---------|--------|
| 多轮澄清 Agent | [LangGraph interrupt()](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/), [Anthropic Tool-Use](https://www.anthropic.com/engineering/advanced-tool-use) |
| 槽位填充 | Adaptive-RAG query complexity classification, ConfRAG confidence-guided retrieval |
| Reranking | [Cohere Rerank v3.5](https://docs.cohere.com/docs/reranking-with-cohere), BGE-reranker-v2-m3, Jina ColBERT v2 |
| 法规RAG | [RAGulating Compliance](https://arxiv.org/abs/2508.09893) - multi-agent KG for regulatory QA |
| 查询分解 | [RQ-RAG](https://arxiv.org/abs/2404.00610) - query refinement framework |
| 用户历史权重 | [Shaped.ai Stateful Agents Guide](https://www.shaped.ai/blog/building-stateful-ai-agents-why-user-history-matters-in-rag-systems-2026-guide) |
