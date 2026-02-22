# BV-RAG Bad Case 260222 改进方案

> **以点带面：从一个查表错误，暴露 RAG 系统在"条件分支法规"场景下的三层系统性缺陷**

---

## 一、Bad Case 深度解剖

### 1.1 用户查询

> "根据SOLAS，对于运输可燃液体货物的轮船，走廊和消防控制站之间的舱壁应该是什么防火等级？"

### 1.2 正确答案

```
船型识别:  运输可燃液体 → Tanker（SOLAS Ch I, Reg 2(h) 定义）
适用条款:  SOLAS II-2/Reg 9/2.4（Tankers 专用章节）
适用表格:  Table 9.7（tanker 舱壁分隔）/ Table 9.8（tanker 甲板分隔）
查表参数:  Control stations = Category (1), Corridors = Category (2)
查表结果:  (1) × (2) = A-0（带脚注 c）
最终答案:  A-0
```

### 1.3 系统错误答案

```
船型识别:  ✓ 正确识别为油轮/化学品船
适用条款:  ✗ 错误使用了 2.3（Cargo ships except tankers）而非 2.4（Tankers）
适用表格:  ✗ 错误引用 Table 9.5（非 tanker 货船）而非 Table 9.7（tanker）
查表参数:  ✓ Category (1) vs Category (2) 判断正确
查表结果:  ✗✗ 即使按 Table 9.5 查，(1)×(2) 也是 A-0，系统却回答 A-60
最终答案:  ✗ A-60（正确应为 A-0）
```

### 1.4 验船师追加测试

> 换问"散货船(Bulk Carrier)"同样的问题，系统：
> - ✓ 正确判断为非 tanker → Table 9.5
> - ✓ 正确识别 Category (1) vs (2)
> - ✗ 查表结果仍然回答 A-60，实际 Table 9.5 中 (1)×(2) = A-0

### 1.5 错误分类（三层独立 bug）

| 错误层 | 类型 | 描述 | 严重度 |
|---|---|---|---|
| **Bug 1** | 法规分支路由错误 | Tanker 应走 Reg 9/2.4 → Table 9.7/9.8，系统走了 2.3 → Table 9.5/9.6 | **严重** |
| **Bug 2** | 表格数值读取错误 | 无论 Table 9.5 还是 9.7，(1)×(2) 都是 A-0，系统回答 A-60 | **严重** |
| **Bug 3** | 幻觉：编造不存在的数据 | 系统可能根本没有读到表格内容，而是凭"消防控制站需要最高防火等级"的直觉编造了 A-60 | **严重** |

---

## 二、根因分析

### 2.1 Bug 1 根因：RAG 缺乏"条件分支"感知能力

**SOLAS II-2/Reg 9 的结构**：

```
Regulation 9: Fire integrity of bulkheads and decks
├── 2.1 Passenger ships carrying more than 36 passengers
│   └── Tables 9.1 / 9.2
├── 2.2 Passenger ships carrying not more than 36 passengers
│   └── Tables 9.3 / 9.4
├── 2.3 Cargo ships other than tankers        ← 散货船、集装箱船等
│   └── Tables 9.5 / 9.6
└── 2.4 Tankers                               ← 油轮、化学品船
    └── Tables 9.7 / 9.8
```

**问题**：当前 RAG 检索时，向量相似度搜索可能同时命中 2.3 和 2.4 的 chunks。如果 2.3 的 chunk 排名更高（因为 2.3 包含更多通用关键词），LLM 就会用错误的条款回答。

**这不是孤例**。SOLAS 中大量法规按船型/吨位/建造年代分支：

| 法规 | 分支条件 | 错误风险 |
|---|---|---|
| SOLAS II-2/Reg 9 | 客船>36人 / 客船≤36人 / 货船非tanker / tanker | **本 bad case** |
| SOLAS II-2/Reg 10 | 客船 / 货船（灭火系统要求不同） | 同类风险 |
| SOLAS II-1/Reg 3-2 | 新船 / 现有船（结构标准不同） | 同类风险 |
| SOLAS III | 客船 / 货船（救生设备配备数量不同） | 同类风险 |
| MARPOL Annex I | 油轮≥150GT / 非油轮≥400GT | 同类风险 |
| MARPOL Annex VI | NECA区域 / 非NECA（NOx标准不同） | 同类风险 |
| Load Line Convention | 船长 / 干舷类型 / 航区 多维分支 | 同类风险 |

### 2.2 Bug 2 根因：表格数据在 chunking 时丢失结构

SOLAS 的防火分隔表格是**二维矩阵**（10×10 或 11×11），chunk 化后极可能：

1. **表格被截断**：一个 chunk 只包含表格的前几行，LLM 看不到完整的交叉数据
2. **行列关系丢失**：纯文本 chunk 中，列标题和数据行的对应关系不清晰
3. **脚注分离**：A-0^c、A-0^e 等带脚注的值可能被错误解析

### 2.3 Bug 3 根因：LLM 的"常识推理"覆盖了检索结果

系统回答中有一句暴露性的话：

> "消防控制站作为关键安全设施，与走廊之间必须保持**最高防火等级**"

这是 LLM 在没有看到准确表格数据时，用"常识推理"编造的结论。A-60 是最高等级，所以 LLM 自信地选了 A-60。**实际上 A-0 才是正确答案**——因为控制站和走廊都不是高火灾风险区域，A-0（钢质不燃但无隔热要求）在很多场景下就够了。

**这暴露了 safety post-check（防幻觉）机制的漏洞**：当前的 pattern-based 检查无法识别"数值看起来合理但实际不对"的幻觉。

---

## 三、改进方案

### 3.1 改进总览

| 改进项 | 解决的 Bug | 优先级 | 工作量 | 预期效果 |
|---|---|---|---|---|
| **A. 法规分支路由元数据** | Bug 1 | P0 | 2-3 天 | 根治船型→条款映射错误 |
| **B. 表格数据专项修复** | Bug 2 | P0 | 2-3 天 | 根治查表读值错误 |
| **C. System Prompt 防幻觉增强** | Bug 3 | P0 | 0.5 天 | 防止 LLM 编造表格数据 |
| **D. 查表验证 Post-check** | Bug 2+3 | P1 | 1-2 天 | 二次校验表格查询结果 |
| **E. 条件分支 Chunk 增强** | Bug 1 | P1 | 2-3 天 | 系统性解决分支法规检索 |
| **F. 回归测试扩展** | 全部 | P1 | 1-2 天 | 防止未来回归 |

---

### 3.2 改进 A：法规分支路由元数据（P0）

**核心思路**：在 chunk 的 metadata 中显式标注"适用条件"，检索时根据用户查询中的船型信息做精准过滤。

#### 3.2.1 Chunk Metadata 增强

当前 chunk 的 metadata 可能只有：

```json
{
  "source": "SOLAS",
  "chapter": "II-2",
  "regulation": "9",
  "section": "2.3.3",
  "title": "Fire integrity of bulkheads and decks"
}
```

**改进后**增加 `applicability` 字段：

```json
{
  "source": "SOLAS",
  "chapter": "II-2",
  "regulation": "9",
  "section": "2.3.3",
  "title": "Fire integrity of bulkheads and decks",

  "applicability": {
    "ship_types": ["cargo_ship_non_tanker"],
    "ship_type_exclusions": ["tanker", "passenger_ship"],
    "tonnage_condition": null,
    "construction_date_condition": null,
    "applicable_tables": ["9.5", "9.6"],
    "parent_condition_text": "2.3 Cargo ships other than tankers"
  }
}
```

**SOLAS II-2/Reg 9 相关 chunks 的 applicability 标注**：

| Section | chunks 关联的 tables | ship_types | ship_type_exclusions |
|---|---|---|---|
| 2.1.x + Table 9.1/9.2 | 9.1, 9.2 | `["passenger_ship_gt36"]` | `["cargo_ship"]` |
| 2.2.x + Table 9.3/9.4 | 9.3, 9.4 | `["passenger_ship_le36"]` | `["cargo_ship"]` |
| 2.3.x + Table 9.5/9.6 | 9.5, 9.6 | `["cargo_ship_non_tanker"]` | `["tanker", "passenger_ship"]` |
| 2.4.x + Table 9.7/9.8 | 9.7, 9.8 | `["tanker"]` | `["cargo_ship_non_tanker", "passenger_ship"]` |

#### 3.2.2 检索时的船型过滤逻辑

```python
# retrieval/hybrid_retriever.py — 新增 applicability 过滤

def retrieve_with_applicability(self, query: str, ship_type: str = None, top_k: int = 10):
    """检索时如果能识别出船型，优先返回 applicability 匹配的 chunks"""

    # 1. 正常检索
    raw_chunks = self.retrieve(query=query, top_k=top_k * 2)  # 多取一些

    if not ship_type:
        return raw_chunks[:top_k]

    # 2. 按 applicability 分组
    matched = []      # applicability 完全匹配
    neutral = []      # 没有 applicability 标注（通用条款）
    conflicting = []  # applicability 明确排除当前船型

    normalized = normalize_ship_type_for_regulation(ship_type)

    for chunk in raw_chunks:
        app = chunk.get("metadata", {}).get("applicability", {})

        if not app or not app.get("ship_types"):
            neutral.append(chunk)
            continue

        # 检查是否被排除
        exclusions = app.get("ship_type_exclusions", [])
        if any(normalized in exc or exc in normalized for exc in exclusions):
            conflicting.append(chunk)
            continue

        # 检查是否匹配
        types = app.get("ship_types", [])
        if any(normalized in t or t in normalized for t in types):
            matched.append(chunk)
        else:
            neutral.append(chunk)

    # 3. 优先返回匹配的，然后是中性的，最后才是冲突的
    result = matched + neutral
    if len(result) < top_k:
        # 如果匹配+中性不够，把冲突的也加上（但标记一下）
        for c in conflicting:
            c["_applicability_warning"] = f"This chunk is for {app.get('ship_types')}, not for {ship_type}"
        result.extend(conflicting)

    return result[:top_k]


def normalize_ship_type_for_regulation(ship_type: str) -> str:
    """把用户输入的船型归一化为法规分类"""
    lower = ship_type.lower()

    # Tanker 判断（SOLAS Ch I, Reg 2(h)：运输可燃液体散装货物的货船）
    tanker_keywords = [
        'tanker', 'oil tanker', 'chemical tanker', 'product tanker',
        '油轮', '化学品船', '成品油轮', '原油轮',
        '可燃液体', 'flammable liquid', 'inflammable',
    ]
    if any(kw in lower for kw in tanker_keywords):
        return 'tanker'

    # 客船判断
    passenger_keywords = ['passenger', '客船', '客轮', 'cruise', '邮轮']
    if any(kw in lower for kw in passenger_keywords):
        return 'passenger_ship'

    # 默认为非 tanker 货船
    return 'cargo_ship_non_tanker'
```

#### 3.2.3 QueryEnhancer 增强：从查询中提取船型

```python
# retrieval/query_enhancer.py — 新增船型识别

def extract_ship_type_from_query(self, query: str) -> str | None:
    """从用户查询中识别船型信息"""

    # 1. 中文关键词映射
    cn_tanker = ['油轮', '化学品船', '成品油轮', '可燃液体', '液体货物', 'tanker']
    cn_bulk = ['散货船', 'bulk carrier', '散装船']
    cn_container = ['集装箱船', 'container ship', '箱船']
    cn_passenger = ['客船', '客轮', '邮轮', 'passenger', 'cruise']
    cn_general = ['杂货船', 'general cargo', '多用途船']

    lower = query.lower()

    # "运输可燃液体货物的轮船" → tanker
    if any(kw in lower for kw in cn_tanker):
        return 'tanker'
    if '可燃' in lower and ('液体' in lower or '液货' in lower):
        return 'tanker'
    if '运输' in lower and '液体' in lower and '货物' in lower:
        return 'tanker'

    if any(kw in lower for kw in cn_bulk):
        return 'cargo_ship_non_tanker'
    if any(kw in lower for kw in cn_container):
        return 'cargo_ship_non_tanker'
    if any(kw in lower for kw in cn_passenger):
        return 'passenger_ship'
    if any(kw in lower for kw in cn_general):
        return 'cargo_ship_non_tanker'

    # 2. 英文关键词（已有 QueryEnhancer 的 600+ 术语映射应覆盖）
    en_tanker = ['tanker', 'flammable liquid', 'inflammable liquid',
                 'oil carrier', 'chemical carrier']
    if any(kw in lower for kw in en_tanker):
        return 'tanker'

    return None  # 无法识别船型
```

---

### 3.3 改进 B：表格数据专项修复（P0）

**核心问题**：SOLAS 的防火分隔表格（Table 9.1 ~ 9.8）是二维矩阵，chunking 后结构丢失，LLM 无法准确查表。

#### 3.3.1 诊断：当前表格 chunks 的状态

**需要先诊断**当前 Qdrant 中 Table 9.5 / 9.7 的 chunks 长什么样：

```python
# scripts/diagnose_table_chunks.py

"""诊断 SOLAS 防火分隔表格的 chunk 质量"""

import asyncio
from retrieval.hybrid_retriever import HybridRetriever

TABLES_TO_CHECK = [
    "Table 9.1", "Table 9.2", "Table 9.3", "Table 9.4",
    "Table 9.5", "Table 9.6", "Table 9.7", "Table 9.8",
]

async def diagnose():
    retriever = HybridRetriever(...)

    for table_name in TABLES_TO_CHECK:
        print(f"\n{'='*60}")
        print(f"Diagnosing: {table_name}")
        print(f"{'='*60}")

        # 搜索包含该表格的 chunks
        chunks = retriever.retrieve(
            query=f"SOLAS {table_name} fire integrity bulkhead",
            top_k=10
        )

        for i, chunk in enumerate(chunks):
            text = chunk.get('text', '')[:500]
            metadata = chunk.get('metadata', {})
            print(f"\n--- Chunk {i+1} ---")
            print(f"Score: {chunk.get('score', 'N/A')}")
            print(f"Metadata: {metadata}")
            print(f"Text preview: {text}")

            # 检查表格完整性
            has_matrix = 'A-0' in text or 'A-60' in text or 'B-0' in text
            has_categories = 'Control stations' in text or 'Category (1)' in text
            has_corridors = 'Corridors' in text or 'Category (2)' in text
            print(f"Has fire rating values: {has_matrix}")
            print(f"Has control station category: {has_categories}")
            print(f"Has corridors category: {has_corridors}")

asyncio.run(diagnose())
```

#### 3.3.2 表格 Chunk 修复方案

**方案一：结构化表格 chunk（推荐）**

将每个防火分隔表格转换为**自描述的结构化文本 chunk**，确保 LLM 可以直接读取：

```text
=== SOLAS Table 9.7: Fire integrity of bulkheads separating adjacent spaces — TANKERS ===

Applicable to: Tankers (SOLAS II-2/Reg 9/2.4)
NOT applicable to: Cargo ships other than tankers (use Table 9.5), Passenger ships (use Table 9.1/9.3)

Space categories:
(1) Control stations
(2) Corridors
(3) Accommodation spaces
(4) Stairways
(5) Service spaces (low risk)
(6) Machinery spaces of category A
(7) Other machinery spaces
(8) Cargo pump-rooms
(9) Service spaces (high risk)
(10) Open decks

Bulkhead fire integrity matrix (row × column):
(1)×(1): A-0     (1)×(2): A-0/c   (1)×(3): A-60    (1)×(4): A-0
(1)×(5): A-15    (1)×(6): A-60    (1)×(7): A-15    (1)×(8): A-60
(1)×(9): A-60    (1)×(10): *

(2)×(2): C       (2)×(3): B-0     (2)×(4): B-0     (2)×(5): B-0
(2)×(6): A-60    (2)×(7): A-0     (2)×(8): A-60    (2)×(9): A-0
(2)×(10): *

(3)×(3): C       (3)×(4): B-0/A-0a  (3)×(5): B-0
(3)×(6): A-60    (3)×(7): A-0     (3)×(8): A-60    (3)×(9): A-0
(3)×(10): *

... (complete matrix)

Footnotes:
a: Where adjacent spaces are of the same numerical category...
c: Where such spaces are adjacent to open deck spaces...
d: ...

IMPORTANT: To look up a value, find the row for one space category and the column for the other. The table is symmetric.
```

**方案二：关键查询对预计算（备选）**

对高频查表场景（如"X 和 Y 之间的防火等级"），预计算结果存入知识库：

```json
{
  "id": "TABLE-LOOKUP-9.7-1-2",
  "type": "table_lookup",
  "source_table": "SOLAS Table 9.7",
  "applicable_ship_types": ["tanker"],
  "space_1": {"category": 1, "name": "Control stations"},
  "space_2": {"category": 2, "name": "Corridors"},
  "bulkhead_rating": "A-0",
  "deck_rating_table": "Table 9.8",
  "footnotes": ["c"],
  "regulation_ref": "SOLAS II-2/Reg 9/2.4, Table 9.7"
}
```

这样对于明确的查表问题，可以直接从知识库返回精确值，不依赖 LLM 解读。

#### 3.3.3 需要修复的全部表格清单

SOLAS 中的关键二维矩阵表格（全部需要按上述方式重新 chunk 或预计算）：

| 表格 | 内容 | 适用船型 | 维度 |
|---|---|---|---|
| Table 9.1 | 舱壁防火等级 | 客船 >36 人 | 14×14 |
| Table 9.2 | 甲板防火等级 | 客船 >36 人 | 14×14 |
| Table 9.3 | 舱壁防火等级 | 客船 ≤36 人 | 11×11 |
| Table 9.4 | 甲板防火等级 | 客船 ≤36 人 | 11×11 |
| Table 9.5 | 舱壁防火等级 | 货船非 tanker | 11×11 |
| Table 9.6 | 甲板防火等级 | 货船非 tanker | 11×11 |
| Table 9.7 | 舱壁防火等级 | Tanker | 10×10 |
| Table 9.8 | 甲板防火等级 | Tanker | 10×10 |

此外还有其他包含查表逻辑的法规（也应排查）：

| 法规 | 表格/内容 | 查表逻辑 |
|---|---|---|
| SOLAS II-2/Reg 4 | 逃生路径最低宽度 | 按人数查表 |
| SOLAS II-2/Reg 10 | 灭火系统配备要求 | 按船型+舱室类型查表 |
| SOLAS III | 救生设备数量要求 | 按船型+人数查表 |
| MARPOL Annex I, Reg 14 | 排放限值 | 按区域+日期查表 |
| MARPOL Annex VI, Reg 13 | NOx 限值 | 按 Tier + 发动机转速查表 |
| Load Line | 干舷计算表 | 多参数查表 |

---

### 3.4 改进 C：System Prompt 防幻觉增强（P0）

#### 3.4.1 当前问题

LLM 在没有看到准确表格数据时，用"常识推理"编造了 A-60：

> "消防控制站作为关键安全设施...必须保持最高防火等级"

这是**推理性幻觉**——逻辑链看起来合理，但结论是错的。

#### 3.4.2 改进后的 System Prompt（通用 RAG 对话场景）

在现有 system prompt 的基础上，增加以下**防表格幻觉规则**：

```text
[新增规则 — 表格查询防幻觉]

TABLE LOOKUP DISCIPLINE:
When answering questions that require looking up values from regulatory tables
(e.g., fire integrity ratings, equipment quantities, emission limits):

1. NEVER guess or infer table values based on "common sense" or "logical reasoning".
   The actual regulatory values are often counter-intuitive.
   Example: Control stations vs Corridors might be A-0, not A-60, because both are
   low fire-risk categories.

2. If the retrieved context contains the relevant table data, quote the EXACT cell value
   including any superscript footnotes (e.g., "A-0^c", "A-0^e").

3. If the retrieved context does NOT contain the table, or the table data is truncated
   or unclear, you MUST explicitly say:
   "我无法在检索到的法规原文中找到完整的 Table X.X 数据，无法给出准确的查表结果。
    建议直接查阅 SOLAS II-2/Reg 9, Table X.X 原文。"
   DO NOT fabricate a value.

4. When citing a table value, always specify:
   - Which table you are reading from (Table 9.5 vs 9.7 matters!)
   - Which row and column (Category numbers)
   - The exact value at the intersection
   - Any applicable footnotes

5. For SOLAS fire integrity tables specifically:
   - Table 9.1/9.2 → Passenger ships >36 passengers
   - Table 9.3/9.4 → Passenger ships ≤36 passengers
   - Table 9.5/9.6 → Cargo ships OTHER THAN tankers
   - Table 9.7/9.8 → Tankers (SOLAS Ch I Reg 2(h): cargo ships carrying flammable liquids in bulk)
   ALWAYS verify you are using the correct table for the ship type before reading values.
```

#### 3.4.3 改进后的 System Prompt（船型识别规则）

```text
[新增规则 — 船型识别与法规分支]

SHIP TYPE CLASSIFICATION FOR REGULATION ROUTING:
Many maritime regulations have different requirements based on ship type.
You MUST correctly identify the ship type BEFORE looking up any regulation.

SOLAS ship type hierarchy:
├── Passenger ship (carrying >12 passengers)
│   ├── >36 passengers → Use Reg 9/2.1, Tables 9.1/9.2
│   └── ≤36 passengers → Use Reg 9/2.2, Tables 9.3/9.4
└── Cargo ship (not a passenger ship)
    ├── Tanker (Reg 2(h): carrying flammable liquids in bulk)
    │   └── Use Reg 9/2.4, Tables 9.7/9.8
    └── Non-tanker cargo ships (bulk carriers, container ships, general cargo, etc.)
        └── Use Reg 9/2.3, Tables 9.5/9.6

CRITICAL MAPPING RULES:
- "运输可燃液体货物" / "flammable liquid cargo in bulk" → TANKER → Reg 9/2.4
- "油轮" / "oil tanker" → TANKER → Reg 9/2.4
- "化学品船" / "chemical tanker" → TANKER → Reg 9/2.4
- "散货船" / "bulk carrier" → NON-TANKER CARGO → Reg 9/2.3
- "集装箱船" / "container ship" → NON-TANKER CARGO → Reg 9/2.3
- "杂货船" / "general cargo" → NON-TANKER CARGO → Reg 9/2.3

ALWAYS state which ship type category you are using and WHY, before citing any table.
If the user does not specify ship type, ASK for clarification before looking up tables.
```

#### 3.4.4 改进后的 Fill Prompt（extension 场景补充）

在 v2 plan 的 `FILL_SYSTEM_PROMPT` 中，补充防火等级相关的 few-shot：

```text
ADDITIONAL STYLE REFERENCES for fire safety defects:

- "Fire integrity of bulkhead between corridor and control station found not meeting
   A-0 standard as required by SOLAS Table 9.7 for tankers.
   (Ref: SOLAS Reg II-2/9.2.4, Table 9.7)"

- "A-class division between machinery space of category A and accommodation space
   found without proper insulation; required standard is A-60 per SOLAS Table 9.5.
   (Ref: SOLAS Reg II-2/9.2.3, Table 9.5)"

NOTE: Fire integrity ratings (A-60, A-30, A-15, A-0, B-15, B-0, C) must be
quoted exactly from the applicable table. Do NOT assume higher ratings
for seemingly important spaces — the actual table values are often A-0
where one might expect A-60.
```

---

### 3.5 改进 D：查表验证 Post-check（P1）

**核心思路**：对于涉及表格查询的回答，增加一道结构化验证。

```python
# generation/post_check.py — 新增表格查询验证

TABLE_LOOKUP_PATTERNS = {
    # 检测回答中是否包含表格引用
    "solas_fire_tables": {
        "trigger_keywords": ["Table 9.", "表 9.", "防火", "fire integrity",
                             "A-0", "A-15", "A-30", "A-60", "B-0", "B-15"],
        "validation_rules": [
            {
                "name": "table_ship_type_consistency",
                "description": "检查引用的表格是否与识别的船型一致",
                "checks": {
                    "tanker + Table 9.5": "ERROR: Tanker should use Table 9.7, not 9.5",
                    "tanker + Table 9.6": "ERROR: Tanker should use Table 9.8, not 9.6",
                    "tanker + Table 9.3": "ERROR: Tanker should use Table 9.7, not 9.3",
                    "cargo ship + Table 9.7": "WARNING: Non-tanker cargo ships should use Table 9.5, not 9.7",
                    "cargo ship + Table 9.8": "WARNING: Non-tanker cargo ships should use Table 9.6, not 9.8",
                    "bulk carrier + Table 9.7": "WARNING: Bulk carriers should use Table 9.5, not 9.7",
                    "passenger + Table 9.5": "WARNING: Passenger ships should use Table 9.1 or 9.3",
                }
            },
            {
                "name": "known_value_verification",
                "description": "对已知的高频查表结果做硬校验",
                "known_values": {
                    "Table 9.5|(1)|(2)": "A-0",
                    "Table 9.5|(1)|(3)": "A-60",
                    "Table 9.5|(1)|(6)": "A-60",
                    "Table 9.7|(1)|(2)": "A-0",
                    "Table 9.7|(1)|(3)": "A-60",
                    "Table 9.7|(1)|(6)": "A-60",
                    "Table 9.7|(2)|(6)": "A-60",
                    # ... 扩展更多高频查询值
                }
            }
        ]
    }
}


def post_check_table_lookup(answer: str, query: str, chunks: list) -> dict:
    """检查回答中的表格引用是否自洽"""

    warnings = []

    # 1. 检测船型
    ship_type = extract_ship_type_from_text(query + " " + answer)

    # 2. 检测引用的表格
    tables_cited = extract_table_references(answer)  # e.g., ["9.5", "9.7"]

    # 3. 船型-表格一致性检查
    if ship_type == "tanker":
        for t in tables_cited:
            if t in ["9.1", "9.2", "9.3", "9.4", "9.5", "9.6"]:
                warnings.append({
                    "level": "ERROR",
                    "type": "table_ship_type_mismatch",
                    "message": f"Tanker 应使用 Table 9.7/9.8，但回答引用了 Table {t}",
                    "fix_suggestion": f"请使用 SOLAS II-2/Reg 9/2.4 中的 Table 9.7（舱壁）或 Table 9.8（甲板）"
                })
    elif ship_type == "cargo_ship_non_tanker":
        for t in tables_cited:
            if t in ["9.7", "9.8"]:
                warnings.append({
                    "level": "WARNING",
                    "type": "table_ship_type_mismatch",
                    "message": f"非 tanker 货船应使用 Table 9.5/9.6，但回答引用了 Table {t}",
                })

    # 4. 已知数值校验
    for table_id in tables_cited:
        categories = extract_categories_from_answer(answer)  # e.g., (1, 2)
        if categories:
            key = f"Table {table_id}|({categories[0]})|({categories[1]})"
            known = TABLE_LOOKUP_PATTERNS["solas_fire_tables"]["validation_rules"][1]["known_values"]
            if key in known:
                expected = known[key]
                actual = extract_fire_rating_from_answer(answer)
                if actual and actual != expected:
                    warnings.append({
                        "level": "ERROR",
                        "type": "table_value_mismatch",
                        "message": f"查 {key} 应为 {expected}，但回答给出 {actual}",
                        "fix_suggestion": f"正确值为 {expected}"
                    })

    return {
        "has_table_lookup": bool(tables_cited),
        "warnings": warnings,
        "should_regenerate": any(w["level"] == "ERROR" for w in warnings)
    }
```

**当 post-check 发现 ERROR 时**，自动触发一次重新生成，在新的 prompt 中注入修正信息：

```python
if check_result["should_regenerate"]:
    correction_context = "\n".join([
        f"⚠️ CORRECTION: {w['message']}. {w.get('fix_suggestion', '')}"
        for w in check_result["warnings"]
        if w["level"] == "ERROR"
    ])

    # 重新生成，注入修正
    corrected_answer = await generator.generate_answer(
        query=query,
        chunks=chunks,
        additional_context=f"\n\nIMPORTANT CORRECTIONS:\n{correction_context}\n\nPlease regenerate the answer with these corrections applied."
    )
```

---

### 3.6 改进 E：条件分支 Chunk 增强（P1）

**核心问题**：SOLAS 很多法规的结构是"同一个 Regulation 下按船型/条件分成多个 sub-section"，但 chunk 只截取了其中一段，丢失了"我是哪个分支"的上下文。

#### 3.6.1 为条件分支 chunk 添加"路径前缀"

在 chunking 时，为每个 chunk 的文本前面加上其在法规树中的完整路径：

```
原始 chunk 文本:
"2.4.2.1 In lieu of paragraph 2.3 and in addition to complying with the specific
provisions for fire integrity of bulkheads and decks of tankers, the minimum fire
integrity of bulkheads and decks shall be as prescribed in tables 9.7 and 9.8."

改进后:
"[SOLAS II-2 / Regulation 9 / 2.4 Tankers / 2.4.2 Fire integrity of bulkheads and decks]
2.4.2.1 In lieu of paragraph 2.3 and in addition to complying with the specific
provisions for fire integrity of bulkheads and decks of tankers, the minimum fire
integrity of bulkheads and decks shall be as prescribed in tables 9.7 and 9.8."
```

这个"路径前缀"在向量化时会被编码，使得搜索 "tanker fire integrity" 时，这个 chunk 的相似度会高于 2.3（non-tanker）的 chunk。

#### 3.6.2 批量修复脚本

```python
# scripts/fix_conditional_branch_chunks.py

"""为 SOLAS 条件分支法规的 chunks 添加路径前缀和 applicability 元数据"""

# 需要修复的法规清单
CONDITIONAL_REGULATIONS = [
    {
        "regulation": "SOLAS II-2/Reg 9",
        "branches": [
            {
                "section_prefix": "2.1",
                "path": "SOLAS II-2 / Regulation 9 / 2.1 Passenger ships (>36 passengers)",
                "applicability": {"ship_types": ["passenger_ship_gt36"]},
                "tables": ["9.1", "9.2"]
            },
            {
                "section_prefix": "2.2",
                "path": "SOLAS II-2 / Regulation 9 / 2.2 Passenger ships (≤36 passengers)",
                "applicability": {"ship_types": ["passenger_ship_le36"]},
                "tables": ["9.3", "9.4"]
            },
            {
                "section_prefix": "2.3",
                "path": "SOLAS II-2 / Regulation 9 / 2.3 Cargo ships other than tankers",
                "applicability": {"ship_types": ["cargo_ship_non_tanker"],
                                  "ship_type_exclusions": ["tanker"]},
                "tables": ["9.5", "9.6"]
            },
            {
                "section_prefix": "2.4",
                "path": "SOLAS II-2 / Regulation 9 / 2.4 Tankers",
                "applicability": {"ship_types": ["tanker"]},
                "tables": ["9.7", "9.8"]
            },
        ]
    },
    {
        "regulation": "SOLAS II-2/Reg 10",
        "branches": [
            {
                "section_prefix": "2",
                "path": "SOLAS II-2 / Regulation 10 / 2 Passenger ships",
                "applicability": {"ship_types": ["passenger_ship"]},
            },
            {
                "section_prefix": "4",
                "path": "SOLAS II-2 / Regulation 10 / 4 Cargo ships",
                "applicability": {"ship_types": ["cargo_ship"]},
            },
        ]
    },
    # ... 扩展更多条件分支法规
]
```

---

### 3.7 改进 F：回归测试扩展（P1）

#### 3.7.1 防火分隔查表专项测试

```python
# tests/test_fire_integrity_tables.py

"""SOLAS II-2/Reg 9 防火分隔表格查询回归测试"""

import pytest

# ============ 船型 → 表格路由测试 ============

SHIP_TYPE_TABLE_ROUTING = [
    # (查询描述, 预期表格, 不应出现的表格)
    ("对于oil tanker，控制站和走廊之间的舱壁防火等级", "9.7", ["9.5", "9.3", "9.1"]),
    ("运输可燃液体货物的轮船，走廊和消防控制站之间", "9.7", ["9.5"]),
    ("化学品船的机舱和居住区之间", "9.7", ["9.5"]),
    ("散货船控制站和走廊之间的防火等级", "9.5", ["9.7"]),
    ("集装箱船机舱和居住区之间的防火分隔", "9.5", ["9.7"]),
    ("客船超过36名旅客，走廊和控制站之间", "9.1", ["9.5", "9.7"]),
]

@pytest.mark.parametrize("query,expected_table,excluded_tables", SHIP_TYPE_TABLE_ROUTING)
def test_ship_type_routes_to_correct_table(query, expected_table, excluded_tables):
    response = call_rag_api(query)
    answer = response["answer"]

    # 应包含正确的表格引用
    assert f"Table {expected_table}" in answer or f"表 {expected_table}" in answer, \
        f"Expected Table {expected_table} in answer for query: {query}"

    # 不应包含错误的表格引用
    for ex_table in excluded_tables:
        assert f"Table {ex_table}" not in answer, \
            f"Should NOT cite Table {ex_table} for query: {query}"


# ============ 查表数值准确性测试 ============

TABLE_VALUE_CASES = [
    # (查询, 预期值, 不应出现的错误值)
    ("油轮走廊和控制站之间的舱壁防火等级", "A-0", ["A-60"]),
    ("散货船走廊和控制站之间的舱壁防火等级", "A-0", ["A-60"]),
    ("油轮控制站和居住区之间的舱壁防火等级", "A-60", ["A-0"]),
    ("油轮走廊和A类机器处所之间", "A-60", ["A-0"]),
    ("散货船走廊和A类机器处所之间", "A-60", ["A-0"]),
    ("油轮居住区和A类机器处所之间", "A-60", ["A-0"]),
    ("散货船控制站和低风险服务处所之间", "A-15", ["A-60", "A-0"]),
    ("散货船走廊和走廊之间的防火等级", "C", ["A-0", "A-60"]),
]

@pytest.mark.parametrize("query,expected_value,wrong_values", TABLE_VALUE_CASES)
def test_table_value_accuracy(query, expected_value, wrong_values):
    response = call_rag_api(query)
    answer = response["answer"]

    # 应包含正确值
    assert expected_value in answer, \
        f"Expected '{expected_value}' in answer for: {query}, got: {answer[:200]}"

    # 不应包含错误值（如果存在明确的错误值）
    for wrong in wrong_values:
        # 需要更精确的匹配，避免误报
        # 例如 answer 中可能提到 "A-60" 是其他场景的值
        pass  # 根据实际情况细化


# ============ 边界条件测试 ============

def test_query_without_ship_type_asks_for_clarification():
    """不指定船型时应该追问"""
    response = call_rag_api("走廊和控制站之间的防火等级是多少")
    answer = response["answer"]
    # 应该要求用户明确船型，或列出不同船型的结果
    assert ("船型" in answer or "ship type" in answer.lower()
            or "tanker" in answer.lower()
            or "Table 9.5" in answer and "Table 9.7" in answer)


def test_tanker_definition_awareness():
    """系统应该理解 tanker 的 SOLAS 定义"""
    response = call_rag_api("根据SOLAS，什么是tanker？tanker的防火分隔用哪个表格？")
    answer = response["answer"]
    assert "可燃" in answer or "flammable" in answer.lower() or "inflammable" in answer.lower()
    assert "9.7" in answer or "9.8" in answer
```

#### 3.7.2 通用查表回归测试框架

```python
# tests/test_table_lookups.py

"""通用法规查表准确性测试框架"""

# 所有需要查表的 known good cases
KNOWN_TABLE_LOOKUPS = [
    # SOLAS II-2/Reg 9 — 防火分隔
    {"query": "油轮控制站vs走廊舱壁",  "table": "9.7", "row": 1, "col": 2, "value": "A-0"},
    {"query": "油轮控制站vs居住区舱壁", "table": "9.7", "row": 1, "col": 3, "value": "A-60"},
    {"query": "油轮控制站vs梯道舱壁",  "table": "9.7", "row": 1, "col": 4, "value": "A-0"},
    {"query": "油轮走廊vsA类机器处所",  "table": "9.7", "row": 2, "col": 6, "value": "A-60"},
    {"query": "货船控制站vs走廊舱壁",  "table": "9.5", "row": 1, "col": 2, "value": "A-0"},
    {"query": "货船控制站vs居住区",    "table": "9.5", "row": 1, "col": 3, "value": "A-60"},
    {"query": "货船走廊vs走廊",       "table": "9.5", "row": 2, "col": 2, "value": "C"},
    {"query": "货船走廊vsA类机器处所",  "table": "9.5", "row": 2, "col": 6, "value": "A-60"},

    # 可扩展: MARPOL 排放限值、Load Line 干舷计算等
]
```

---

## 四、同类 Bad Case 排查清单

基于此 bad case 暴露的问题模式，以下场景极可能存在类似 bug：

### 4.1 高风险同类场景

| # | 场景 | 潜在 Bug 类型 | 排查方法 |
|---|---|---|---|
| 1 | SOLAS II-2/Reg 10 灭火系统要求（客船 vs 货船分支） | 船型→条款路由错误 | 问"油轮机舱需要什么灭火系统" |
| 2 | SOLAS III 救生设备（客船 vs 货船，不同配备数量） | 同上 | 问"油轮需要多少救生筏" |
| 3 | MARPOL Annex I Reg 14 油水分离器排放限值（特殊区域 vs 非特殊区域） | 区域条件分支错误 | 问"在波罗的海可以排放含油污水吗" |
| 4 | MARPOL Annex VI Reg 13 NOx 排放限值（Tier I/II/III） | 时间条件分支错误 | 问"2020年以后建造的船 NOx 限值" |
| 5 | SOLAS II-2 Table 9.1-9.8 甲板防火等级（Table 9.2/9.4/9.6/9.8） | 舱壁 vs 甲板表格混淆 | 问"油轮控制站和走廊之间的甲板防火等级" |
| 6 | SOLAS II-1/Reg 3-2 结构标准（新船 vs 现有船） | 建造年代分支错误 | 问"2005年建造的船防腐蚀要求" |
| 7 | Load Line 干舷计算（A型 vs B型干舷） | 干舷类型分支错误 | 问"散货船的最小夏季干舷" |

### 4.2 立即执行的验证测试

```bash
# 对以上 7 个场景各跑一个查询，人工审核结果
# 记录哪些场景存在同类 bug

python scripts/run_badcase_sweep.py --cases "
  油轮走廊和控制站之间的舱壁防火等级是什么
  散货船走廊和控制站之间的舱壁防火等级是什么
  油轮控制站和走廊之间的甲板防火等级是什么
  油轮机舱需要配备什么固定灭火系统
  散货船需要配备多少救生筏
  在MARPOL特殊区域内含油污水排放标准是多少ppm
  2021年建造的船舶NOx排放限值是多少
"
```

---

## 五、执行优先级与排期

### Phase 1（立即修复，1-3 天）— 止血

| 任务 | 优先级 | 工作量 | 效果 |
|---|---|---|---|
| **C. System Prompt 防幻觉增强** | P0 | 2h | 防止 LLM 编造表格数据 |
| **B-诊断. 运行 diagnose_table_chunks.py** | P0 | 1h | 确认表格 chunks 的实际状态 |
| **B-修复. 重新 chunk Table 9.1-9.8** | P0 | 4h | 修复防火分隔表格数据 |
| **F-核心. 跑 7 个高风险同类场景测试** | P0 | 2h | 确认 bug 范围 |

### Phase 2（系统性修复，3-5 天）

| 任务 | 优先级 | 工作量 |
|---|---|---|
| **A. 法规分支路由元数据（applicability）** | P0 | 2 天 |
| **E. 条件分支 Chunk 路径前缀** | P1 | 1 天 |
| **D. 查表验证 Post-check** | P1 | 1.5 天 |
| **F-完整. 回归测试全套** | P1 | 1 天 |

### Phase 3（扩展到其他法规）

| 任务 | 工作量 |
|---|---|
| 排查 MARPOL、Load Line 等的条件分支法规 | 2-3 天 |
| 为所有二维矩阵表格做结构化 chunk | 3-5 天 |
| 构建完整的 known_table_lookups 验证集 | 持续 |

---

## 六、验收标准

修复完成后，以下查询必须全部返回正确结果：

| # | 查询 | 正确答案 | 关键验证点 |
|---|---|---|---|
| 1 | 运输可燃液体货物的轮船，走廊和控制站之间的舱壁防火等级 | **A-0**（Table 9.7） | 识别为 tanker → 2.4 → Table 9.7 |
| 2 | 散货船走廊和控制站之间的舱壁防火等级 | **A-0**（Table 9.5） | 识别为非 tanker → 2.3 → Table 9.5 |
| 3 | 油轮控制站和居住区之间的舱壁防火等级 | **A-60**（Table 9.7） | 值读取准确 |
| 4 | 散货船走廊和A类机器处所之间的舱壁防火等级 | **A-60**（Table 9.5） | 值读取准确 |
| 5 | 油轮走廊和走廊之间的舱壁防火等级 | **C**（Table 9.7） | 低等级值读取准确 |
| 6 | 油轮控制站和走廊之间的甲板防火等级 | 查 Table 9.8 | 区分舱壁 vs 甲板表格 |
| 7 | 客船（36人以上）控制站和走廊之间的舱壁防火等级 | 查 Table 9.1 | 客船路由正确 |
