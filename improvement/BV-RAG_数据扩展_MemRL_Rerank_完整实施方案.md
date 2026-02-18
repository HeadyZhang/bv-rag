# BV-RAG 数据扩展 + 工业级Rerank升级 — 完整实施方案

> **目标**: 将 BV Rules (130+ 出版物) + IACS UR/UI/Rec (200+ 决议) 全量注入现有RAG系统，同时引入 MemRL 启发的 Utility-Aware Reranking 机制
> 
> **执行方式**: Claude Code 可直接执行的分轮 Prompt
> 
> **预估新增数据**: ~150,000-250,000 chunks (当前 24,476 → 目标 ~200,000-270,000)

---

## 第一部分: 数据源深度探查

### 1.1 Bureau Veritas Marine & Offshore Rules

**网站**: `https://marine-offshore.bureauveritas.com/rules-guidelines`

**内容结构** (经过实际爬取验证):

| 分类 | 编号体系 | 数量 | 文件格式 | 示例 |
|------|---------|------|---------|------|
| Rules for Classification | NR + 3位数字 | ~30 | PDF (合并版 Consolidated) | NR467 钢质船舶, NR217 内河船舶 |
| Rule Notes | NR + 3位数字 | ~50 | PDF | NR216 材料焊接, NR526 起重设备 |
| Guidance Notes | NI + 3位数字 | ~50 | PDF | NI615 网络安全, NI675 无人船 |
| Technical Documents | 杂项 | ~10 | PDF | 技术通告, 修正勘误 |

**关键发现**:
- PDF 下载链接模式: `https://erules.veristar.com/dy/data/bv/pdf/{NR编号}-NR_Consolidated_{日期}.pdf`
- 部分需要 Veristar 登录（免费注册）
- eRules 在线版可直接抓取 HTML: `https://erules-svc-ppr.veristar.com/`
- NR467 (钢质船舶规范) 是最核心出版物，合并版 PDF 超过 2000 页

**优先级排序** (对验船师问答价值):
1. **P0 核心**: NR467 (钢质船舶), NR216 (材料焊接), NR445 (海上装置), NR483 (军舰)
2. **P1 重要**: NR217 (内河船), NR526 (起重设备), NR544 (设备材料认证)
3. **P2 参考**: NI 系列 Guidance Notes (网络安全, 新燃料, 噪声振动等)

### 1.2 IACS (International Association of Classification Societies)

**网站**: `https://iacs.org.uk/`

**内容结构**:

| 分类 | 编号体系 | 类别数 | 文件格式 | 说明 |
|------|---------|--------|---------|------|
| Unified Requirements (UR) | UR + 字母 + 数字 | 17类 | PDF | 船级社必须执行的最低标准 |
| Unified Interpretations (UI) | UI + 公约简称 + 数字 | 10+ 公约 | PDF | IMO 公约的统一解释 |
| Procedural Requirements (PR) | PR + 数字 | ~40 | PDF | 程序性要求 |
| Recommendations (Rec) | Rec + 数字 | ~100 | PDF | 行业推荐 |
| Common Structural Rules (CSR) | CSR BC & OT | 1套 | PDF | 散货船+油轮共同结构规范 |

**UR 17 个类别 (全量爬取)**:
- **A** - 系泊与锚泊 (Mooring & Anchoring)
- **C** - 集装箱 (Containers)
- **D** - 移动式海洋钻井平台 (MODU)
- **E** - 电气与电子 (Electrical & Electronic)
- **F** - 防火 (Fire Protection)
- **G** - 气体运输船 (Gas Tankers)
- **H** - 新燃料与其他能源 (New Fuels)
- **I** - 极地船舶 (Polar Class)
- **K** - 螺旋桨 (Propellers)
- **L** - 分舱/稳性/载重线 (Subdivision, Stability & Load Line)
- **M** - 机械装置 (Machinery)
- **N** - 航行 (Navigation)
- **P** - 管路与压力容器 (Pipes & Pressure Vessels)
- **S** - 船体强度 (Strength of Ships)
- **W** - 材料与焊接 (Materials & Welding)
- **Z** - 检验与证书 (Survey & Certification)

**关键发现**:
- IACS 网站返回 403 (Cloudflare 防爬)，需要模拟浏览器或使用 Playwright/Selenium
- 每个 UR/UI 详情页有 "VIEW PDF" 和 "DOWNLOAD FILE" 链接
- PDF 链接格式: 直接 PDF 下载链接嵌入在页面中
- 每个 UR 有多个版本 (Rev1, Rev2...) + 修正 (Corr.1) + 带下划线版 (UL)
- **只需下载最新 Clean 版** (CLN)，不需要历史版本

**UI (统一解释) 覆盖的公约**:
- UI SC (SOLAS), UI LL (Load Lines), UI MPC (MARPOL)
- UI GC (Gas Code), UI FP (Fire Protection), UI EP (Electrical)
- 与现有 IMO 法规数据形成完美互补

### 1.3 数据获取方式决策

| 数据源 | 格式 | 获取方式 | 理由 |
|--------|------|---------|------|
| BV Rules 目录页 | HTML | Scrapy 爬取 | 获取所有出版物列表+PDF链接 |
| BV Rules PDF | PDF | 批量下载 | 核心法规内容全在 PDF 中 |
| BV eRules | HTML | Scrapy 爬取 (备选) | 部分规范有在线版，结构化更好 |
| IACS 目录页 | HTML | Playwright + BeautifulSoup | Cloudflare 防爬，需无头浏览器 |
| IACS UR/UI PDF | PDF | 批量下载 | 每个决议一个PDF，结构规整 |

**结论**: 两个网站的核心内容都以 **PDF 下载** 为主，HTML 页面主要用于获取目录索引和PDF链接。

---

## 第二部分: 工业界前沿法规RAG方案调研

### 2.1 2024-2025 法规/合规领域 RAG SOTA

基于对 LegalBench-RAG、LRAGE、TrueLaw AI、ZeroEntropy、Graph RAG 合规系统等的调研:

**核心架构趋势**:

1. **Hybrid Search + Cross-Encoder Reranking** (业界标准)
   - 初检: BM25 (精确术语) + Dense Retrieval (语义理解)
   - 重排: Cross-encoder reranker 而非纯 cosine similarity
   - **关键发现**: 通用 reranker (如 Cohere) 在法律领域反而降低性能，需要领域适配

2. **Hierarchical Chunking with Metadata** 
   - 法规文档天然有层级结构 (公约→章→条→款)
   - 每个 chunk 携带完整层级路径 (breadcrumb)
   - 小 chunk 用于精确检索，父级 chunk 提供上下文

3. **Knowledge Graph 增强** (Graph RAG)
   - 法规间的交叉引用构建知识图谱
   - 沿引用链扩展检索结果
   - 你的系统已有 cross_references 表，是正确方向

4. **Multi-Tier Collection 隔离**
   - 不同权威层级的法规分 collection 存储
   - IMO 公约 > IACS UR > 船级社 Rules > Guidance Notes
   - 查询时可按权威层级过滤/加权

5. **Table-Aware Parsing** (你的 P0 问题根源)
   - 法规 PDF 中大量关键信息以表格形式存在
   - 普通 PDF 解析器跳过或破坏表格
   - SOTA 方案: Docling (IBM) 或 LlamaParse 专门处理表格
   - 表格→结构化文本/Markdown 后再 chunk

### 2.2 MemRL 论文核心思想及对 BV-RAG 的适用性分析

**论文**: *MemRL: Self-Evolving Agents via Runtime Reinforcement Learning on Episodic Memory* (SJTU + MemTensor, 2025)

**核心机制**:

```
传统 RAG:  query → 向量召回 top-k → 直接送入 LLM
                    ↑
              纯语义相似度

MemRL 改进: query → Phase A: 向量召回 top-k₁ (宽筛) 
                  → Phase B: Q-value 重排 → 选 top-k₂ (精选)
                                ↑
                    每个 memory 有 utility 分数 (Q-value)
                    基于历史使用效果持续更新
```

**三元组结构**: 每条记忆 = (Intent, Experience, Utility)
- **Intent**: 查询意图的嵌入表示 (用于 Phase A 语义召回)
- **Experience**: 记忆内容 (对应我们的 chunk text)
- **Utility**: Q-value 分数，反映该记忆在历史回答中的实际效用

**Two-Phase Retrieval**:
- **Phase A (语义召回)**: cosine similarity 选出 k₁ 个候选 (宽网)
- **Phase B (价值选择)**: 用 Q-value 对 k₁ 候选重排，选出 k₂ 个最终结果

**Runtime Learning (非参数 RL)**:
- 每次回答后，根据用户反馈或答案质量评分，更新被使用 chunk 的 Q-value
- 使用 EMA (指数移动平均) 更新: `Q_new = α * reward + (1-α) * Q_old`
- 好的 chunk 被多次使用且效果好 → Q-value 升高 → 未来更容易被选中
- 差的 chunk 被使用后效果差 → Q-value 降低 → 逐渐被淘汰

**对 BV-RAG 的适用性评估**:

| 维度 | 适用性 | 说明 |
|------|--------|------|
| 核心思路 | ✅ **强适用** | 法规 chunk 确实存在"看起来相似但实际无用" vs "精确命中" |
| Phase A | ✅ 已有 | 你的 Qdrant 向量搜索 = Phase A |
| Phase B | ⭐ **最大价值** | 用 Q-value 替代/增强当前 RRF 排序 |
| Runtime RL | ⚠️ 需简化 | MemRL 原始设计面向 Agent 任务链，法规问答更简单 |
| 稳定性 | ✅ 有保证 | EMA 更新收敛已有理论证明 |

**BV-RAG 改造方案 — Utility-Aware Reranking**:

我们不需要完整实现 MemRL (它是面向 Agent 的)，而是提取其核心洞察——**给每个 chunk 维护一个 utility score，用于检索后重排**:

```
当前: Vector + BM25 + Graph → RRF 融合 → top_k
改造后: Vector + BM25 + Graph → RRF 融合 → top_k₁ (宽筛)
        → Utility-Aware Reranking → top_k₂ (精选)
        → 回答后更新 utility scores
```

**Utility Score 更新逻辑**:
1. **隐式反馈**: 每次回答后，如果 confidence=high，被引用的 chunk utility += 0.1
2. **负反馈**: 如果 confidence=low 或 answer 包含"无法回答"，被检索但未引用的 chunk utility -= 0.05
3. **EMA 平滑**: `utility = 0.9 * utility + 0.1 * reward`
4. **存储**: PostgreSQL 新增 `chunk_utilities` 表, 以 (chunk_id, query_category) 为键
5. **冷启动**: 新 chunk 默认 utility=0.5，需要 ~10 次使用才稳定

---

## 第 2.5 部分: MemRL 落地三步走（白话版）+ 你需要亲自做的事

> **核心澄清**: MemRL utility reranking **不是一个神经网络模型，不需要 GPU 训练**。
> 它本质上是一个"好评率计数器"——每个 chunk 维护一个分数，用得好就涨，用了没用就降。
> 
> **为什么它解决了通用 Reranker 的问题**: LegalBench-RAG 研究发现 Cohere 等通用 reranker
> 在法规领域反而降低性能，因为它学的是通用"相关性"（看起来像就行），而法规领域的真实需求是
> "这个 chunk 在历史上对这类问题有没有实际帮助"。MemRL utility 不需要预训练的模型，
> 它的"领域适配"是从你自己系统的每一次问答中自然积累出来的——天生领域适配。

### 三步走：具体到 BV-RAG 系统需要做的事

#### 第一步：数据库加一张表（5 分钟）

在 PostgreSQL 里加一张 `chunk_utilities` 表。核心就两个字段：`chunk_id`（哪个法规片段）和 `utility_score`（好用程度）。每个 chunk 初始分数 0.5（中性，代表"还没验证过"）。

额外加了 `query_category` 字段做分桶——同一个 chunk 在"防火"问题下可能很好用（SOLAS II-2/9），但在"稳性"问题下可能无关。分桶让 utility 更精准。

**对应你的代码库**：
- 改动文件：`scripts/seed_data.py`（在建表脚本里加一段 CREATE TABLE）
- 或者直接在 Railway PostgreSQL 里执行一条 SQL

**☑️ Claude Code 能做**：完全自动完成，无需你操作。

#### 第二步：检索后加一步排序（30 行代码）

当前你的检索流程：
```
用户问题 → QueryEnhancer 增强 → Vector搜索 + BM25搜索 + Graph搜索 
→ RRF 融合排序 → 返回 top 5 给 LLM 生成回答
```

改动后的检索流程（只在 RRF 之后插入一步）：
```
用户问题 → QueryEnhancer 增强 → Vector搜索 + BM25搜索 + Graph搜索 
→ RRF 融合排序 → 取 top 10（多拿一些候选）
→ 【新增】Utility Reranking（查每个 chunk 的 utility 分数，跟 RRF 分数加权混合）
→ 重新排序后返回 top 5 给 LLM 生成回答
```

加权公式：`最终分数 = 0.7 × RRF分数 + 0.3 × utility分数`

初期 utility 数据少时 0.3 权重足够保守（RRF 仍然占主导）。等系统跑了几百个问题后，可以调到 0.4 或 0.5。

**对应你的代码库**：
- 新建文件：`retrieval/utility_reranker.py`（一个独立的类，约 80 行）
- 改动文件：`retrieval/hybrid_retriever.py`（在 `retrieve()` 方法里加 3 行调用代码）

**☑️ Claude Code 能做**：完全自动完成，无需你操作。

#### 第三步：回答后更新分数（自动积累，无需人工标注）

每次系统回答完一个问题后，自动执行一次 utility 更新。逻辑很直觉：

**系统自动判断依据**（已经存在于你的系统输出中）：
1. `confidence` 字段 — 你的 LLM 回答时已经输出 high/medium/low
2. `citations` 字段 — 你的 LLM 回答时已经输出引用了哪些 chunk

**更新规则（EMA 指数移动平均）**：

```
新分数 = 0.9 × 旧分数 + 0.1 × 本次奖励
```

| 情况 | 奖励值 | 解释 |
|------|--------|------|
| chunk 被引用 + confidence=high | +1.0 | 这个 chunk 很好用，加大分 |
| chunk 被引用 + confidence=medium | +0.5 | 有用但不够确定，小加分 |
| chunk 被检索但没被引用 + confidence=high | -0.1 | 答案不需要它，轻微扣分 |
| chunk 被检索但没被引用 + confidence=low | -0.3 | 它碍事了（可能是 MODU Code 这种噪声），扣分 |
| 所有 chunk + 回答"无法回答" | -0.5 | 全部候选都没帮上忙，集体扣分 |

**EMA 的好处**：分数变化是渐进的（每次只动 10%），不会因为一次意外就剧烈波动。一个 chunk 需要连续多次表现好/差才会显著改变分数。

**对应你的代码库**：
- 改动文件：`pipeline/voice_qa_pipeline.py`（在回答生成后加 5-8 行 utility 更新代码）
- 改动文件：`api/routes/admin.py`（加一个 `/api/v1/admin/utility-stats` 查看学习统计）

**☑️ Claude Code 能做**：完全自动完成，无需你操作。

---

### 🔴 你需要亲自做的事（Claude Code 做不了的）

绝大部分工作 Claude Code 都能完成（代码编写、数据库改动、部署）。以下是**需要你参与的环节**：

#### 1. 加速冷启动标注（可选但推荐，30-60 分钟）

系统刚上线时所有 chunk utility 都是 0.5，reranking 等于没开。自然积累需要 200-1000 个真实问题才能分化出好坏。

**加速方法**：拿你已有的 8 个回归测试 + 5 个验船师题目，人工跑一遍。每道题看一下系统检索到的 chunks（在 API 返回的 `sources` 字段里），标注哪些是"对的"（应该被引用）、哪些是"噪声"（不应该出现）。

格式很简单，就是一个 JSON 文件：
```json
[
  {
    "query": "货船厨房到走廊的防火等级",
    "category": "fire_safety",
    "good_chunks": ["SOLAS_II-2_Reg9_Table9.3_c0", "SOLAS_II-2_Reg9_Table9.3_c1"],
    "bad_chunks": ["MODU_Code_Ch9_c3", "MODU_Code_Ch9_c7"]
  },
  ...
]
```

Claude Code 会写一个脚本读取这个 JSON 并批量更新 utility（好的设 0.8，坏的设 0.2）。但**判断哪些 chunk 好、哪些坏需要你的海事专业知识**。

**⚠️ 这一步不做也行**，系统会自己慢慢学。但做了之后冷启动阶段的回答质量会立刻提升。

#### 2. 观察 α 参数并调整（部署后 1-2 周）

α 是 RRF 和 utility 的混合权重。初始设 0.3（utility 只占 30%）。

部署后你需要偶尔看一下 `/api/v1/admin/utility-stats` 端点的数据：
- 如果 `avg_uses`（平均使用次数）超过 10 次，说明 utility 数据已经有信号了，可以考虑调到 0.4
- 如果 `high_utility`（分数>0.7 的 chunk 数量）和 `low_utility`（分数<0.3 的 chunk 数量）明显分化，说明系统在学习，可以进一步调高

这不需要频繁操作，部署后第 1 周看一次、第 2 周看一次就行。

**⚠️ 不调也行**，0.3 是一个安全的保守值，不会让系统变差。

#### 3. BV/IACS 数据源的手动验证（如果自动爬取失败）

风险控制表里已经列了：IACS 有 Cloudflare 保护，BV 有些 PDF 可能需要登录。如果 Claude Code 的自动爬虫被拦截，你需要：
- **IACS**：手动在浏览器打开 https://iacs.org.uk/，下载 UR PDF 文件，放到 `data/iacs/raw_pdfs/` 目录
- **BV**：如果 Veristar 要求登录，手动注册一个免费账号，或者从 eRules 网站手动下载 PDF

Claude Code 会提供详细的"哪些文件需要下载"的清单。

#### 4. Qdrant 容量决策（5 分钟）

现有 Qdrant Cloud 免费版是 1GB RAM。加入 BV+IACS 后预估需要约 350MB（170k 向量）。虽然在限额内，但如果后续继续扩展（比如加入 Lloyd's Register 或 DNV 的规范），可能需要升级。

你需要决定：
- **选项 A**：继续用免费版（目前够用）
- **选项 B**：升级到 Qdrant Starter（$25/月，4GB RAM，未来扩展无忧）
- **选项 C**：在 Railway 上自建 Qdrant（$5-10/月，完全自主控制）

Claude Code 可以帮你执行任何一个选项，但需要你做决定。

---

### "训练"时间线 — 什么时候能看到效果

| 阶段 | 累计问答数 | α 建议值 | 系统表现 |
|------|-----------|---------|---------|
| 冷启动 | 0-50 | 0.1-0.2 | utility 基本不起作用，等于现有系统 |
| 加速冷启动（如果做了标注） | 人工标注 13 题 | 0.3 | 标注涉及的领域立即改善，其他领域不变 |
| 早期学习 | 50-200 | 0.3 | 高频领域（防火、稳性）开始分化 |
| 热身完成 | 200-500 | 0.3-0.4 | 多数领域出现明显好坏 chunk 分化 |
| 稳态运行 | 500+ | 0.4-0.5 | MODU Code 污染等问题自然消退 |

**关键认知**：这不是一次性训练，而是**持续自我进化**。系统用得越多越准。你不需要任何 GPU、不需要标注团队、不需要 fine-tune 任何模型。唯一的"训练数据"就是**用户正常使用系统本身**。

---

## 第三部分: 完整技术实施方案

### Phase 0: 环境准备 + PDF 解析工具安装

```
预计耗时: 30分钟
依赖: pip install docling pdfplumber playwright
```

### Phase 1: BV Rules 爬取 + 下载 (2-3小时)

**Step 1.1**: 爬取 BV 出版物目录，提取所有 PDF 下载链接
**Step 1.2**: 批量下载优先级 P0+P1 的 PDF 文件
**Step 1.3**: 使用 Docling 解析 PDF → Markdown (含表格)

### Phase 2: IACS 爬取 + 下载 (2-3小时)

**Step 2.1**: 使用 Playwright 爬取 IACS 所有 UR/UI/PR/Rec 列表页
**Step 2.2**: 提取每个决议的 PDF 下载链接 (最新 CLN 版)
**Step 2.3**: 批量下载并用 Docling 解析

### Phase 3: 统一分块 + 入库 (1-2小时)

**Step 3.1**: PDF→Markdown→Structured Chunks (保留层级元数据)
**Step 3.2**: 生成 embeddings (text-embedding-3-large, 1024d)
**Step 3.3**: 写入 PostgreSQL (regulations + chunks 表) + Qdrant

### Phase 4: 检索优化 — Utility-Aware Reranking (1小时)

**Step 4.1**: PostgreSQL 新增 chunk_utilities 表
**Step 4.2**: HybridRetriever 增加 Phase B 重排逻辑
**Step 4.3**: Pipeline 增加回答后 utility 更新钩子

### Phase 5: Multi-Collection 管理 + 权威层级 (30分钟)

**Step 5.1**: Qdrant 新建 collection: `bv_rules`, `iacs_resolutions`
**Step 5.2**: 检索时跨 collection 搜索 + 权威层级加权
**Step 5.3**: QueryEnhancer 新增 BV/IACS 术语映射

### Phase 6: 验证 + 回归测试 (30分钟)

---

## 第四部分: Claude Code 可执行 Prompt

### 🔥 Prompt 1: 环境准备 + PDF 工具链安装

```
你是一个Python系统工程师。在项目 bv-rag (Railway 部署的海事法规RAG系统) 中完成以下工作:

## 任务: 安装 PDF 解析工具链

### 1. 更新 pyproject.toml 添加新依赖:
```toml
# 在 dependencies 中添加:
docling = ">=2.26.0"          # IBM PDF 解析 (表格提取最佳)
pdfplumber = ">=0.11.0"       # PDF 文本/表格提取 (备选)
playwright = ">=1.49.0"       # 无头浏览器 (爬取 IACS)
markdownify = ">=0.14.0"      # HTML → Markdown
aiohttp = ">=3.11.0"          # 异步 HTTP 下载
tqdm = ">=4.67.0"             # 进度条
```

### 2. 创建 scripts/install_pdf_tools.sh:
```bash
#!/bin/bash
pip install docling pdfplumber playwright markdownify aiohttp tqdm --break-system-packages
playwright install chromium --with-deps
echo "PDF tool chain installed successfully"
```

### 3. 创建 data/ 目录结构:
```
data/
├── bv_rules/
│   ├── raw_pdfs/              # 下载的原始 PDF
│   ├── parsed_markdown/       # Docling 解析结果
│   └── chunks/                # 分块后的 JSONL
├── iacs/
│   ├── raw_pdfs/
│   ├── parsed_markdown/
│   └── chunks/
└── catalog/
    ├── bv_catalog.json        # BV 出版物索引
    └── iacs_catalog.json      # IACS 决议索引
```

### 4. 测试 Docling 安装:
创建 scripts/test_docling.py，用一个简单的测试 PDF 验证表格提取功能。

**重要**: 先 git add + commit 这些基础变更，确保环境可用后再进行数据爬取。
```

---

### 🔥 Prompt 2: BV Rules 爬虫 + PDF 下载器

```
你是一个Python爬虫工程师。在 bv-rag 项目中创建 BV Rules 数据采集管线。

## 背景
Bureau Veritas 海事法规规范出版物在 https://marine-offshore.bureauveritas.com/rules-guidelines
每个出版物有独立页面，页面上有 "Check the Consolidated PDF file" 等链接指向 PDF 下载。
PDF 链接常见模式: https://erules.veristar.com/dy/data/bv/pdf/{NR编号}...pdf

## 任务 1: 创建 crawler/bv_rules_crawler.py

使用 Scrapy 爬取 BV 出版物索引:

1. 起始页: https://marine-offshore.bureauveritas.com/rules-classification-rule-notes-and-guidance-notes
2. 从索引页提取所有出版物链接 (NR/NI 开头的页面)
3. 进入每个出版物详情页，提取:
   - title: 出版物标题 (e.g., "NR467 Rules for the classification of steel ships")
   - nr_code: NR/NI 编号 (e.g., "NR467")
   - description: 适用范围描述
   - pdf_urls: 所有 PDF 下载链接 (consolidated + amendments + main changes)
   - category: 分类 (Rules / Rule Notes / Guidance Notes)
   - edition_date: 版本日期
   - related_publications: 相关出版物列表
4. 输出到 data/catalog/bv_catalog.json

注意:
- BV 网站可能用 JavaScript 动态加载部分内容，如果 Scrapy 抓不到 PDF 链接，
  使用 Playwright 作为备选方案
- Consolidated PDF 优先 (包含所有修正)，单独 amendment PDF 不需要
- 需要处理 Veristar 登录重定向 (部分 PDF 可能需要免费注册)
- 做好请求速率限制 (每请求间隔 2-3 秒)

## 任务 2: 创建 scripts/download_bv_pdfs.py

批量下载器:
1. 读取 bv_catalog.json
2. 按优先级排序:
   - P0: NR467, NR216, NR445, NR483 (核心分类规范)
   - P1: NR217, NR526, NR544, NR580 (重要补充)
   - P2: 所有 NI 系列 (指导性文件)
3. 使用 aiohttp 异步下载，带:
   - 进度条 (tqdm)
   - 断点续传 (检查文件是否已存在)
   - 重试逻辑 (3次, exponential backoff)
   - 文件命名: {nr_code}_{edition_date}.pdf
4. 下载到 data/bv_rules/raw_pdfs/
5. 生成下载报告: 成功/失败/跳过数量

## 输出文件:
- crawler/bv_rules_crawler.py
- scripts/download_bv_pdfs.py
- 两者都应该可以独立运行

git commit 并附带清晰的 commit message。
```

---

### 🔥 Prompt 3: IACS 爬虫 + PDF 下载器

```
你是一个Python爬虫工程师。在 bv-rag 项目中创建 IACS 数据采集管线。

## 背景
IACS 网站 https://iacs.org.uk/ 发布 Unified Requirements (UR)、Unified Interpretations (UI)、
Procedural Requirements (PR) 和 Recommendations。每个决议有独立页面，提供 PDF 下载。
IACS 使用 Cloudflare 防爬保护，直接 requests 会返回 403。

## 已知网站结构 (从搜索结果验证):
- UR 总索引: https://iacs.org.uk/resolutions/unified-requirements
- UR 分类页: https://iacs.org.uk/resolutions/unified-requirements/ur-{letter}
  字母: a, c, d, e, f, g, h, i, k, l, m, n, p, s, w, z
- 单个 UR 页面: https://iacs.org.uk/resolutions/unified-requirements/ur-{letter}/ur-{letter}{number}-{desc}
  例如: ur-s/ur-s1-rev7-cln
- UI 总索引: https://iacs.org.uk/resolutions/unified-interpretations
- PR 总索引: https://iacs.org.uk/resolutions/procedural-requirements
- Rec 总索引: https://iacs.org.uk/resolutions/recommendations

## 任务 1: 创建 crawler/iacs_crawler.py

使用 Playwright (无头 Chromium) 绕过 Cloudflare:

1. 启动 Playwright Chromium 浏览器 (headless=True)
2. 按顺序爬取:
   a. UR 索引页 → 17 个类别页 → 每个类别下的所有 UR 详情页
   b. UI 索引页 → 按公约分类 → 所有 UI 详情页
   c. PR 索引页 → 所有 PR 详情页
   d. Rec 索引页 → 所有 Rec 详情页
3. 在每个详情页提取:
   - title: 完整标题 (e.g., "UR S1 Requirements for Loading Conditions...")
   - code: 编号 (e.g., "UR S1 Rev7")
   - category: UR/UI/PR/Rec
   - sub_category: 字母分类 (e.g., "S" for Strength)
   - pdf_url: "VIEW PDF" 或 "DOWNLOAD FILE" 链接
   - version: 版本信息 (Rev 号, 日期)
   - is_clean: 是否是 CLN (clean) 版
   - is_underlined: 是否是 UL (underlined) 版
   - technical_background_url: 技术背景文件链接 (如有)
4. **只保留最新 Clean 版** (带 "cln" 或 不带 "ul" 的最新 Rev)
5. 输出到 data/catalog/iacs_catalog.json

注意:
- 页面之间间隔 3-5 秒 (避免触发更严格的反爬)
- 使用 page.wait_for_selector() 确保内容加载完成
- 处理可能的 Cloudflare challenge 页面 (等待几秒后重试)
- 如果 Playwright 也被挡，考虑添加 stealth 插件

## 任务 2: 创建 scripts/download_iacs_pdfs.py

批量下载器 (结构同 BV 下载器):
1. 读取 iacs_catalog.json
2. 优先级:
   - P0: UR-F (防火), UR-L (稳性/载重线), UR-S (强度), UR-Z (检验), UR-E (电气)
   - P1: UR-M (机械), UR-W (材料焊接), UR-P (管路), UR-A (系泊), UR-N (航行)
   - P2: UI 全部, PR 全部, Rec 全部
   - P3: UR-C, UR-D, UR-G, UR-H, UR-I, UR-K (特种船/设备)
3. 使用 Playwright 下载 (因为可能需要绕过防爬)
4. 下载到 data/iacs/raw_pdfs/
5. 文件命名: {category}_{code}_{version}.pdf

## 输出文件:
- crawler/iacs_crawler.py
- scripts/download_iacs_pdfs.py

git commit 并附带清晰的 commit message。
```

---

### 🔥 Prompt 4: PDF 解析管线 (Docling + 表格增强)

```
你是一个数据工程师。在 bv-rag 项目中创建 PDF 解析管线，将下载的 BV/IACS PDF 转换为
RAG-ready 的结构化文本。

## 背景
当前系统的数据来自 imorules.com 的 HTML 页面 (parser/html_parser.py)。
新增数据来自 PDF 文件，需要专门的 PDF 解析管线。

关键挑战:
1. BV Rules PDF 有大量复杂表格 (防火分隔等级表、尺寸规格表等)
2. 法规条款有严格的层级编号 (1.2.3.4 格式)
3. 需要保留每个条款的完整层级路径 (章→节→条→款)
4. 某些 PDF 超过 2000 页，需要分批处理

## 任务 1: 创建 parser/pdf_parser.py

使用 Docling 作为主解析器:

```python
class PDFParser:
    """
    PDF 法规文档解析器
    - 使用 Docling 提取文本+表格 (97%+ 表格精度)
    - 保留法规层级结构
    - 表格转换为结构化 Markdown
    """
    
    def __init__(self):
        from docling.document_converter import DocumentConverter
        self.converter = DocumentConverter()
    
    def parse_pdf(self, pdf_path: str, source: str = "BV") -> list[dict]:
        """
        解析单个 PDF，返回结构化条款列表
        
        每个条款:
        {
            "doc_id": "BV_NR467_Pt_B_Ch1_Sec1_1.2.3",
            "title": "Section 1 - Application",
            "document": "BV NR467",
            "regulation_number": "Pt.B Ch.1 Sec.1 1.2.3",
            "breadcrumb": "NR467 > Part B Hull > Chapter 1 General > Section 1",
            "body_text": "...",
            "page_type": "regulation",
            "url": "https://marine-offshore.bureauveritas.com/nr467...",
            "source_type": "bv_rules",  # bv_rules / iacs_ur / iacs_ui
            "parent_doc_id": "BV_NR467_Pt_B_Ch1_Sec1",
            "tables": [...],  # 解析出的表格列表
            "metadata": {
                "nr_code": "NR467",
                "edition": "January 2025",
                "authority_level": "classification_rule"  # 权威层级
            }
        }
        """
    
    def _parse_tables(self, docling_result) -> list[dict]:
        """
        提取表格并转换为多种格式:
        1. Markdown 表格 (用于 LLM 上下文)
        2. 结构化 JSON (用于精确查询)
        3. 自然语言描述 (用于向量检索)
        
        关键: 防火分隔表 (如 SOLAS Table 9.3 对应的 BV 表格) 
        需要将每行每列组合展开为独立的可检索条目:
        
        例如: "Galley vs Corridor: A-0 fire integrity required"
        """
    
    def _extract_hierarchy(self, text: str, source: str) -> dict:
        """
        提取法规层级结构:
        - BV: Part > Chapter > Section > 1.2.3
        - IACS: Section > 1.2.3
        """
    
    def _generate_table_descriptions(self, table_data: dict) -> list[str]:
        """
        将表格转换为可检索的自然语言描述
        
        例如火灾分隔表:
        输入: 行="Galley", 列="Corridor", 值="A-0"
        输出: "According to BV NR467, the fire integrity requirement 
               between a galley and a corridor on a cargo ship is A-0 
               class division."
        
        这解决了你的 T101/T102 测试失败问题!
        每个表格单元格 = 一个可检索的 chunk
        """
```

## 任务 2: 创建 parser/iacs_pdf_parser.py (继承 PDFParser)

IACS PDF 格式特点:
- 通常较短 (5-30 页/份)
- 标准格式: 标题 + 适用范围 + 条款
- 版本信息在首页
- 需要提取: UR 编号, 适用日期, 关联的 IMO 公约

## 任务 3: 创建 chunker/pdf_chunker.py

PDF 内容分块策略 (兼容现有 regulation_chunker.py):

1. **法规条款分块**: 按自然条款边界分块 (1.1, 1.2, 1.3...)
2. **表格分块**: 
   - 完整表格作为一个 chunk (Markdown 格式)
   - 如果表格超过 1000 tokens，按行组拆分
   - 每行组合展开为独立 chunk (防火表/尺寸表)
3. **长段落分块**: 超过 500 tokens 的段落按句子边界拆分
4. **元数据保留**: 每个 chunk 携带完整 breadcrumb + source_type

chunk 输出格式 (与现有 chunks.jsonl 兼容):
```json
{
    "chunk_id": "BV_NR467_PtB_Ch1_Sec1_1.2.3_c0",
    "text": "...",
    "text_for_embedding": "BV NR467 Part B Chapter 1 Section 1: ...",
    "document": "BV NR467",
    "regulation_number": "Pt.B Ch.1 Sec.1 1.2.3",
    "breadcrumb": "NR467 > Part B > Chapter 1 > Section 1 > 1.2.3",
    "url": "https://marine-offshore.bureauveritas.com/nr467...",
    "title": "NR467 Pt.B Ch.1 Sec.1 - General Requirements",
    "source_type": "bv_rules",
    "authority_level": "classification_rule",
    "chunk_type": "regulation|table|table_cell"
}
```

## 任务 4: 处理脚本
创建 scripts/parse_all_pdfs.py:
- 扫描 data/bv_rules/raw_pdfs/ 和 data/iacs/raw_pdfs/
- 批量解析 → 输出到对应的 parsed_markdown/ 和 chunks/ 目录
- 进度条 + 错误处理 + 跳过已解析文件
- 最终统计: 解析了 N 个 PDF, 生成 M 个条款, K 个 chunks

git commit 并附带清晰的 commit message。
```

---

### 🔥 Prompt 5: 数据入库 (PostgreSQL + Qdrant 扩展)

```
你是一个数据工程师。将解析好的 BV/IACS 数据导入 bv-rag 的 PostgreSQL 和 Qdrant。

## 背景
当前数据库:
- PostgreSQL: regulations 表 (18,589 条) + cross_references 表
- Qdrant: imo_regulations collection (24,476 向量)

新增数据预估:
- BV Rules: ~100,000-150,000 chunks (仅 NR467 就可能有 50,000+)
- IACS: ~20,000-30,000 chunks

## 任务 1: 扩展 PostgreSQL schema

在 scripts/seed_data.py 中添加:

```sql
-- 新增: chunk_utilities 表 (MemRL 启发的 Utility-Aware Reranking)
CREATE TABLE IF NOT EXISTS chunk_utilities (
    chunk_id TEXT NOT NULL,
    query_category TEXT NOT NULL DEFAULT 'general',
    utility_score REAL NOT NULL DEFAULT 0.5,
    use_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (chunk_id, query_category)
);

CREATE INDEX idx_chunk_utilities_score ON chunk_utilities(query_category, utility_score DESC);

-- 新增: source_type 列 (区分数据来源)
ALTER TABLE regulations ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'imo_rules';
ALTER TABLE regulations ADD COLUMN IF NOT EXISTS authority_level TEXT DEFAULT 'convention';

-- authority_level 枚举:
-- 'convention' (IMO 公约, 最高)
-- 'resolution' (IMO 决议)
-- 'iacs_ur' (IACS 统一要求)
-- 'iacs_ui' (IACS 统一解释)
-- 'classification_rule' (BV 船级社规范)
-- 'guidance_note' (指导性文件, 最低)
```

## 任务 2: 创建 pipeline/ingest_external.py

新增数据入库管线 (不影响现有 ingest.py):

```python
class ExternalDataIngestor:
    """
    BV Rules + IACS 数据入库管线
    
    与现有 ingest.py 的区别:
    1. 数据来源是 PDF 解析结果 (JSONL)，不是爬虫原始 HTML
    2. 支持增量入库 (跳过已存在的 doc_id)
    3. 使用 multi-collection 策略:
       - imo_regulations (现有, 不变)
       - bv_rules (新建)
       - iacs_resolutions (新建)
    4. 批量 embedding 生成 (每批 100 条，避免 API 限流)
    """
    
    def ingest_bv_rules(self, chunks_dir: str):
        """入库 BV Rules chunks"""
        # 1. 读取 chunks JSONL
        # 2. 写入 PostgreSQL regulations 表 (source_type='bv_rules')
        # 3. 批量生成 embeddings
        # 4. 写入 Qdrant bv_rules collection
        # 5. 提取交叉引用写入 cross_references 表
        # 6. 初始化 chunk_utilities 表 (utility=0.5)
    
    def ingest_iacs(self, chunks_dir: str):
        """入库 IACS chunks"""
        # 同上，写入 iacs_resolutions collection
```

## 任务 3: Qdrant 多 Collection 创建

在 retrieval/vector_store.py 中扩展:

```python
COLLECTIONS = {
    "imo_regulations": {
        "description": "IMO conventions and codes (SOLAS, MARPOL, etc.)",
        "authority_level": 1.0  # 最高权重
    },
    "bv_rules": {
        "description": "Bureau Veritas classification rules and guidance",
        "authority_level": 0.7
    },
    "iacs_resolutions": {
        "description": "IACS unified requirements and interpretations",
        "authority_level": 0.85
    }
}

def create_collections(self):
    """创建所有 collections (如果不存在)"""
    for name, config in COLLECTIONS.items():
        if not self.client.collection_exists(name):
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=1024,
                    distance=Distance.COSINE
                ),
                quantization_config=ScalarQuantization(
                    scalar=ScalarQuantizationConfig(type=ScalarType.INT8)
                )
            )

def search_all_collections(self, query_vector, top_k, document_filter=None):
    """跨 collection 搜索，按权威层级加权"""
    all_results = []
    for name, config in COLLECTIONS.items():
        results = self.client.query_points(
            collection_name=name,
            query=query_vector,
            limit=top_k,
            query_filter=...,
        )
        for r in results:
            r.score *= config["authority_level"]  # 权威层级加权
        all_results.extend(results)
    
    all_results.sort(key=lambda x: x.score, reverse=True)
    return all_results[:top_k]
```

## 任务 4: 入库执行脚本

创建 scripts/run_external_ingest.py:
1. 检查 Qdrant/PostgreSQL 连接
2. 创建新 collections
3. 运行 BV Rules 入库
4. 运行 IACS 入库
5. 输出统计: 各 collection 向量数、PG 记录数

**注意**: embedding 生成需要 OpenAI API 调用，成本估算:
- 200,000 chunks × ~200 tokens/chunk = 40M tokens
- text-embedding-3-large 价格 $0.13/1M tokens
- 预估成本: ~$5.2

git commit 并附带清晰的 commit message。
```

---

### 🔥 Prompt 6: Utility-Aware Reranking (MemRL 核心适配)

```
你是一个高级ML工程师。在 bv-rag 项目中实现 Utility-Aware Reranking，
灵感来自 MemRL (arxiv 2601.03192) 的 Two-Phase Retrieval 机制。

## 背景
MemRL 论文提出将检索分为两个阶段:
- Phase A: 语义相似度粗召回 (k₁ 个候选)
- Phase B: 基于 learned Q-value (utility) 精选 (k₂ 个最终结果)

在我们的法规 RAG 场景中:
- Phase A = 现有的 Vector + BM25 + Graph → RRF 融合
- Phase B = 新增的 Utility-Aware Reranking
- Q-value = chunk 的历史使用效用评分

## 核心思路
每次用户提问后，根据回答质量反馈，更新被检索 chunk 的 utility score。
高 utility 的 chunk 在未来检索中会被优先选中。

## 任务 1: 创建 retrieval/utility_reranker.py

```python
class UtilityReranker:
    """
    MemRL-inspired Utility-Aware Reranker for maritime regulation RAG.
    
    核心机制:
    1. 接收 RRF 融合后的 top_k₁ 结果 (Phase A output)
    2. 查询每个 chunk 的 utility score
    3. 计算综合分数: final_score = α * rrf_score + (1-α) * utility_score
    4. 返回 top_k₂ 精选结果
    
    Utility 更新 (EMA):
    - 回答后根据 confidence + citation 匹配更新
    - utility = (1-α) * old_utility + α * reward
    - α = 0.1 (学习率，保持稳定性)
    """
    
    def __init__(self, pg_conn, alpha=0.3, learning_rate=0.1):
        """
        alpha: RRF 与 utility 的混合权重 (0.3 = 70% RRF + 30% utility)
               初期 utility 数据稀少时 alpha 应小，随数据积累逐渐增大
        learning_rate: EMA 更新速率
        """
        self.pg_conn = pg_conn
        self.alpha = alpha
        self.lr = learning_rate
    
    def rerank(self, chunks: list[dict], query_category: str = "general") -> list[dict]:
        """
        Phase B: Utility-Aware Selection
        
        Args:
            chunks: RRF 融合后的 top_k₁ 候选 (每个有 rrf_score)
            query_category: 查询分类 (fire_safety, pollution, lifesaving, etc.)
        
        Returns:
            重排后的 chunks (按 final_score 降序)
        """
        chunk_ids = [c.get("chunk_id", c.get("doc_id", "")) for c in chunks]
        
        # 批量查询 utility scores
        utilities = self._batch_get_utilities(chunk_ids, query_category)
        
        for chunk in chunks:
            cid = chunk.get("chunk_id", chunk.get("doc_id", ""))
            u = utilities.get(cid, 0.5)  # 默认 0.5 (中性)
            rrf = chunk.get("rrf_score", chunk.get("score", 0.0))
            
            # 归一化 RRF score 到 [0, 1]
            rrf_norm = min(rrf / 0.1, 1.0)  # RRF 分数通常在 0-0.1 范围
            
            # 综合分数
            chunk["utility_score"] = u
            chunk["final_score"] = (1 - self.alpha) * rrf_norm + self.alpha * u
        
        chunks.sort(key=lambda x: x["final_score"], reverse=True)
        return chunks
    
    def update_utilities(self, 
                         retrieved_chunks: list[dict],
                         cited_chunk_ids: set[str],
                         confidence: str,
                         query_category: str = "general"):
        """
        回答后更新 utility scores (MemRL 的 Runtime Learning)
        
        更新规则:
        - 被引用且 confidence=high: reward = +1.0
        - 被引用且 confidence=medium: reward = +0.5
        - 被检索但未引用且 confidence=high: reward = -0.1 (轻微惩罚)
        - 被检索但未引用且 confidence=low: reward = -0.3
        - confidence=low 且答案含"无法回答": 所有被检索 chunk reward = -0.5
        """
        for chunk in retrieved_chunks:
            cid = chunk.get("chunk_id", chunk.get("doc_id", ""))
            is_cited = cid in cited_chunk_ids
            
            if confidence == "high":
                reward = 1.0 if is_cited else -0.1
            elif confidence == "medium":
                reward = 0.5 if is_cited else 0.0
            else:  # low
                reward = 0.0 if is_cited else -0.3
            
            self._update_utility(cid, query_category, reward)
    
    def _update_utility(self, chunk_id: str, category: str, reward: float):
        """EMA 更新: utility = (1-lr) * old + lr * reward"""
        # UPSERT with EMA update
        sql = """
        INSERT INTO chunk_utilities (chunk_id, query_category, utility_score, use_count, success_count, last_used)
        VALUES (%s, %s, %s, 1, %s, NOW())
        ON CONFLICT (chunk_id, query_category)
        DO UPDATE SET
            utility_score = (1 - %s) * chunk_utilities.utility_score + %s * %s,
            use_count = chunk_utilities.use_count + 1,
            success_count = chunk_utilities.success_count + %s,
            last_used = NOW()
        """
        success = 1 if reward > 0 else 0
        initial_utility = 0.5 + reward * self.lr  # 初始值基于首次 reward
        self.pg_conn.execute(sql, (
            chunk_id, category, initial_utility, success,
            self.lr, self.lr, reward, success
        ))
    
    def _batch_get_utilities(self, chunk_ids: list[str], category: str) -> dict:
        """批量获取 utility scores"""
        if not chunk_ids:
            return {}
        placeholders = ",".join(["%s"] * len(chunk_ids))
        sql = f"""
        SELECT chunk_id, utility_score 
        FROM chunk_utilities 
        WHERE chunk_id IN ({placeholders}) AND query_category = %s
        """
        results = self.pg_conn.fetchall(sql, (*chunk_ids, category))
        return {r[0]: r[1] for r in results}
    
    def get_stats(self) -> dict:
        """获取 utility 统计信息"""
        sql = """
        SELECT query_category, 
               COUNT(*) as total_chunks,
               AVG(utility_score) as avg_utility,
               AVG(use_count) as avg_uses,
               COUNT(CASE WHEN utility_score > 0.7 THEN 1 END) as high_utility,
               COUNT(CASE WHEN utility_score < 0.3 THEN 1 END) as low_utility
        FROM chunk_utilities
        GROUP BY query_category
        """
        return self.pg_conn.fetchall(sql)
```

## 任务 2: 集成到 HybridRetriever

修改 retrieval/hybrid_retriever.py:

```python
# 在 retrieve() 方法中，RRF 融合之后，Graph Expansion 之前:

# Phase A: 现有的 RRF 融合 (已有)
rrf_results = self._rrf_fusion(vector_results, bm25_results, graph_results)

# Phase B: Utility-Aware Reranking (新增)
if self.utility_reranker:
    query_category = self._classify_query_category(enhanced_query)
    rrf_results = self.utility_reranker.rerank(rrf_results, query_category)

# Graph Expansion (已有)
expanded = self._graph_expand(rrf_results[:5], enhanced_query)
```

新增 `_classify_query_category()` 方法:
```python
def _classify_query_category(self, query: str) -> str:
    """将查询分类为法规领域，用于 utility 分桶"""
    categories = {
        "fire_safety": ["防火", "fire", "A-0", "A-60", "B-15", "防火分隔"],
        "lifesaving": ["救生", "liferaft", "davit", "lifeboat"],
        "pollution": ["排放", "MARPOL", "排油", "ODME", "OWS", "污水"],
        "stability": ["稳性", "stability", "freeboard", "载重线"],
        "structure": ["结构", "强度", "strength", "scantling"],
        "machinery": ["机械", "machinery", "engine", "boiler"],
        "navigation": ["航行", "navigation", "ECDIS", "AIS"],
        "survey": ["检验", "survey", "PSC", "certificate"]
    }
    for cat, keywords in categories.items():
        if any(kw in query.lower() for kw in keywords):
            return cat
    return "general"
```

## 任务 3: 在 Pipeline 中注入 Utility 更新钩子

修改 pipeline/voice_qa_pipeline.py 的 _process_query():

在步骤 9 (保存 turn) 之后添加:
```python
# Step 9.5: Update chunk utilities (MemRL runtime learning)
if hasattr(self, 'utility_reranker') and self.utility_reranker:
    cited_ids = set()
    for citation in result.get("citations", []):
        # 从 citation 中提取 chunk_id
        for source in result.get("sources", []):
            if citation.get("citation", "") in source.get("breadcrumb", ""):
                cited_ids.add(source.get("chunk_id", ""))
    
    self.utility_reranker.update_utilities(
        retrieved_chunks=result.get("sources", []),
        cited_chunk_ids=cited_ids,
        confidence=result.get("confidence", "low"),
        query_category=self._get_query_category(enhanced_query)
    )
```

## 任务 4: Admin 端点展示 Utility 统计

在 api/routes/admin.py 添加:
```python
@router.get("/api/v1/admin/utility-stats")
async def utility_stats(request: Request):
    """展示 chunk utility 学习统计"""
    stats = request.app.state.utility_reranker.get_stats()
    return {"utility_stats": stats}
```

git commit 并附带清晰的 commit message。
```

---

### 🔥 Prompt 7: QueryEnhancer BV/IACS 术语扩展 + 跨源检索

```
你是一个NLP工程师。扩展 bv-rag 的 QueryEnhancer 以支持 BV Rules 和 IACS 术语。

## 任务 1: 扩展 TERMINOLOGY_MAP (retrieval/query_enhancer.py)

新增 BV Rules 相关术语映射:

```python
# BV Rules 特有术语
"入级": ["classification", "class", "NR467"],
"船级社": ["classification society", "Bureau Veritas", "BV"],
"入级检验": ["classification survey", "initial survey", "renewal survey"],
"附加标志": ["additional class notation", "notation", "class notation"],
"结构强度": ["structural strength", "scantling", "hull girder"],
"腐蚀余量": ["corrosion addition", "corrosion allowance", "wastage"],
"疲劳强度": ["fatigue strength", "fatigue assessment", "fatigue life"],
"有限元分析": ["finite element analysis", "FEA", "direct calculation"],
"许用应力": ["allowable stress", "permissible stress"],
"最小板厚": ["minimum thickness", "minimum plate thickness"],

# IACS 特有术语  
"统一要求": ["unified requirement", "UR", "IACS UR"],
"统一解释": ["unified interpretation", "UI", "IACS UI"],
"共同结构规范": ["common structural rules", "CSR", "CSR BC&OT"],
"极地船舶": ["polar class", "polar ship", "ice class"],
"网络安全": ["cyber resilience", "UR E26", "UR E27", "cybersecurity"],
```

## 任务 2: 扩展 TOPIC_TO_REGULATIONS

新增 BV/IACS 法规关联:

```python
# BV Rules
"classification": ["BV NR467", "IACS UR Z"],
"structural strength": ["BV NR467 Pt.B", "IACS UR S", "CSR"],
"materials welding": ["BV NR216", "IACS UR W"],
"corrosion": ["BV NR467 Pt.B", "IACS UR S"],
"fatigue": ["BV NR467 Pt.B Ch.7", "IACS UR S"],

# IACS UR → IMO 公约关联
"mooring anchoring": ["IACS UR A", "SOLAS II-1"],
"fire protection iacs": ["IACS UR F", "SOLAS II-2"],
"stability loadline": ["IACS UR L", "ILLC", "SOLAS II-1"],
"machinery": ["IACS UR M", "SOLAS II-1"],
"survey certification": ["IACS UR Z", "SOLAS XI"],
```

## 任务 3: 跨数据源检索路由

在 retrieval/hybrid_retriever.py 的 retrieve() 方法中:

```python
def _determine_search_collections(self, enhanced_query: str, classification: dict) -> list[str]:
    """
    根据查询内容决定搜索哪些 collections
    
    默认: 搜索所有 collections
    优化: 如果查询明确指向特定数据源，只搜索相关 collection
    """
    collections = ["imo_regulations"]  # 始终搜索 IMO
    
    query_lower = enhanced_query.lower()
    
    # BV 相关查询
    if any(kw in query_lower for kw in ["bv", "bureau veritas", "nr467", "nr216", "入级", "附加标志"]):
        collections.append("bv_rules")
    
    # IACS 相关查询
    if any(kw in query_lower for kw in ["iacs", "ur ", "统一要求", "统一解释", "csr", "共同结构"]):
        collections.append("iacs_resolutions")
    
    # 通用技术查询 → 搜索所有
    if not any(c in collections for c in ["bv_rules", "iacs_resolutions"]):
        collections.extend(["bv_rules", "iacs_resolutions"])
    
    return collections
```

git commit 并附带清晰的 commit message。
```

---

### 🔥 Prompt 8: 测试 + 回归验证

```
你是一个QA工程师。为 bv-rag 的新数据源和 Utility Reranking 添加测试。

## 任务 1: 扩展 tests/regression_test.py

新增测试用例:

```python
# BV Rules 测试
{
    "id": "T009",
    "query": "BV NR467对于散货船货舱区域的最小板厚要求是多少？",
    "expect_contains": ["plate thickness", "mm"],
    "expect_contains_any": [["NR467", "BV"]],
    "expect_not_contains": ["无法回答"],
    "description": "BV Rules 检索验证"
},
{
    "id": "T010", 
    "query": "IACS UR Z7.1 对年度检验的要求是什么？",
    "expect_contains": ["annual survey"],
    "expect_contains_any": [["UR Z", "IACS"]],
    "expect_not_contains": ["无法回答"],
    "description": "IACS UR 检索验证"
},
{
    "id": "T011",
    "query": "BV的入级规范和SOLAS对船体结构的要求有什么区别？",
    "expect_contains_any": [["NR467", "BV"], ["SOLAS"]],
    "expect_model": "claude-sonnet-4-20250514",
    "description": "跨数据源比较查询"
},

# 重新运行原有 T101-T105 (验船师五题)
# 期望 T101/T102 在新数据入库后改善 (BV 防火表 + SOLAS 表)
```

## 任务 2: Utility Reranking 单元测试

创建 tests/test_utility_reranker.py:

```python
def test_rerank_with_no_utilities():
    """冷启动: 所有 chunk utility=0.5，排序应等同于 RRF"""

def test_rerank_high_utility_promoted():
    """高 utility chunk 应该被提升排名"""

def test_utility_update_positive():
    """confidence=high + cited → utility 应上升"""

def test_utility_update_negative():
    """confidence=low + not cited → utility 应下降"""

def test_utility_convergence():
    """多次更新后 utility 应收敛 (EMA 特性)"""
```

## 任务 3: 运行完整验证

```bash
# 1. 先跑单元测试
python -m pytest tests/test_utility_reranker.py -v

# 2. 跑回归测试 (12 个用例)
python tests/regression_test.py https://bv-rag-production.up.railway.app

# 3. 跑验船师五题
python tests/regression_test.py https://bv-rag-production.up.railway.app --senior-only
```

git commit 并附带清晰的 commit message。
```

---

## 第五部分: 执行顺序 + 风险控制

### 执行顺序

```
Week 1:
  Day 1-2: Prompt 1 (环境) → Prompt 2 (BV 爬虫)
  Day 3-4: Prompt 3 (IACS 爬虫) → 下载所有 PDF
  Day 5:   Prompt 4 (PDF 解析) → 处理所有 PDF

Week 2:
  Day 1-2: Prompt 5 (入库) → 生成 embeddings + 写入 DB
  Day 3:   Prompt 6 (Utility Reranking) → 核心检索升级
  Day 4:   Prompt 7 (术语扩展) → QueryEnhancer 更新
  Day 5:   Prompt 8 (测试) → 全面验证

Week 3:
  Day 1-2: 修复测试发现的问题
  Day 3:   部署到 Railway
  Day 4-5: P0-P3 修复方案执行 (之前未跑的诊断+修复)
```

### 风险控制

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| BV PDF 需要登录 | 中 | 高 | 手动注册免费账号，或先用 eRules HTML |
| IACS Cloudflare 拦截 | 高 | 中 | Playwright + stealth plugin，或手动下载 |
| PDF 表格解析失败 | 中 | 高 | Docling → LlamaParse → 手动 fallback |
| Qdrant 免费版容量不足 | 高 | 高 | 200k+ vectors 超出 free tier，需升级或自建 |
| Embedding 成本超预算 | 低 | 中 | 分批处理，先 P0 核心数据 |
| Utility Reranking 冷启动 | 确定 | 低 | alpha=0.3 (RRF 占主导)，随使用逐渐生效 |

### Qdrant 容量规划

| Collection | 预估向量数 | 内存需求 (INT8) | 说明 |
|-----------|-----------|---------------|------|
| imo_regulations | 24,476 | ~50 MB | 现有 |
| bv_rules | ~120,000 | ~250 MB | NR467 最大 |
| iacs_resolutions | ~25,000 | ~50 MB | UR+UI+PR |
| **合计** | **~170,000** | **~350 MB** | 需 Qdrant 付费版或自建 |

**Qdrant 免费版限制**: 1GB RAM，可能需要升级到 Starter ($25/月) 或在 Railway 自建 Qdrant。

### 成本估算

| 项目 | 数量 | 单价 | 总价 |
|------|------|------|------|
| OpenAI Embedding | ~40M tokens | $0.13/M | ~$5.2 |
| Qdrant Starter (可选) | 1个月 | $25/月 | $25 |
| Railway 额外存储 | 10GB | 含在 Pro 计划 | $0 |
| **合计** | | | **$5-30** |

---

## 第六部分: MemRL 适用性深度分析

### 为什么 MemRL 的思路对 BV-RAG 特别有价值

**问题回顾**: 在诊断测试中，T101 (厨房-走廊防火等级) 检索到了 MODU Code (钻井平台) 
而不是 SOLAS II-2/9。两者的向量距离可能很接近 (都包含 "fire division" 等术语)，
但 MODU Code 对货船问题完全无用。

**MemRL 视角**:
- Phase A (语义召回): MODU Code 和 SOLAS II-2/9 都能被召回 (语义相似)
- Phase B (utility 重排): 随着使用，SOLAS II-2/9 在 fire_safety 分类下 utility 会升高，
  MODU Code 因为被检索但不被引用而 utility 下降
- **最终效果**: 同样的查询，系统会学会优先返回 SOLAS II-2/9 而非 MODU Code

**与 P3 (MODU Code Demotion) 的关系**:
- P3 是规则硬编码 (看到"货船"就降权 MODU Code)
- MemRL utility 是数据驱动 (从使用效果中自动学习)
- **两者互补**: P3 提供冷启动时的合理默认值，utility 在运行中持续优化

### 简化设计 vs 完整 MemRL

| MemRL 原始设计 | BV-RAG 简化版 | 理由 |
|---------------|-------------|------|
| Intent embedding | query_category 字符串 | 法规领域有限，不需要连续空间 |
| Experience (完整trajectory) | chunk text | RAG 无需存储行动序列 |
| Q-value (Bellman backup) | EMA 平滑 utility | 法规问答无多步决策 |
| Phase A: k₁=20 | k₁=top_k*2 (已有) | RRF 自带过采样 |
| Phase B: Q-value weighted | α-混合重排 | 更稳定，避免 utility 噪声主导 |
| γ (折扣因子) | 不需要 | 无时序依赖 |

**核心保留**: Two-Phase Retrieval + Runtime Learning 的思想
**核心简化**: 去掉 RL 的 MDP 框架，用简单的 EMA 统计替代

---

*文档版本: v1.0*
*创建时间: 2026-02-17*
*适用项目: BV-RAG Maritime Regulation Voice Q&A System*
