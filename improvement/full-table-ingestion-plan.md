# BV-RAG 全量法规表格结构化入库方案

> **目标：将 IMO 公约中所有关键表格以结构化文本格式入库 Qdrant，彻底消除"查表靠模型兜底"的问题**

---

## 一、为什么要做全量表格入库

当前 Qdrant 中 283K+ chunks 来自 PDF/HTML 解析，表格在这个过程中大概率被破坏：

| 表格类型 | PDF 解析后的典型问题 |
|---|---|
| 二维矩阵（防火分隔表） | 行列关系丢失，数值和标题分离 |
| 多列对照表（设备要求表） | 列合并、串行、断裂 |
| 公式表（排放限值） | 上标/下标丢失，公式变乱码 |
| 带脚注的表格 | 脚注与表格分到不同 chunks |
| 跨页表格 | 被截成两个不完整 chunks |

**结构化入库 = 人工审核过的"真值表"**。LLM 不需要从破碎的 chunk 中猜测表格内容，直接读取完整的、自描述的结构化文本。

---

## 二、执行方法论

### 2.1 四阶段流程

```
阶段 1：扫描诊断（自动化）
  ↓ 扫描 Qdrant 中所有包含 "Table" / "表" 的 chunks
  ↓ 输出：现有表格 chunks 清单 + 质量评估
  
阶段 2：表格清单编制（半自动 + 人工审核）
  ↓ 从公约目录中提取全量表格清单
  ↓ 按优先级排序
  ↓ 输出：需要入库的表格全量清单 + 结构化模板
  
阶段 3：数据提取 + 结构化（批量执行）
  ↓ 从 imorules.com / 已有 chunks / PDF 提取表格原始数据
  ↓ 转换为结构化文本格式
  ↓ 人工校验关键数值
  ↓ 输出：结构化表格 JSON 文件
  
阶段 4：入库 + 验证（自动化）
  ↓ 批量写入 Qdrant（带 metadata + applicability 标注）
  ↓ 检索验证每张表格可被正确命中
  ↓ 回归测试确认无破坏
```

### 2.2 表格分类体系

所有海事法规表格归为 5 种类型，每种有不同的结构化模板：

| 类型 | 特征 | 示例 | 模板 |
|---|---|---|---|
| **TYPE-A：二维查找矩阵** | 行列交叉取值 | SOLAS Table 9.1-9.8 | 矩阵格式 |
| **TYPE-B：阈值/限值表** | 按条件查数值 | MARPOL NOx/SOx 限值 | 条件→值格式 |
| **TYPE-C：设备配备表** | 按船型/吨位查要求 | SOLAS III 救生设备 | 清单格式 |
| **TYPE-D：计算参数表** | 多参数计算用 | Load Line 干舷修正表 | 参数格式 |
| **TYPE-E：分类/定义表** | 分类标准对照 | SOLAS II-2 处所分类 | 定义格式 |

---

## 三、全量表格清单

### 3.1 SOLAS（海上人命安全公约）

#### SOLAS Chapter II-1：构造 — 结构、分舱、稳性

| 表格 | 内容 | 类型 | 优先级 | 数据来源 |
|---|---|---|---|---|
| Reg 2 — 定义表 | 新船/现有船的日期界定 | TYPE-E | P2 | imorules |
| Reg 5-1 — Table: Extent of damage | 破舱范围假设值 | TYPE-D | P2 | imorules |
| Reg 7-2 — Table: Permeability values | 渗透率假设值表 | TYPE-D | P2 | imorules |
| Reg 8 — Residual stability criteria | 剩余稳性标准值 | TYPE-B | P1 | imorules |
| Reg 25-8 — Table: Minimum bow height | 最小艏高表 | TYPE-D | P1 | imorules |
| Reg 35-1 — Bilge pumping arrangements | 舱底水排量计算表 | TYPE-D | P2 | imorules |

#### SOLAS Chapter II-2：构造 — 防火、探火、灭火 ⭐ 最高优先级

| 表格 | 内容 | 类型 | 优先级 | 维度 | 数据状态 |
|---|---|---|---|---|---|
| **Table 9.1** | 客船>36人 舱壁防火等级 | TYPE-A | **P0** | 14×14 | ❌ 未入库 |
| **Table 9.2** | 客船>36人 甲板防火等级 | TYPE-A | **P0** | 14×14 | ❌ 未入库 |
| **Table 9.3** | 客船≤36人 舱壁防火等级 | TYPE-A | **P0** | 11×11 | ❌ 未入库 |
| **Table 9.4** | 客船≤36人 甲板防火等级 | TYPE-A | **P0** | 11×11 | ❌ 未入库 |
| **Table 9.5** | 货船非tanker 舱壁防火等级 | TYPE-A | **P0** | 11×11 | ❌ 部分数据有（截图） |
| **Table 9.6** | 货船非tanker 甲板防火等级 | TYPE-A | **P0** | 11×11 | ❌ 未入库 |
| **Table 9.7** | Tanker 舱壁防火等级 | TYPE-A | **P0** | 10×10 | ✅ 已入库（badcase修复） |
| **Table 9.8** | Tanker 甲板防火等级 | TYPE-A | **P0** | 10×10 | ❌ 未入库 |
| Reg 3 — 处所分类定义 | 14类处所定义 | TYPE-E | **P0** | — | 需确认 |
| Reg 4.2 — 逃生路径最低宽度 | 按人数查宽度 | TYPE-B | P1 | — | imorules |
| Reg 5 — 逃生设施要求表 | 按船型/甲板查 | TYPE-C | P1 | — | imorules |
| Reg 7 — 探火系统配置表 | 按处所类型查 | TYPE-C | P1 | — | imorules |
| Reg 10 — 灭火系统配备要求 | 按船型+处所查 | TYPE-C | **P0** | — | imorules |
| Reg 13 — 逃生通道布置 | 逃生距离限值 | TYPE-B | P1 | — | imorules |
| Reg 17 — 可替代设计和布置 | 评估标准表 | TYPE-E | P2 | — | imorules |

#### SOLAS Chapter III：救生设备和装置

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 21** — 客船救生设备配备 | 救生筏/救生艇数量和容量 | TYPE-C | **P0** |
| **Reg 31** — 货船救生设备配备 | 救生筏/救生艇数量和容量 | TYPE-C | **P0** |
| Reg 32 — 个人救生设备 | 救生衣/救生圈数量 | TYPE-C | P1 |
| Reg 34 — 救生设备的存放 | 存放位置和高度要求 | TYPE-B | P2 |
| Reg 36 — 船上培训和演习 | 演习频率和内容 | TYPE-C | P1 |

#### SOLAS Chapter IV：无线电通信

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 7-14** — GMDSS 设备配备表 | 按航区(A1-A4)查设备 | TYPE-C | **P0** |

#### SOLAS Chapter V：航行安全

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 19** — 航行设备配备表 | 按吨位查设备 | TYPE-C | **P0** |
| Reg 18 — VDR/S-VDR 要求 | 按船型/吨位/日期 | TYPE-B | P1 |
| Reg 22 — 驾驶台可视范围 | 角度和距离要求 | TYPE-B | P1 |

#### SOLAS Chapter VI/VII：货物运输/危险品运输

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| Reg VI/5-6 — 载荷信息要求 | 按货物类型 | TYPE-C | P2 |
| Reg VII — 危险品分类表 | 9类危险品分类 | TYPE-E | P1 |

#### SOLAS Chapter XII：散货船安全附加措施

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 5-6** — 散货船结构强度要求 | 按船龄/载荷查 | TYPE-B | P1 |

---

### 3.2 MARPOL（防止船舶造成污染公约）

#### MARPOL Annex I：防止油污染

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 14** — 油水分离设备要求 | 按吨位查设备配备 | TYPE-C | **P0** |
| **Reg 15** — 机舱含油污水排放标准 | 通用海域 vs 特殊区域 | TYPE-B | **P0** |
| **Reg 34** — 油轮货舱区排放标准 | 排放速率/总量限值 | TYPE-B | **P0** |
| Reg 12A — 油类燃料舱保护 | 舱容限值表 | TYPE-B | P1 |
| Reg 13G/13H — 双壳要求时间表 | 淘汰日期表 | TYPE-B | P1 |
| Reg 19 — 特殊区域清单 | 各附则特殊区域定义 | TYPE-E | **P0** |
| Reg 36 — 油类记录簿代码表 | 操作代码对照 | TYPE-E | P1 |

#### MARPOL Annex II：散装有毒液体物质

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 13** — NLS 排放标准 | 按类别(X/Y/Z)查限值 | TYPE-B | P1 |
| Appendix I — 有毒液体分类表 | 物质分类清单 | TYPE-E | P2 |

#### MARPOL Annex III：有害包装物质

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| 标识和标签要求 | 按 IMDG 分类 | TYPE-E | P2 |

#### MARPOL Annex IV：生活污水

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 11** — 生活污水排放标准 | 距岸距离/处理要求 | TYPE-B | **P0** |
| Reg 9 — 生活污水处理装置配备 | 按吨位/人数查 | TYPE-C | P1 |

#### MARPOL Annex V：垃圾

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 4** — 垃圾排放标准表 | 按垃圾类型×区域查 | TYPE-A | **P0** |
| Reg 10 — 垃圾管理计划要求 | 按吨位查 | TYPE-C | P1 |

#### MARPOL Annex VI：防止空气污染

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 13** — NOx 排放限值 Tier I/II/III | 按建造日期+转速 | TYPE-B | **P0** |
| **Reg 14** — SOx/燃油硫含量限值 | 按日期+区域查 | TYPE-B | **P0** |
| Reg 18 — 燃油质量要求 | 参数标准表 | TYPE-B | P1 |
| Reg 22A — EEDI/EEXI 要求值 | 按船型×载重吨 | TYPE-D | P1 |
| Reg 26 — CII 评级界限 | 按船型×年度 | TYPE-D | P1 |
| Reg 12 — ODS 控制要求 | 物质清单+淘汰日期 | TYPE-E | P2 |

---

### 3.3 国际载重线公约 (Load Line Convention)

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Reg 27** — 基本干舷表(A型) | 按船长查干舷 | TYPE-D | P1 |
| **Reg 28** — 基本干舷表(B型) | 按船长查干舷 | TYPE-D | P1 |
| Reg 29 — 方形系数修正 | 修正公式+表 | TYPE-D | P2 |
| Reg 30 — 深度修正 | 修正公式+表 | TYPE-D | P2 |
| Reg 31 — 上层建筑修正 | 按上建长度比查 | TYPE-D | P2 |
| Reg 33 — 艏高要求表 | 按方形系数查 | TYPE-D | P2 |
| Reg 40-51 — 各航区干舷 | 热带/冬季/淡水修正 | TYPE-B | P1 |

---

### 3.4 STCW（海员培训、发证和值班标准公约）

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Table A-II/1** — 值班水手适任标准 | 知识/能力/评估标准 | TYPE-C | P1 |
| **Table A-II/2** — 大副/船长适任标准 | 同上 | TYPE-C | P1 |
| **Table A-III/1** — 值班轮机员适任标准 | 同上 | TYPE-C | P1 |
| **Table A-III/2** — 轮机长/大管轮适任标准 | 同上 | TYPE-C | P1 |
| **Table A-IV/2** — GMDSS 操作员适任标准 | 同上 | TYPE-C | P2 |
| **Table A-V** — 特种船舶培训 | 油轮/化学品/液化气 | TYPE-C | P1 |
| **Table A-VI** — 基本安全培训 | 个人安全/求生/消防/急救 | TYPE-C | P1 |
| Reg VIII — 值班安排（休息时间表） | 最低休息时间标准 | TYPE-B | **P0** |

---

### 3.5 COLREG（国际海上避碰规则）

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| Annex I — 号灯和号型位置 | 高度/距离/光弧要求 | TYPE-B | P1 |
| Annex I §2 — 号灯可见距离 | 按船长×灯类型查海里数 | TYPE-A | P1 |
| Annex III — 声号设备 | 频率/声级要求 | TYPE-B | P2 |

---

### 3.6 相关规则（Codes）

#### FSS Code（消防安全系统规则）

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| Ch 5 — CO2 系统计算表 | 储量计算参数 | TYPE-D | P1 |
| Ch 7 — 水雾系统设计参数 | 喷头间距/流量 | TYPE-D | P2 |
| Ch 9 — 固定探火报警系统 | 探头间距/类型选择 | TYPE-C | P1 |

#### LSA Code（救生设备规则）

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| Ch II — 救生圈/救生衣性能标准 | 浮力/标识要求 | TYPE-B | P2 |
| Ch IV — 救生筏性能标准 | 容量/装备清单 | TYPE-C | P1 |

#### IBC Code（散装运输危险化学品规则）

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| **Ch 17/18** — 最低要求总表 | 物质→船型/舱型/设备要求 | TYPE-C | P1 |
| Ch 15 — 特殊要求表 | 特定物质附加要求 | TYPE-C | P2 |

#### IGC Code（散装运输液化气体规则）

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| Ch 19 — 货物/船型兼容性表 | 气体→舱型要求 | TYPE-A | P1 |

#### ISM Code

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| 无复杂表格 | 主要是程序要求 | — | Skip |

#### ISPS Code

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| Part A §7 — 安全等级措施表 | 按安全等级(1/2/3)查措施 | TYPE-C | P2 |

---

### 3.7 IACS 统一要求（Unified Requirements）

| 表格 | 内容 | 类型 | 优先级 |
|---|---|---|---|
| UR S — 结构强度表 | 板厚/骨材尺寸 | TYPE-D | P2 |
| UR W — 焊接要求 | 焊缝尺寸/检验比例 | TYPE-B | P2 |
| UR Z — 检验要求 | 检验范围/频率 | TYPE-C | P1 |

---

## 四、统计与优先级总览

### 4.1 全量统计

| 公约/规则 | P0 表格数 | P1 表格数 | P2 表格数 | 合计 |
|---|---|---|---|---|
| SOLAS II-2 | **10** | 5 | 1 | 16 |
| SOLAS III | **2** | 2 | 1 | 5 |
| SOLAS IV/V | **2** | 2 | 0 | 4 |
| SOLAS 其他 | 0 | 2 | 5 | 7 |
| MARPOL I | **3** | 3 | 0 | 6 |
| MARPOL IV/V/VI | **4** | 3 | 1 | 8 |
| MARPOL 其他 | 0 | 1 | 2 | 3 |
| Load Line | 0 | 4 | 4 | 8 |
| STCW | **1** | 6 | 1 | 8 |
| COLREG | 0 | 2 | 1 | 3 |
| Codes (FSS/LSA/IBC/IGC) | 0 | 5 | 3 | 8 |
| IACS | 0 | 1 | 2 | 3 |
| **合计** | **22** | **36** | **21** | **79** |

### 4.2 执行分批

| 批次 | 范围 | 表格数 | 工作量 | 依赖 |
|---|---|---|---|---|
| **Batch 1** | SOLAS II-2 Table 9.1-9.8 + Reg 3 处所分类 + Reg 10 灭火 | ~10 | 1-2 天 | 有截图数据+已有 9.7 参考 |
| **Batch 2** | MARPOL 排放限值（NOx/SOx/油污水/生活污水/垃圾排放表） | ~8 | 1 天 | 数值已知，结构简单 |
| **Batch 3** | SOLAS III/IV/V 设备配备表（救生/通信/航行） | ~5 | 1 天 | 需从 imorules 提取 |
| **Batch 4** | STCW 休息时间 + COLREG 号灯 + Load Line 干舷 | ~8 | 1-2 天 | 需从 imorules 提取 |
| **Batch 5** | P1 剩余（FSS/LSA/IBC/IACS 等） | ~15 | 2-3 天 | 逐步补充 |
| **Batch 6** | P2 全部 | ~21 | 持续 | 按需补充 |

---

## 五、结构化模板（5 种类型）

### 5.1 TYPE-A：二维查找矩阵

```
=== {公约} {表格编号}: {表格标题} ===
=== Applicable to: {适用船型/条件} ===
=== NOT applicable to: {不适用船型}（use {替代表格}） ===

{行/列类别定义}:
(1) {类别名称}
(2) {类别名称}
...

{矩阵名称} (row × column = value):
(1)×(1)={值}  (1)×(2)={值}  (1)×(3)={值} ...
(2)×(2)={值}  (2)×(3)={值} ...
...

Footnotes:
{脚注 a}: {内容}
{脚注 b}: {内容}
...

LOOKUP INSTRUCTION: This table is symmetric. To find the value between
Category X and Category Y, look up (X)×(Y) or (Y)×(X).
```

### 5.2 TYPE-B：阈值/限值表

```
=== {公约} {条款}: {标题} ===
=== Applicable to: {适用范围} ===

{限值类别 1} — {适用条件描述}:
  {参数条件 1}: {限值} {单位}
  {参数条件 2}: {限值} {单位}
  {参数条件 3}: {公式}

{限值类别 2} — {适用条件描述}:
  {参数条件 1}: {限值} {单位}
  ...

Applicable areas/dates/conditions:
- {条件 1}: {描述}
- {条件 2}: {描述}

IMPORTANT NOTES:
- {关键注意事项}

LOOKUP INSTRUCTION: To determine the applicable limit:
1. Identify {条件1} → {类别}
2. Identify {条件2} → specific limit value
```

### 5.3 TYPE-C：设备配备表

```
=== {公约} {条款}: {标题} ===
=== Applicable to: {适用船型} ===

{条件分类 1}（{条件描述}）:
  Required equipment:
  - {设备1}: {数量/规格} ({法规引用})
  - {设备2}: {数量/规格} ({法规引用})
  ...
  Additional requirements:
  - {附加要求1}
  - {附加要求2}

{条件分类 2}（{条件描述}）:
  Required equipment:
  - {设备1}: {数量/规格}
  ...

Exemptions:
- {豁免条件}

LOOKUP INSTRUCTION: First identify ship type and tonnage/passenger count,
then find the matching section for equipment requirements.
```

### 5.4 TYPE-D：计算参数表

```
=== {公约} {条款}: {标题} ===
=== Applicable to: {适用范围} ===

Base values table:
  {参数} = {值}  when {条件}
  {参数} = {值}  when {条件}
  ...

OR (for continuous tables):
  Ship length (m) | {参数名}
  24              | {值}
  25              | {值}
  ...
  365             | {值}

Correction formulas:
  {修正1}: {公式}  when {条件}
  {修正2}: {公式}  when {条件}

CALCULATION INSTRUCTION:
1. Look up base value for {主参数}
2. Apply correction for {修正条件}
3. Final value = {公式}
```

### 5.5 TYPE-E：分类/定义表

```
=== {公约} {条款}: {标题} ===
=== Purpose: {用途说明} ===

Category (1) — {类别名称}:
  Definition: {定义}
  Examples: {具体例子}
  Related requirements: {相关条款}

Category (2) — {类别名称}:
  Definition: {定义}
  Examples: {具体例子}
  ...

USAGE INSTRUCTION: Use these category definitions when looking up
values in related tables (e.g., Table 9.1-9.8 for fire integrity).
```

---

## 六、Metadata 标准

每张表格入库的 metadata 必须包含以下字段：

```json
{
  // === 必填字段 ===
  "source": "SOLAS | MARPOL | LOAD_LINE | STCW | COLREG | FSS_CODE | LSA_CODE | IBC_CODE | IGC_CODE | IACS",
  "chapter": "II-2",
  "regulation": "9",
  "section": "2.3.3",
  "table_id": "9.5",
  "title": "完整标题（中英文皆可）",
  "content_type": "structured_table",
  "table_type": "TYPE-A | TYPE-B | TYPE-C | TYPE-D | TYPE-E",

  // === applicability 字段（对有条件分支的表格必填）===
  "applicability": {
    "ship_types": ["tanker", "cargo_ship_non_tanker", "passenger_ship", "all"],
    "ship_type_exclusions": ["tanker"],
    "tonnage_condition": ">=500GT",
    "construction_date_condition": "after 2000-01-01",
    "area_condition": "ECA only",
    "applicable_tables": ["9.7", "9.8"]
  },

  // === 可选字段 ===
  "source_url": "https://imorules.com/GUID-xxxx.html",
  "data_verified": true,
  "data_source": "user_screenshot | imorules | pdf_extraction | model_knowledge",
  "last_updated": "2026-02-22",
  "related_tables": ["9.8"],
  "supersedes_chunk_ids": ["旧chunk的Qdrant point_id"]
}
```

---

## 七、执行 Prompt（分批次）

### Batch 1：SOLAS II-2 防火分隔全套（P0，最先执行）

```
你的任务是将 SOLAS II-2 Chapter 中所有关键表格以结构化文本格式写入 Qdrant。

第一步：理解现有入库方式

1. 阅读 scripts/fix_table_chunks.py（badcase 修复时创建的），理解：
   - Qdrant collection name
   - embedding model 和维度
   - metadata 格式
   - chunk 写入方式（upsert / insert）

2. 搜索验证 Table 9.7 的结构化 chunk 确实存在。
   打印它的完整 text + metadata，作为后续入库的格式参考。

3. 搜索以下表格，确认哪些已存在、哪些缺失：
   Table 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
   对每个打印结果（或"未找到"）

第二步：创建 scripts/ingest_structured_tables.py

这个脚本接受一个 JSON 数据文件，批量将结构化表格 chunks 写入 Qdrant。

脚本结构：
- 读取 data/structured_tables.json（包含所有表格的 text + metadata）
- 对每条记录：生成 embedding → 写入 Qdrant
- 如果 Qdrant 中已有同 table_id 的旧 chunk，先删除再插入
- 支持 --dry-run 模式（只验证不写入）
- 支持 --verify 模式（写入后搜索验证每张表格）

第三步：创建 data/structured_tables.json — Batch 1 数据

在这个 JSON 文件中，按以下顺序添加表格。
对每张表格，严格使用 TYPE-A 矩阵模板。

需要入库的表格：

A. SOLAS Reg II-2/3 — 处所分类定义（TYPE-E）
   10类（或14类，客船更多）处所的定义。从 Qdrant 已有 chunks 中提取。
   这是 Table 9.1-9.8 的查表前提——用户问"走廊和控制站"，
   需要先知道走廊=Category(2)、控制站=Category(1)。

B. Table 9.5 — 货船非tanker 舱壁分隔（TYPE-A）
   数据来源：用户提供的截图（Image 5），矩阵数据已在之前的改进方案中整理。
   applicability: cargo_ship_non_tanker, bulk_carrier, container_ship, general_cargo
   exclusions: tanker, passenger_ship

C. Table 9.6 — 货船非tanker 甲板分隔（TYPE-A）
   数据来源：尝试从 Qdrant 已有 chunks 提取。
   如果找不到完整数据，搜索 Qdrant 中任何包含 "Table 9.6" 或 "deck" + "cargo ship" 的 chunks。
   如果仍然找不到完整矩阵数据，创建占位 chunk（标注 data_verified: false）。

D. Table 9.7 — Tanker 舱壁分隔（TYPE-A）
   如果已有结构化 chunk，跳过。
   如果没有或格式不统一，用截图（Image 3）中的完整数据重新入库。

E. Table 9.8 — Tanker 甲板分隔（TYPE-A）
   数据来源：同 Table 9.6 处理方式——先从 Qdrant 找，找不到用占位 chunk。

F. Table 9.1 — 客船>36人 舱壁分隔（TYPE-A）
   数据来源：从 Qdrant 已有 chunks 提取。客船表格更大（14×14），
   如果找不到完整数据，用占位 chunk。

G. Table 9.2 — 客船>36人 甲板分隔（TYPE-A）— 同上处理
H. Table 9.3 — 客船≤36人 舱壁分隔（TYPE-A）— 同上处理
I. Table 9.4 — 客船≤36人 甲板分隔（TYPE-A）— 同上处理

J. SOLAS II-2/Reg 10 — 灭火系统配备要求（TYPE-C）
   从 Qdrant 中搜索 Reg 10 相关 chunks，整理为结构化格式。
   至少要覆盖：
   - 10.2 客船灭火系统要求
   - 10.4 货船灭火系统要求
   - 10.5 CO2 系统参数
   - 10.8/10.9 油轮特殊要求

关键约束：
1. 不要编造数据。如果表格的完整矩阵数据无法确认，
   用占位 chunk 并标注 data_verified: false
2. 占位 chunk 应包含已知数据点 + "For complete data, refer to original regulation" 提示
3. 所有 chunk 的格式必须与已有 Table 9.7 chunk 保持一致
4. 每张表格 1 个 chunk，不要拆分
5. applicability metadata 必须填写，这是检索过滤的关键
```

### Batch 2：MARPOL 排放限值全套（P0）

```
继续在 data/structured_tables.json 中添加以下表格。
运行 scripts/ingest_structured_tables.py 入库。

A. MARPOL Annex VI Reg 13 — NOx Tier I/II/III 排放限值（TYPE-B）
   数据（已知，无需查找）：
   Tier I (2000-2010): n<130→17.0, 130≤n<2000→45.0×n^(-0.2), n≥2000→9.8
   Tier II (2011+): n<130→14.4, 130≤n<2000→44.0×n^(-0.23), n≥2000→7.7
   Tier III (2016+, in ECA): n<130→3.4, 130≤n<2000→9.0×n^(-0.2), n≥2000→2.0
   
   ECA/NECA 清单：
   - North American ECA: 2012.8.1
   - US Caribbean: 2014.1.1
   - North Sea + Baltic NECA: 2021.1.1
   - Mediterranean NECA: 2025.1.1

B. MARPOL Annex VI Reg 14 — SOx/燃油硫含量限值（TYPE-B）
   数据（已知）：
   全球：2020.1.1 起 ≤0.50% m/m（之前 3.50%）
   ECA 内：2015.1.1 起 ≤0.10% m/m（之前 1.00%）
   EU 港口：≤0.10%

C. MARPOL Annex I Reg 15 — 机舱含油污水排放标准（TYPE-B）
   通用海域：≤15ppm，航行中，经油水分离器处理，有 OCM
   特殊区域：同 ≤15ppm，但必须有 15ppm 报警器+自动停止装置
   对于 <10000GT 非特殊区域可豁免部分设备

D. MARPOL Annex I Reg 34 — 油轮货舱区排放标准（TYPE-B）
   特殊区域外：
   - 航行中
   - 瞬时排放速率 ≤30L/nmile
   - 总排放量 ≤1/30000 货物量（现有油轮）或 1/30000（新油轮）
   - 排放监控系统运行
   - 距最近陆地 >50 海里
   特殊区域内：禁止排放

E. MARPOL Annex IV Reg 11 — 生活污水排放标准（TYPE-B）
   已处理：距最近陆地 >3 海里
   未处理：距最近陆地 >12 海里，速度 >4 节，逐步排放
   粉碎消毒后：距最近陆地 >3 海里
   波罗的海特殊区域：2023.6.1 起新标准

F. MARPOL Annex V Reg 4 — 垃圾排放规定表（TYPE-A 矩阵）
   这是一个 垃圾类型 × 排放区域 的矩阵表：
   行：食品废弃物 / 货物残余 / 清洁剂 / 动物尸体 / 食用油 / 一切其他垃圾
   列：特殊区域外(>12nm, 3-12nm, <3nm) / 特殊区域内

G. MARPOL Annex I Reg 19 — 全部公约特殊区域清单（TYPE-E）
   列出每个 Annex 的特殊区域名称和生效日期

每张表格都必须有完整的 applicability metadata 和 LOOKUP INSTRUCTION。
对于无法确认完整数据的，从 Qdrant 搜索现有 chunks 提取。
```

### Batch 3：SOLAS III/IV/V 设备配备表（P0）

```
继续在 data/structured_tables.json 中添加以下表格。

A. SOLAS III Reg 21 — 客船救生设备配备要求（TYPE-C）
   从 Qdrant 搜索 "SOLAS III Reg 21 passenger ship survival craft" 提取
   至少覆盖：救生艇、救生筏、救生圈、救生衣的数量/容量要求

B. SOLAS III Reg 31 — 货船救生设备配备要求（TYPE-C）
   从 Qdrant 搜索 "SOLAS III Reg 31 cargo ship survival craft" 提取
   关键要点：
   - 救生筏总容量 = 200% 全船人员（可两舷转移时）
   - ≥85m 货船至少一舷 davit-launched
   - Free-fall 救生艇不免除 davit 要求

C. SOLAS IV Reg 7-14 — GMDSS 设备配备表（TYPE-C）
   按航区 A1/A2/A3/A4 列出必备/可选设备

D. SOLAS V Reg 19 — 航行设备配备表（TYPE-C）
   按吨位分档（<150GT, 150-300, 300-500, 500-3000, 3000-10000,
   10000-50000, ≥50000）列出必备航行设备

E. STCW Reg VIII — 船员值班和休息时间要求（TYPE-B）
   最低休息时间：24小时内 ≥10h，7天内 ≥77h
   休息时间可分为不超过两段，其中一段至少6h
   连续两段休息之间不超过14h
```

### Batch 4-6：按需继续

P1 和 P2 表格按照上述模式继续扩展，不再逐一写 prompt。
关键原则不变：先从 Qdrant 搜索已有数据，有则提取结构化，无则标注 TODO。

---

## 八、验证框架

### 8.1 入库后自动验证脚本

```
创建 scripts/verify_table_ingestion.py：

对 data/structured_tables.json 中的每张表格：
1. 用 3 个不同的自然语言查询搜索 Qdrant
   （例如 Table 9.5 用："cargo ship corridor control station fire rating"、
   "散货船走廊控制站防火等级"、"SOLAS Table 9.5"）
2. 检查是否在 top-3 结果中命中
3. 检查命中的 chunk 的 content_type == "structured_table"
4. 检查 applicability metadata 是否完整
5. 输出验证报告：PASS / FAIL / NOT_FOUND

期望结果：所有入库的表格在 3 种查询方式中至少 2 种命中 top-3。
```

### 8.2 扩展 post-check known values

```
每入库一张新的 TYPE-A 矩阵表，同步在 generation/table_post_check.py 中
添加该表的 known values。

例如 Table 9.5 入库后，添加：
"Table 9.5|(1)|(2)": "A-0",
"Table 9.5|(1)|(3)": "A-60",
... （至少覆盖高频查询的 category 交叉点）

同步在 tests/test_table_post_check.py 中添加对应测试。
```

### 8.3 端到端回归测试

```
每完成一个 Batch 的入库，跑以下查询验证：

Batch 1 验证：
- 油轮走廊vs控制站舱壁 → A-0, Table 9.7, 不说"未找到"
- 散货船走廊vs控制站舱壁 → A-0, Table 9.5, 不说"未找到"
- 油轮控制站vs走廊甲板 → A-0, Table 9.8, 不说"未找到"
- 客船(36人以上)走廊vs机舱舱壁 → Table 9.1
- 油轮居住区vs机舱舱壁 → A-60, Table 9.7
- 集装箱船机舱vs货泵舱甲板 → Table 9.6

Batch 2 验证：
- 2021年建造的船NOx限值 → Tier III, 具体数值, 不说"未找到"
- 2025年ECA内燃油硫含量限值 → 0.10%
- 波罗的海排放含油污水标准 → 15ppm
- 油轮特殊区域内可以排放货舱洗舱水吗 → 禁止

Batch 3 验证：
- 散货船需要多少救生筏 → 200%
- A3航区需要什么通信设备 → GMDSS 设备清单
- 50000GT 船需要什么航行设备 → 设备清单
- 船员最低休息时间 → 24h内10h, 7天77h
```

---

## 九、长期维护机制

### 9.1 新法规修正案入库流程

```
1. IMO 发布修正案 → 人工识别受影响的表格
2. 更新 data/structured_tables.json 中对应记录
3. 运行 scripts/ingest_structured_tables.py --update
4. 运行 scripts/verify_table_ingestion.py
5. 更新 table_post_check.py 中的 known values
6. 跑端到端回归测试
```

### 9.2 缺失表格识别机制

在 system prompt 中已有的"未检索到原文"警告基础上，增加自动记录：

```python
# 在 pipeline 中：如果 LLM 回答包含 "未检索到" / "未找到" / "基于模型知识"
# 自动记录到 missing_tables_log.jsonl

{
  "timestamp": "2026-02-22T06:00:00Z",
  "query": "油轮控制站和走廊之间的甲板防火等级",
  "missing_reference": "Table 9.8",
  "confidence_level": "medium"
}
```

每周审查这个日志，识别高频缺失的表格，优先入库。
