# BV-RAG 技术文档

> Maritime Regulation Voice Q&A System — 海事法规语音问答系统

**版本**: 1.0.0
**部署环境**: Railway Pro
**线上地址**: https://bv-rag-production.up.railway.app

---

## 目录

1. [系统概览](#1-系统概览)
2. [技术栈](#2-技术栈)
3. [系统架构](#3-系统架构)
4. [数据管线 (Data Pipeline)](#4-数据管线)
5. [检索系统 (Retrieval)](#5-检索系统)
6. [生成系统 (Generation)](#6-生成系统)
7. [对话记忆系统 (Memory)](#7-对话记忆系统)
8. [语音系统 (Voice)](#8-语音系统)
9. [知识库系统 (Knowledge)](#9-知识库系统)
10. [API 层](#10-api-层)
11. [前端](#11-前端)
12. [部署与运维](#12-部署与运维)
13. [回归测试](#13-回归测试)
14. [数据统计](#14-数据统计)

---

## 1. 系统概览

BV-RAG 是一个面向船舶验船师的海事法规智能问答系统，支持语音和文字双模式输入。系统采用 RAG (Retrieval-Augmented Generation) 架构，将 IMO 海事法规（SOLAS, MARPOL, STCW, COLREG 等）与大语言模型结合，为验船师提供准确、实用的法规解读。

### 核心特性

- **三路混合检索**: 向量语义搜索 + PostgreSQL BM25 全文搜索 + 图谱交叉引用
- **RRF 融合排序**: Reciprocal Rank Fusion 将三路结果统一排序
- **智能模型路由**: 简单查询用 Haiku (快速/低成本)，复杂查询用 Sonnet (深度推理)
- **三层指代消解**: 正则检测 → 上下文前缀注入 → LLM 兜底
- **验船实务知识库**: YAML 格式的资深验船师经验，注入 LLM 上下文
- **中英双语术语映射**: 中文口语化查询自动映射为 IMO 英文术语
- **语音交互**: STT (语音识别) + TTS (语音合成)，支持 WebSocket 实时通信

### 端到端请求流程

```
用户输入 (语音/文字)
    │
    ├── [语音模式] STT 转写 (gpt-4o-mini-transcribe)
    │
    ▼
会话记忆加载 (Redis)
    │
    ├── 指代消解 (3层策略)
    │
    ▼
查询分类 (QueryClassifier)
    │
    ├── intent: applicability / specification / comparison / ...
    ├── ship_info: {type, length, tonnage}
    ├── top_k: 5~12
    │
    ▼
查询增强 (QueryEnhancer)
    │
    ├── 中文→英文术语映射
    ├── 话题→法规章节映射
    ├── 船型/船长阈值规则
    │
    ▼
三路混合检索 (HybridRetriever)
    │
    ├── Vector: Qdrant Cloud (text-embedding-3-large, 1024维)
    ├── BM25: PostgreSQL tsvector (plainto_tsquery)
    ├── Graph: cross_references 交叉引用
    │
    ├── RRF 融合 → top_k 结果
    ├── Graph Expansion: 跟踪交叉引用发现关联法规
    │
    ▼
验船实务知识匹配 (PracticalKnowledgeBase)
    │
    ├── 关键词 + 法规编号 + 船型匹配
    ├── 返回 top 3 实务条目
    │
    ▼
答案生成 (AnswerGenerator)
    │
    ├── 模型选择: Haiku / Sonnet (基于分类 + 兜底路由)
    ├── System Prompt: 资深验船师人设 + 决策树格式
    ├── Context: 法规检索结果 + 验船实务 + 船舶信息
    │
    ▼
会话保存 (Redis)
    │
    ├── 保存 user/assistant turn
    ├── 跟踪 active_regulations, active_topics, ship_type
    │
    ▼
响应返回
    ├── answer_text (Markdown 格式)
    ├── citations (法规引用列表)
    ├── confidence (high/medium/low)
    ├── model_used
    ├── timing (各阶段耗时)
    └── [按需] TTS 音频 (base64)
```

---

## 2. 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| Web 框架 | FastAPI 0.115+ | 异步 ASGI，支持 WebSocket |
| LLM | Claude Sonnet 4 / Haiku 4.5 | Anthropic API，双模型路由 |
| Embedding | text-embedding-3-large | OpenAI，1024 维度 |
| 向量数据库 | Qdrant Cloud (free tier) | 24,476 向量点，INT8 量化 |
| 关系数据库 | PostgreSQL (Railway) | BM25 全文搜索 + 图查询 + 法规存储 |
| 缓存/会话 | Redis (Railway) | 会话记忆，24h TTL |
| STT | gpt-4o-mini-transcribe | OpenAI，回退 whisper-1 |
| TTS | gpt-4o-mini-tts | OpenAI，voice="ash" |
| 前端 | 单页 HTML (Vanilla JS) | 无框架，静态文件 |
| 爬虫 | Scrapy 2.12 | 爬取 imorules.com |
| 解析 | BeautifulSoup4 + lxml | HTML 结构化解析 |
| 部署 | Railway Pro + Docker | Dockerfile + railway.toml |
| Python | 3.11+ (Docker 用 3.12-slim) | |

### 关键依赖版本

```toml
fastapi>=0.115
anthropic>=0.42
openai>=1.60
qdrant-client>=1.12
psycopg2-binary>=2.9
redis>=5.2
scrapy>=2.12
beautifulsoup4>=4.12
tiktoken>=0.8
pydantic-settings>=2.7
```

---

## 3. 系统架构

### 目录结构

```
bv-rag/
├── api/                    # FastAPI 应用层
│   ├── main.py             # 应用入口，lifespan 初始化所有服务
│   └── routes/
│       ├── voice.py        # 语音/文字查询 + WebSocket + TTS
│       ├── search.py       # 独立搜索接口
│       └── admin.py        # 统计 + 调试端点
├── config/
│   └── settings.py         # Pydantic BaseSettings，环境变量配置
├── crawler/                # Scrapy 爬虫
│   └── run_crawler.py      # imorules.com 法规页面爬取
├── parser/
│   └── html_parser.py      # HTML → 结构化 regulation JSONL
├── chunker/
│   └── regulation_chunker.py # 法规文本分块
├── db/
│   ├── bm25_search.py      # PostgreSQL tsvector 全文搜索
│   ├── graph_queries.py    # 递归 CTE 图查询
│   └── postgres.py         # schema 初始化 + 统计
├── retrieval/
│   ├── hybrid_retriever.py # 三路检索 + RRF 融合 + 图扩展
│   ├── vector_store.py     # Qdrant Cloud 向量搜索
│   ├── query_enhancer.py   # 中英术语映射 + 法规章节注入
│   ├── query_classifier.py # 查询意图分类 + 船舶信息提取
│   └── query_router.py     # 检索策略路由 (keyword/semantic/hybrid)
├── generation/
│   ├── generator.py        # Claude 答案生成 + 模型路由
│   └── prompts.py          # System prompt + 辅助 prompt
├── memory/
│   └── conversation_memory.py # Redis 会话管理 + 指代消解
├── knowledge/
│   ├── practical_knowledge.py # 实务知识库加载/查询/格式化
│   └── practical/           # YAML 知识条目
│       ├── lifesaving.yaml
│       ├── fire_safety.yaml
│       ├── stability.yaml
│       ├── marpol.yaml
│       ├── navigation.yaml
│       └── survey_practice.yaml
├── voice/
│   ├── stt_service.py      # 语音识别服务
│   └── tts_service.py      # 语音合成服务
├── pipeline/
│   ├── voice_qa_pipeline.py # 端到端管线编排
│   └── ingest.py           # 数据入库管线
├── scripts/
│   └── seed_data.py        # PostgreSQL schema 初始化
├── tests/
│   └── regression_test.py  # 8 个回归测试用例
├── static/
│   └── index.html          # 前端单页应用
├── data/                   # 管线中间产物
│   ├── raw/pages.jsonl
│   ├── parsed/regulations.jsonl
│   └── chunks/chunks.jsonl
├── Dockerfile
├── railway.toml
└── pyproject.toml
```

### 服务初始化 (`api/main.py`)

应用启动时通过 FastAPI lifespan 机制一次性初始化所有服务实例，挂载到 `app.state`：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.stt = STTService(...)          # 语音识别
    app.state.tts = TTSService(...)          # 语音合成
    app.state.memory = ConversationMemory(...)  # Redis 会话
    app.state.vector_store = VectorStore(...)   # Qdrant
    app.state.bm25 = BM25Search(...)         # PG 全文搜索
    app.state.graph = GraphQueries(...)      # PG 图查询
    app.state.retriever = HybridRetriever(...)  # 混合检索器
    app.state.generator = AnswerGenerator(...)  # LLM 生成
    app.state.pipeline = VoiceQAPipeline(...)   # 端到端管线
    yield
    app.state.bm25.close()
    app.state.graph.close()
```

---

## 4. 数据管线

### 4.1 爬虫 (`crawler/run_crawler.py`)

使用 Scrapy 从 imorules.com 爬取 IMO 海事法规页面。

- **输入**: imorules.com 法规索引页
- **输出**: `data/raw/pages.jsonl`
- **包含字段**: url, title, html_content, breadcrumb, page_type, parent_url

### 4.2 解析 (`parser/html_parser.py`)

将原始 HTML 页面解析为结构化法规记录。

- **输入**: `data/raw/pages.jsonl`
- **输出**: `data/parsed/regulations.jsonl`
- **包含字段**: doc_id, title, document, regulation, breadcrumb, body_text, page_type, url, parent_doc_id
- **解析逻辑**:
  - BeautifulSoup4 提取正文内容
  - 去除导航、页脚等噪声元素
  - 保留法规层级关系 (parent_doc_id)
  - 提取交叉引用链接

### 4.3 分块 (`chunker/regulation_chunker.py`)

将法规文本按语义边界分块，用于向量化存储。

- **输入**: `data/parsed/regulations.jsonl`
- **输出**: `data/chunks/chunks.jsonl`
- **分块策略**:
  - 按法规条款自然段分块
  - tiktoken 计算 token 数控制大小
  - 保留元数据: document, regulation_number, breadcrumb, url

### 4.4 数据入库 (`pipeline/ingest.py`)

将解析后的法规和分块数据写入 PostgreSQL 和 Qdrant。

**PostgreSQL 写入**:
- `regulations` 表: 完整法规记录 + tsvector 搜索向量
- `cross_references` 表: 法规间交叉引用关系
- `concepts` + `regulation_concepts` 表: 概念实体关联

**Qdrant 写入**:
- Collection: `imo_regulations`
- 向量维度: 1024 (text-embedding-3-large, dimensions=1024)
- 距离函数: Cosine
- 量化: INT8 scalar quantization
- 每个点的 payload: chunk_id, text, document, regulation_number, breadcrumb, url, title

### 4.5 执行命令

```bash
# Step 1: 爬取
python -m crawler.run_crawler

# Step 2: 解析
python -m parser.html_parser

# Step 3: 分块
python -m chunker.regulation_chunker

# Step 4: 初始化 PG schema
python -m scripts.seed_data

# Step 5: 入库 (PG + Qdrant)
python -m pipeline.ingest
```

---

## 5. 检索系统

检索系统是 BV-RAG 的核心，采用多层架构实现精准法规定位。

### 5.1 查询增强 (`retrieval/query_enhancer.py`)

**目的**: 弥合中文口语化查询与英文 IMO 法规文本之间的语义鸿沟。

**五步增强流程**:

```
输入: "100米货船两边救生筏都需要起降落设备吗"
    │
    ├── Step 1: 术语映射 (TERMINOLOGY_MAP, 57个映射)
    │   "救生筏" → [liferaft, life-raft, inflatable liferaft]
    │   "起降落" → [launching appliance, davit, launching device]
    │
    ├── Step 2: 话题→法规映射 (TOPIC_TO_REGULATIONS)
    │   liferaft → [SOLAS III, LSA Code]
    │   davit → [SOLAS III, LSA Code Chapter 6]
    │
    ├── Step 3: 船型→法规映射
    │   "货船" + LSA keywords → SOLAS III/31, SOLAS III/16
    │
    ├── Step 4: 船长阈值规则
    │   100m ≥ 85m → SOLAS III/31, davit-launched liferaft, 85 metres
    │
    ├── Step 5: 双侧/两舷检测
    │   "两边" + LSA → throw-overboard, davit-launched, each side, SOLAS III/31.1.4
    │
    ▼
输出: "100米货船两边救生筏都需要起降落设备吗 | 85 metres davit davit-launched liferaft
       each side free-fall lifeboat ... | LSA Code Chapter 6 SOLAS III SOLAS III/16
       SOLAS III/31 SOLAS III/31.1.3 SOLAS III/31.1.4"
```

**关键数据结构**:

- `TERMINOLOGY_MAP`: 57 个中文→英文术语映射组，覆盖救生设备、消防、结构、船型、导航等类别
- `TOPIC_TO_REGULATIONS`: 15 个英文关键词→法规章节映射
- `_LSA_KEYWORDS`: 救生设备相关关键词列表
- `_BILATERAL_KW`: 双侧/两舷相关关键词列表
- `_LENGTH_RE`: 船长提取正则 `(\d+)\s*[米m]`

### 5.2 查询分类 (`retrieval/query_classifier.py`)

**目的**: 识别查询意图，动态调整检索深度和模型选择。

**五种意图类型**:

| 意图 | 触发词 (中/英) | 策略 | 模型 | top_k |
|------|---------------|------|------|-------|
| `applicability` | 是否需要, 必须, do I need, must | broad | primary (Sonnet) | 12 |
| `specification` | 最小, 最大, 尺寸, minimum, size | precise | fast (Haiku) | 5 |
| `procedure` | 怎么, 如何, 步骤, how to, procedure | normal | primary | 8 |
| `comparison` | 区别, 不同, 比较, difference, versus | broad | primary | 10 |
| `definition` | 什么是, 定义, what is, meaning of | precise | fast | 5 |

**船舶信息提取**:
- 船型: `_TYPE_MAP` (12 个中/英船型映射)
- 船长: `(\d+)\s*(米|m|metres)` 正则提取
- 吨位: `(\d+)\s*(吨|GT|总吨|gross tonnage)` 正则提取
- 特殊规则: "国际航行" 无明确船型 → 默认 cargo ship

**强制 applicability 覆盖**:
当查询同时包含 (船长 OR 吨位) + 需求关键词时，强制将意图设为 `applicability`，避免被错分为其他类别。

### 5.3 查询路由 (`retrieval/query_router.py`)

**目的**: 决定使用哪种检索策略组合。

**路由逻辑**:
- 匹配到精确法规引用 (如 "SOLAS Regulation II-1/3-6") → `keyword` 策略
- 包含关系词 ("哪些", "所有", "相关") → `hybrid` 策略 (覆盖 keyword)
- 默认 → `hybrid` 策略

**实体提取**:
- `document_filter`: 从 12 个公约 + 20 个规则中匹配
- `concept`: 从 23 个概念中匹配 (fire safety, bulk carrier 等)
- `regulation_ref`: 精确法规编号正则提取

### 5.4 混合检索器 (`retrieval/hybrid_retriever.py`)

这是检索系统的核心编排器，组合三路检索并用 RRF 融合排序。

#### 三路检索

**1. 向量语义搜索 (VectorStore)**
```
查询文本 → OpenAI text-embedding-3-large → 1024维向量
    → Qdrant query_points (cosine距离, top_k * 2)
    → 支持 document_filter (payload 条件过滤)
```

**2. BM25 全文搜索 (BM25Search)**
```
查询文本 → plainto_tsquery('english', query)
    → PostgreSQL ts_rank_cd (search_vector, ..., 32)
    → ORDER BY score DESC LIMIT top_k * 2
    → 支持 document = %s 过滤
```

SQL 核心:
```sql
SELECT doc_id, title, breadcrumb, url, body_text,
       ts_rank_cd(search_vector, plainto_tsquery('english', %s), 32) as score
FROM regulations
WHERE search_vector @@ plainto_tsquery('english', %s)
  AND (%s::text IS NULL OR document = %s)
ORDER BY score DESC LIMIT %s
```

**3. 图谱查询 (GraphQueries)**
- 概念匹配: `get_related_by_concept()` → 通过 concepts 表找相关法规
- 法规引用链: `search_by_regulation_number()` → `get_interpretations()` + `get_amendments()`

图谱查询使用 PostgreSQL 递归 CTE (替代 Neo4j):
```sql
-- 获取法规父链 (从子到根)
WITH RECURSIVE ancestors AS (
    SELECT doc_id, parent_doc_id, title, breadcrumb, 0 as depth
    FROM regulations WHERE doc_id = %s
    UNION ALL
    SELECT r.doc_id, r.parent_doc_id, r.title, r.breadcrumb, a.depth + 1
    FROM regulations r JOIN ancestors a ON r.doc_id = a.parent_doc_id
    WHERE a.depth < 20
)
SELECT * FROM ancestors ORDER BY depth DESC
```

#### RRF 融合

Reciprocal Rank Fusion 公式: `score = Σ 1/(k + rank)`, k=60

每路检索结果独立排序后，按排名计算 RRF 分数。同一文档在多路中出现时分数累加。

#### 动态 top_k

基于增强查询中的法规计数动态调整:
- 3+ 个法规 → top_k + 5 (上限 15)
- 2+ 个法规 → top_k + 3 (上限 12)
- 复杂查询 (含数值参数/适用性关键词) → top_k * 2 (上限 15)
- 默认 → 使用 QueryClassifier 输出的 top_k

#### Graph Expansion

从 RRF 排序后的 top-5 结果中跟踪交叉引用:

```
Top-5 results
    │
    ├── 提取 doc_ids
    ├── get_cross_document_regulations(doc_id)
    │   → references[].target_doc_id
    │
    ├── 过滤: 排除已在结果中的文档
    │
    ├── BM25 搜索: 用关联法规的 title 作为查询
    │   → 获取最多 3 个额外 chunks
    │
    ▼
    追加到结果列表 (rrf_score=0.005, _graph_expanded=True)
```

#### 图上下文附加

对每个最终结果附加 `graph_context`:
- `breadcrumb_path`: 父链标题拼接 ("SOLAS > Chapter II-1 > Regulation 3-6")
- `has_interpretations`: 是否有统一解释
- `interpretation_count`: 解释数量

### 5.5 向量存储 (`retrieval/vector_store.py`)

**Qdrant Cloud 配置**:
- Collection: `imo_regulations`
- 向量维度: 1024
- Embedding 模型: text-embedding-3-large (OpenAI)
- 量化: INT8 scalar quantization (节省存储)
- 距离: Cosine

**搜索流程**:
1. 调用 OpenAI Embeddings API 获取查询向量
2. 构建 Qdrant Filter (document, collection 条件)
3. `client.query_points()` 执行向量搜索
4. 返回 payload 中的 text, metadata (排除 text_for_embedding 字段)

---

## 6. 生成系统

### 6.1 答案生成器 (`generation/generator.py`)

#### 模型路由策略

**三层模型选择**:

```
Layer 1: QueryClassifier 意图驱动
    ├── classification.model == "primary" → Sonnet
    ├── classification.model == "fast" → Haiku
    └── 其他 → 进入 Layer 2

Layer 2: 兜底路由 (_select_model)
    │
    ├── Haiku 条件 (任一触发):
    │   ├── 查询包含精确法规引用 (SOLAS/MARPOL + 编号)
    │   ├── top chunk 分数 > 0.75
    │   └── word_count < 15 且无关系词
    │
    ├── Sonnet 覆盖 (任一触发):
    │   ├── 包含 COMPLEX_KEYWORDS (compare/区别/适用/豁免/...)
    │   ├── 含船舶参数 (数值+单位: 米/m/吨/GT/DWT)
    │   ├── 含船型关键词 (货船/客船/国际航行/...)
    │   ├── 含适用性关键词 (是否/需不需要/must/...)
    │   └── 查询长度 > 60 字符
    │
    └── Sonnet 覆盖优先级高于 Haiku 条件
```

**模型配置**:
| 模型 | ID | max_tokens | max_context_tokens |
|------|----|-----------|-------------------|
| Primary (Sonnet) | claude-sonnet-4-20250514 | 2048 | 5000 |
| Fast (Haiku) | claude-haiku-4-5-20251001 | 1024 | 3000 |

#### Context 构建

`_build_context()` 按以下规则构建法规上下文:
- 每个 chunk 最大 1600 字符 (超出截断)
- token 估算: `len(text) // 4`
- 累计不超过 max_context_tokens
- 格式: `**[breadcrumb]** (Source: url)\n{text}`
- 如有 interpretations 则追加提示

#### System Prompt 结构

```
角色: 资深验船师 (20年经验)
    │
    ├── 核心原则:
    │   ├── 结论先行: 第一句给明确结论
    │   ├── 实务优先: 实际执行 > 字面理解
    │   ├── 完整配置: 给整套方案，不只单个条款
    │   ├── 决策树格式: if...then... 分支
    │   ├── 主动识别遗漏: 缺关键信息时主动补充
    │   ├── 引用规范: [SOLAS III/31.1.4] 格式
    │   └── 上下文处理: [Context: ...] 前缀感知
    │
    ├── 验船实务参考: 使用注入的实务知识
    │
    ├── 语言规则:
    │   ├── 中文提问→中文回答
    │   ├── 英文术语首次出现加中文释义
    │   └── 400-600 字控制
    │
    ├── [Haiku 追加] 简洁回答，≤300 字
    ├── [Sonnet 追加] 完整但不冗余，≤600 字
    │
    ├── [有用户偏好] 注入用户常查法规
    └── [适用性查询] 注入船舶参数 (船型/船长/吨位)
```

#### 引用提取

从生成的答案中通过正则提取法规引用:
```python
CITATION_PATTERN = re.compile(
    r"\[(SOLAS|MARPOL|MSC|MEPC|ISM|ISPS|Resolution|LSA|FSS|FTP|STCW|COLREG)[^\]]*\]"
)
```

#### 置信度评估

基于检索结果最高分数:
- `> 0.85` → high
- `> 0.60` → medium
- 其他 → low

---

## 7. 对话记忆系统

### 7.1 会话管理 (`memory/conversation_memory.py`)

#### 数据结构

```python
@dataclass
class ConversationTurn:
    turn_id: str       # UUID
    role: str          # "user" | "assistant"
    content: str       # 消息内容
    timestamp: float   # Unix 时间戳
    input_mode: str    # "voice" | "text"
    metadata: dict     # {enhanced_query, citations, confidence, retrieved_regulations}

@dataclass
class SessionContext:
    session_id: str              # 前端传入或自动生成
    user_id: str                 # 用户 ID
    turns: list[ConversationTurn]
    active_regulations: list[str]  # 活跃法规列表 (最多20个)
    active_topics: list[str]
    active_ship_type: str | None
```

#### Redis 存储

- Key: `session:{session_id}`
- Value: JSON 序列化的 SessionContext
- TTL: 24 小时 (`session_ttl_hours * 3600`)
- 编码: `ensure_ascii=False` (保留中文)

#### 会话持久化

前端通过 `session_id` 参数维持会话连续性:
1. 首次请求: 后端生成 UUID，返回 `session_id`
2. 前端保存 `SESSION_ID`，后续请求携带
3. 后端 `get_session()` 加载已有会话
4. `create_session()` 接受可选 `session_id` 参数，优先使用前端传入值

#### Turn 追踪

每次 `add_turn()` 时:
- **user turn**: 检测船型关键词，更新 `active_ship_type` 和 `active_topics`
- **assistant turn**:
  - 从 metadata.retrieved_regulations 追踪检索到的法规
  - 从答案文本中正则提取引用的法规
  - 从 metadata.citations 追踪引用对象
  - `active_regulations` 保持最近 20 个

### 7.2 指代消解 (Coreference Resolution)

三层策略，逐层回退:

```
Layer 1: 正则检测 (零延迟)
    │
    ├── 检测中文代词: 这个, 那个, 该, 它的, 刚才, 这条, 此, ...
    ├── 检测英文代词: this, that, it, the above, same, aforementioned, ...
    │
    ├── 无代词 → 直接返回原查询
    ├── 无 active_regulations → 直接返回原查询
    └── 有代词 + 有 regulations → 进入 Layer 2

Layer 2: 上下文前缀注入 (零 API 调用)
    │
    ├── 2a: 从最近 assistant turn 的 metadata 获取 retrieved_regulations
    │   → "[Context: the previous question was about {reg1}, {reg2}] {query}"
    │
    ├── 2b: 回退到 session 级 active_regulations
    │   → "[Context: this conversation has discussed {reg1}, {reg2}] {query}"
    │
    └── 都无法获取 → 进入 Layer 3

Layer 3: LLM 兜底 (Haiku API 调用)
    │
    ├── 构建上下文: 最近 6 个 turn 的摘要
    ├── 调用 Claude Haiku (max_tokens=150)
    ├── 指令: 将代词替换为具体法规名称，保持原始语言
    ├── 长度校验: 结果 < 原查询 3 倍 且 > 5 字符
    └── 失败 → 返回原查询
```

### 7.3 LLM 上下文构建

`build_llm_context()`:
1. 取最近 `max_turns * 2` 个 turn 作为 messages
2. 超出部分用 Haiku 摘要 (200 tokens)
3. 对当前查询执行指代消解
4. 返回 (messages, enhanced_query) 元组

### 7.4 用户画像

```python
# 存储: user_profile:{user_id}
{
    "total_queries": int,
    "regulation_counts": {"SOLAS III": 5, "MARPOL I": 3, ...},
    "ship_types": {"cargo ship": 10, "bulk carrier": 3, ...}
}
```

`get_user_context()` 输出: "用户常查法规: SOLAS III(5次), MARPOL I(3次), ..."

---

## 8. 语音系统

### 8.1 STT 服务 (`voice/stt_service.py`)

| 参数 | 值 |
|------|-----|
| 主模型 | gpt-4o-mini-transcribe |
| 回退模型 | whisper-1 |
| 输入格式 | webm (浏览器录音) |
| 自动语言检测 | 支持，也可指定 language 参数 |

**回退逻辑**: 主模型失败 → `audio_file.seek(0)` 重置 → whisper-1 重试

### 8.2 TTS 服务 (`voice/tts_service.py`)

| 参数 | 值 |
|------|-----|
| 模型 | gpt-4o-mini-tts |
| 声音 | ash |
| 输出格式 | mp3 |
| 最大文本长度 | 1500 字符 |

**海事专用朗读指令**:
```
Speak clearly and at a moderate pace. When reading regulation numbers like
'II-1/3-6' or 'SOLAS Chapter XII', pronounce each part distinctly with a
brief pause between segments. Emphasize numerical values such as dimensions,
tonnage, and dates. Maintain a professional, authoritative tone.
```

**TTS 文本预处理** (`prepare_tts_text()`):
1. 移除 "参考来源" / "Sources:" / "References:" 段落
2. 去除 Markdown 格式: `**bold**`, `# heading`, `> quote`, `- list`
3. 去除 URL
4. 去除方括号引用 `[SOLAS III/31]` → `SOLAS III/31`
5. 合并多余空行
6. 超长截断: 在 1500 字符处找最近的句号截断

### 8.3 按需 TTS 架构

文字查询模式不自动生成音频。前端提供 "Play Audio" 按钮，点击后调用独立 `/api/v1/voice/tts` 端点:

```
POST /api/v1/voice/tts
    Body: text={answer_text}
    Response: { answer_audio_base64, audio_format: "mp3" }
```

优势: 节省 90%+ 的 TTS API 调用费用。

---

## 9. 知识库系统

### 9.1 实务知识库 (`knowledge/practical_knowledge.py`)

**目的**: 补充 LLM 训练数据中缺失的验船实务经验，纠正法规字面解读与实际执行的差异。

#### YAML 条目结构

```yaml
- id: cargo_liferaft_davit
  title: "货船救生筏降落设备配置"
  keywords: ["救生筏", "降落设备", "起降", "davit"]
  terms: ["davit-launched liferaft", "throw-overboard"]
  regulations: ["SOLAS III/31", "SOLAS III/31.1.4"]
  ship_types: ["cargo ship", "bulk carrier", "tanker"]
  common_mistake: "看到 'on each side' 就认为两舷都需要 davit..."
  correct_interpretation: "≥85m 货船的标准配置是：一舷 davit，另一舷 throw-overboard..."
  typical_configurations:
    - "最常见配置：船尾 free-fall lifeboat + 两舷 throw-overboard liferafts"
    - "无 free-fall 配置：一舷 davit + davit-launched，另一舷 throw-overboard"
  decision_tree:
    - "Step 1: 确认船型（货船 vs 客船）"
    - "Step 2: 确认船长（≥85m 适用 SOLAS III/31.1.4）"
    - ...
```

#### 六个知识文件

| 文件 | 条目数 | 覆盖领域 |
|------|--------|---------|
| lifesaving.yaml | 3 | 救生筏降落设备、容量计算、free-fall 豁免 |
| fire_safety.yaml | 3 | 探火系统分区、便携式灭火器、结构防火 |
| stability.yaml | 2 | 完整稳性标准、破损稳性 |
| marpol.yaml | 3 | 油水分离器、污水排放、压载水 |
| navigation.yaml | 2 | AIS 要求、ECDIS 要求 |
| survey_practice.yaml | 2 | PSC 重点检查项、测厚要求 |

#### 索引机制

```python
class PracticalKnowledgeBase:
    _by_id: dict[str, dict]           # id → entry 直接映射
    _keyword_index: dict[str, list]    # keyword → [entry_ids] 倒排索引
    _reg_index: dict[str, list]        # regulation → [entry_ids] 倒排索引
```

#### 查询评分

```python
# 权重分配:
keyword 命中: +2 (关键词出现在用户查询中)
regulation 命中: +3 (法规编号匹配)
regulation 在查询中: +2
matched_terms 命中: +1 (QueryEnhancer 映射的英文术语)
ship_type 命中: +2

# 返回 top 3 (按总分降序)
```

#### LLM 注入格式

```markdown
## 验船实务参考（来自资深验船师经验）

### 货船救生筏降落设备配置
**适用法规**: SOLAS III/31, SOLAS III/31.1.4
**正确理解**: ≥85m 货船的标准配置是...
**常见误解**: 看到 'on each side' 就认为两舷都需要 davit...
**典型配置**:
- 最常见配置：船尾 free-fall lifeboat + 两舷 throw-overboard liferafts
- 无 free-fall 配置：一舷 davit + davit-launched，另一舷 throw-overboard
**判断逻辑**:
- Step 1: 确认船型（货船 vs 客船）
- Step 2: 确认船长（≥85m 适用 SOLAS III/31.1.4）
```

---

## 10. API 层

### 10.1 路由总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/voice/query` | 语音查询 (上传音频文件) |
| POST | `/api/v1/voice/text-query` | 文字查询 |
| POST | `/api/v1/voice/tts` | 按需 TTS |
| WS | `/api/v1/voice/ws/{session_id}` | WebSocket 实时查询 |
| POST | `/api/v1/search` | 独立搜索接口 |
| GET | `/api/v1/regulation/{doc_id}` | 获取单条法规 |
| GET | `/api/v1/admin/stats` | 系统统计 (PG/Qdrant/Redis) |
| GET | `/api/v1/admin/session/{session_id}` | 调试: 查看会话内容 |
| POST | `/api/v1/admin/reindex` | 重建索引 (提示本地执行) |

### 10.2 文字查询接口

```
POST /api/v1/voice/text-query
Content-Type: multipart/form-data

Parameters:
  text: str (required)        - 查询文本
  session_id: str (optional)  - 会话 ID
  generate_audio: bool (false) - 是否生成音频
  input_mode: str ("text")    - 输入模式

Response:
{
  "session_id": "uuid",
  "enhanced_query": "增强后的查询",
  "answer_text": "Markdown 格式答案",
  "answer_audio_base64": null,
  "citations": [{"citation": "[SOLAS III/31]", "verified": true}],
  "confidence": "high",
  "model_used": "claude-sonnet-4-20250514",
  "sources": [{"chunk_id": "...", "url": "...", "breadcrumb": "...", "score": 0.85}],
  "timing": {
    "memory_ms": 15,
    "retrieval_ms": 800,
    "generation_ms": 3000,
    "tts_ms": 0,
    "total_ms": 3815
  },
  "input_mode": "text",
  "transcription": "原始文本"
}
```

### 10.3 WebSocket 协议

```json
// 客户端 → 服务端
{"type": "text", "text": "SOLAS II-1/3-6的要求？"}
{"type": "audio", "audio": "<base64_encoded_audio>"}

// 服务端 → 客户端
{"type": "response", "session_id": "...", "answer_text": "...", ...}
{"type": "error", "message": "..."}
```

### 10.4 管线编排 (`pipeline/voice_qa_pipeline.py`)

`VoiceQAPipeline._process_query()` 编排完整请求处理流程:

```
1. 会话加载/创建 (Redis)
2. build_llm_context → (messages, enhanced_query)
3. QueryClassifier.classify(text) → intent, ship_info, top_k, model
4. HybridRetriever.retrieve(enhanced_query, top_k)
5. PracticalKnowledgeBase.query(text) + format_for_llm()
6. AnswerGenerator.generate(query, chunks, messages, user_context, practical_context, classification)
7. [按需] TTS 合成
8. 提取 retrieved_regulations (从 chunk metadata 标题中正则提取)
9. add_turn(user) + add_turn(assistant, metadata={retrieved_regulations, citations, confidence})
10. 返回结果
```

**法规引用提取** (`_extract_regulation_ref()`):
```python
# 优先从 title 中提取精确引用
pattern = r"(SOLAS|MARPOL|STCW|COLREG|ISM|ISPS|LSA|FSS|IBC|IGC|MSC|MEPC)\s*(?:Regulation\s*)?[\w\-\/\.]+"
# 回退: regulation_number (如果足够具体且 > 3 字符)
# 再回退: document + 截断 title
```

---

## 11. 前端

### 单页应用 (`static/index.html`)

纯 Vanilla JavaScript，无框架依赖。

**核心功能**:
- 文字输入框 + 发送按钮
- 语音录音按钮 (MediaRecorder API)
- 回答展示区 (支持 Markdown 渲染)
- "Play Audio" 按钮 (按需 TTS)
- 会话 ID 维护 (`let SESSION_ID`)
- 历史记录展示

**会话持久化**:
```javascript
let SESSION_ID = '';

// 每次请求后更新
async function sendText() {
    const response = await fetch('/api/v1/voice/text-query', { ... });
    const data = await response.json();
    if (data.session_id) SESSION_ID = data.session_id;
}
```

**按需 TTS**:
```javascript
async function playAudio(text) {
    const response = await fetch('/api/v1/voice/tts', {
        method: 'POST',
        body: new URLSearchParams({ text }),
    });
    const data = await response.json();
    if (data.answer_audio_base64) {
        const audio = new Audio('data:audio/mp3;base64,' + data.answer_audio_base64);
        audio.play();
    }
}
```

---

## 12. 部署与运维

### 12.1 Docker 配置

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY . .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 12.2 Railway 配置

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "uvicorn api.main:app --host 0.0.0.0 --port 8000"
healthcheckPath = "/health"
healthcheckTimeout = 300
numReplicas = 1
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

### 12.3 环境变量

| 变量 | 说明 | 来源 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API (STT/TTS/Embedding) | 手动配置 |
| `ANTHROPIC_API_KEY` | Anthropic API (Claude LLM) | 手动配置 |
| `QDRANT_URL` | Qdrant Cloud 集群地址 | 手动配置 |
| `QDRANT_API_KEY` | Qdrant Cloud API Key | 手动配置 |
| `DATABASE_URL` | PostgreSQL 连接字符串 | Railway 自动注入 |
| `REDIS_URL` | Redis 连接字符串 | Railway 自动注入 |

### 12.4 配置管理 (`config/settings.py`)

使用 Pydantic BaseSettings，自动从 `.env` 和环境变量加载:

```python
class Settings(BaseSettings):
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1024
    llm_model_primary: str = "claude-sonnet-4-20250514"
    llm_model_fast: str = "claude-haiku-4-5-20251001"
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "ash"
    max_conversation_turns: int = 10
    session_ttl_hours: int = 24
```

---

## 13. 回归测试

### 测试套件 (`tests/regression_test.py`)

8 个端到端测试用例，覆盖核心场景:

| ID | 查询类型 | 验证点 | 期望模型 |
|----|---------|--------|---------|
| T001 | 规格查询 | SOLAS II-1/3-6 开口尺寸 600mm | Haiku |
| T002 | 适用性分析 | 100m 货船救生筏 davit 配置 (单边/throw-overboard) | Sonnet |
| T003 | 指代消解 | "这个规定适用于FPSO吗" → 解析为 SOLAS II-1/3-6 | - |
| T004 | 英文规格 | 最小初稳高 GM 0.15m | - |
| T005 | 中文领域 | 散货船货舱通道要求 | - |
| T006 | MARPOL | 油水分离器 15ppm 排放标准 | - |
| T007 | 比较分析 | 客船 vs 货船救生设备 → SOLAS III | Sonnet |
| T008 | 消防 | A-60 vs A-0 防火门区别 | - |

### 检查维度

每个测试检查:
- `expect_contains`: 答案必须包含的关键词
- `expect_not_contains`: 答案不能包含的关键词 (如 "无法回答")
- `expect_contains_any`: 至少包含一组关键词中的一个
- `expect_model`: 使用的模型匹配
- `max_time_ms`: 响应时间上限

### 执行

```bash
python tests/regression_test.py https://bv-rag-production.up.railway.app
```

---

## 14. 数据统计

| 指标 | 数值 |
|------|------|
| Qdrant 向量点数 | 24,476 |
| PostgreSQL 法规记录数 | 18,589 |
| Qdrant Collection | imo_regulations |
| 向量维度 | 1024 |
| 术语映射数 | 57 组 (TERMINOLOGY_MAP) |
| 话题→法规映射 | 15 组 (TOPIC_TO_REGULATIONS) |
| 实务知识条目 | 15 条 (6 个 YAML 文件) |
| 回归测试用例 | 8 个 |
| 会话 TTL | 24 小时 |
| 最大对话轮次 | 10 (超出自动摘要) |

---

## 附录: PostgreSQL Schema

### regulations 表
```sql
CREATE TABLE regulations (
    doc_id TEXT PRIMARY KEY,
    title TEXT,
    document TEXT,
    regulation TEXT,
    breadcrumb TEXT,
    body_text TEXT,
    page_type TEXT,
    url TEXT,
    parent_doc_id TEXT,
    search_vector tsvector  -- GIN 索引，用于 BM25 搜索
);
```

### cross_references 表
```sql
CREATE TABLE cross_references (
    source_doc_id TEXT,
    target_doc_id TEXT,
    anchor_text TEXT,
    relation_type TEXT,  -- 'INTERPRETS', 'AMENDS', 'REFERENCES'
    title TEXT,
    url TEXT
);
```

### concepts 表
```sql
CREATE TABLE concepts (
    concept_id TEXT PRIMARY KEY,
    name TEXT
);

CREATE TABLE regulation_concepts (
    doc_id TEXT,
    concept_id TEXT
);
```
