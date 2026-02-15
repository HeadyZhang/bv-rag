# BV-RAG: 海事法规语音智能问答系统
# 最终执行方案 — Railway部署版

> **状态**: 可直接喂给 Claude Code 逐阶段执行
> **已就绪**: OpenAI API ✅ | Anthropic API ✅ | Qdrant Cloud (BV-RAG cluster) ✅
> **部署平台**: Railway Pro ($20/月)

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户 (验船师)                              │
│              🎤 语音输入  /  ⌨️ 文字输入                          │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTPS (Railway自动提供)
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                Railway Project: bv-rag                           │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │            FastAPI 主服务 (Python)                        │    │
│  │                                                           │    │
│  │  ┌─────────┐  ┌──────────────┐  ┌─────────────────┐     │    │
│  │  │ STT     │  │ RAG Pipeline │  │ TTS             │     │    │
│  │  │ OpenAI  │  │              │  │ OpenAI          │     │    │
│  │  │ transcr.│→ │ 查询理解     │→ │ gpt-4o-mini-tts │     │    │
│  │  └─────────┘  │ 混合检索     │  └─────────────────┘     │    │
│  │               │ LLM生成      │                           │    │
│  │               │ (Claude)     │                           │    │
│  │               └──────┬───────┘                           │    │
│  └──────────────────────┼───────────────────────────────────┘    │
│                         │                                         │
│  ┌──────────────────────┼───────────────────────────────────┐    │
│  │  Redis (Railway一键部署)                                   │    │
│  │  • 会话记忆 (session:{id})                                │    │
│  │  • 用户画像 (user_profile:{id})                           │    │
│  └──────────────────────┼───────────────────────────────────┘    │
│                         │                                         │
│  ┌──────────────────────┼───────────────────────────────────┐    │
│  │  PostgreSQL (Railway一键部署)                               │    │
│  │  • 法规文本存储 + FTS5全文检索 (替代Elasticsearch)          │    │
│  │  • 知识图谱关系表 (替代Neo4j)                              │    │
│  │  • chunk元数据                                             │    │
│  └──────────────────────┘───────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
   ┌────────────┐ ┌──────────┐ ┌──────────┐
   │ Qdrant     │ │ OpenAI   │ │ Anthropic│
   │ Cloud      │ │ API      │ │ API      │
   │ (BV-RAG)   │ │          │ │          │
   │ 向量检索    │ │ STT+TTS  │ │ Claude   │
   │ FREE tier  │ │ Embedding│ │ LLM推理  │
   └────────────┘ └──────────┘ └──────────┘
```

### 为什么这样精简

| 原方案 | 现方案 | 原因 |
|-------|-------|------|
| Qdrant 自托管 | **Qdrant Cloud 免费集群** | 已创建BV-RAG集群，零运维 |
| Elasticsearch | **PostgreSQL FTS** | Railway原生支持PG，全文检索够用 |
| Neo4j 图数据库 | **PostgreSQL 关系表** | 法规层级用递归CTE查询，省一个服务 |
| 自购服务器+证书 | **Railway Pro** | 自动HTTPS，Git push部署 |
| 分散的4个数据库 | **2个Railway服务 + 1个外部** | 降低成本和复杂度 |

---

## 环境变量清单

在 Railway 项目中配置以下环境变量:

```env
# === API Keys ===
OPENAI_API_KEY=sk-xxx                     # OpenAI: STT + TTS + Embedding
ANTHROPIC_API_KEY=sk-ant-xxx              # Anthropic: Claude LLM
QDRANT_URL=https://xxx.aws.cloud.qdrant.io  # Qdrant Cloud: BV-RAG集群URL
QDRANT_API_KEY=xxx                        # Qdrant Cloud: API Key

# === Railway 内部服务 (自动注入) ===
DATABASE_URL=${{Postgres.DATABASE_URL}}   # PostgreSQL 连接串
REDIS_URL=${{Redis.REDIS_URL}}            # Redis 连接串

# === 应用配置 ===
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIMENSIONS=1024                 # 降维到1024，省Qdrant内存
LLM_MODEL_PRIMARY=claude-sonnet-4-20250514
LLM_MODEL_FAST=claude-haiku-4-5-20251001
STT_MODEL=gpt-4o-mini-transcribe
TTS_MODEL=gpt-4o-mini-tts
TTS_VOICE=ash

# === 系统配置 ===
PORT=8000
ENVIRONMENT=production
LOG_LEVEL=INFO
MAX_CONVERSATION_TURNS=10
SESSION_TTL_HOURS=24
```

---

## Phase 0: 项目初始化与基础设施

### Claude Code 指令:

```
请初始化 BV-RAG 海事法规语音问答项目。

## 目录结构

创建以下完整目录结构:

bv-rag/
├── README.md
├── pyproject.toml
├── Dockerfile
├── railway.toml                    # Railway部署配置
├── .env.example
│
├── config/
│   └── settings.py                 # Pydantic Settings，从环境变量读取所有配置
│
├── crawler/
│   ├── spider.py                   # Scrapy全站爬虫
│   └── run_crawler.py              # 爬虫启动脚本
│
├── parser/
│   ├── html_parser.py              # HTML解析器
│   └── quality_check.py            # 解析质量检查
│
├── chunker/
│   ├── regulation_chunker.py       # 法规分块器
│   └── chunk_stats.py              # 分块统计
│
├── db/
│   ├── postgres.py                 # PostgreSQL 连接管理
│   ├── schema.sql                  # 建表SQL（含FTS索引+图关系表）
│   ├── graph_queries.py            # 图谱查询（用SQL递归CTE实现）
│   └── bm25_search.py              # 基于PG tsvector的全文检索
│
├── retrieval/
│   ├── vector_store.py             # Qdrant Cloud 向量检索
│   ├── hybrid_retriever.py         # 混合检索 (向量+BM25+图谱) + RRF融合
│   └── query_router.py             # 查询意图路由
│
├── generation/
│   ├── prompts.py                  # System Prompt
│   └── generator.py                # Claude LLM 答案生成
│
├── voice/
│   ├── stt_service.py              # OpenAI STT 语音转文字
│   └── tts_service.py              # OpenAI TTS 文字转语音
│
├── memory/
│   └── conversation_memory.py      # Redis会话记忆 + 指代消解
│
├── pipeline/
│   ├── ingest.py                   # 数据入库总管线
│   └── voice_qa_pipeline.py        # 语音问答端到端管线
│
├── api/
│   ├── main.py                     # FastAPI入口
│   └── routes/
│       ├── voice.py                # 语音/文字查询API
│       ├── search.py               # 纯检索API
│       └── admin.py                # 管理接口(重新索引/统计)
│
├── evaluation/
│   ├── test_queries.json           # 测试查询集
│   └── run_eval.py                 # 评估脚本
│
├── scripts/
│   ├── crawl.sh                    # 爬取脚本
│   ├── ingest.sh                   # 入库脚本
│   └── seed_data.py                # 初始化数据库schema
│
├── data/                           # 本地开发用，不上传Railway
│   ├── raw/
│   ├── parsed/
│   └── chunks/
│
└── tests/
    ├── test_parser.py
    ├── test_chunker.py
    ├── test_retrieval.py
    └── test_voice.py


## pyproject.toml

[project]
name = "bv-rag"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = [
    # Web框架
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "python-multipart>=0.0.18",   # 文件上传
    "websockets>=14.0",

    # AI APIs
    "openai>=1.60",               # STT + TTS + Embedding
    "anthropic>=0.42",            # Claude LLM

    # 数据库
    "qdrant-client>=1.12",        # Qdrant Cloud
    "asyncpg>=0.30",              # PostgreSQL async
    "psycopg2-binary>=2.9",       # PostgreSQL sync (用于数据入库)
    "redis>=5.2",                 # Redis

    # 爬虫与解析
    "scrapy>=2.12",
    "beautifulsoup4>=4.12",
    "lxml>=5.3",

    # 工具
    "tiktoken>=0.8",              # Token计数
    "pydantic-settings>=2.7",     # 配置管理
    "tenacity>=9.0",              # 重试
    "rich>=13.9",                 # 终端美化输出
    "python-dotenv>=1.0",
]


## Dockerfile

FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# 复制源码
COPY . .

# 启动
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]


## railway.toml

[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
healthcheckPath = "/health"
healthcheckTimeout = 300
numReplicas = 1
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3


## config/settings.py

使用 pydantic-settings 从环境变量读取所有配置:

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Keys
    openai_api_key: str
    anthropic_api_key: str
    qdrant_url: str
    qdrant_api_key: str

    # Railway 自动注入
    database_url: str                          # PostgreSQL
    redis_url: str                             # Redis

    # 模型配置
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1024           # ← 降维
    llm_model_primary: str = "claude-sonnet-4-20250514"
    llm_model_fast: str = "claude-haiku-4-5-20251001"
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "ash"

    # 系统配置
    port: int = 8000
    environment: str = "production"
    log_level: str = "INFO"
    max_conversation_turns: int = 10
    session_ttl_hours: int = 24

    class Config:
        env_file = ".env"

settings = Settings()


## .env.example

完整的环境变量模板，注释说明每个变量用途。


## api/main.py 骨架

创建 FastAPI 应用骨架:
- GET /health → 返回 {"status": "ok"}
- 启动时初始化所有服务连接 (Qdrant, PostgreSQL, Redis, OpenAI, Anthropic)
- 注册所有路由
- CORS 中间件（允许前端跨域）

确保所有文件创建完毕，依赖可以安装，health endpoint 可访问。
```

---

## Phase 1: 全站爬取

### Claude Code 指令:

```
基于 bv-rag 项目，实现 imorules.com 全站爬虫。

## 目标
爬取 https://www.imorules.com/ 全部HTML页面，包含7大分类下的所有层级页面。

## 实现 crawler/spider.py

使用 Scrapy CrawlSpider:

1. 起始URL:
   - https://www.imorules.com/
   - https://www.imorules.com/COLLECTION-_-_9.html    (International Conventions)
   - https://www.imorules.com/COLLECTION-_-_10.html   (International Codes)
   - https://www.imorules.com/COLLECTION-_-_11.html   (Resolutions)
   - https://www.imorules.com/COLLECTION-_-_15.html   (Circulars)
   - https://www.imorules.com/COLLECTION-_-_30.html   (Guidelines)
   - https://www.imorules.com/COLLECTION-_-_31.html   (Specifications and Manuals)
   - https://www.imorules.com/COLLECTION-_-_32.html   (International Conferences)

2. 爬取规则:
   - allowed_domains: ['imorules.com', 'www.imorules.com']
   - 只跟踪 .html 结尾的链接
   - DEPTH_LIMIT = 15
   - DOWNLOAD_DELAY = 1.0 秒
   - CONCURRENT_REQUESTS = 3
   - HTTPCACHE_ENABLED = True (缓存到 data/cache/)
   - ROBOTSTXT_OBEY = True

3. 每个页面提取:
   - url: 页面完整URL
   - title: 从h1/h2/h3或<title>提取
   - breadcrumb: 面包屑路径文本（通常在页面顶部表格中，包含 "---" 分隔符）
     格式如: "Clasification Society 2024 - Version 9.40 --- Statutory Documents - IMO Publications and Documents - International Conventions - SOLAS - Chapter V - Regulation 19"
   - raw_html: 完整HTML源码
   - internal_links: [{url, anchor_text, href}] 页面内所有内部.html链接
   - child_links: [{url, title, href}] <li>标签内的子页面链接（用于层级关系）
   - parent_topic: 从 "Parent topic:" 附近的链接提取 {url, href}
   - page_hash: raw_html的MD5

4. 输出:
   - data/raw/pages.jsonl  (每行一个JSON)
   - 爬取完成后打印统计: 总页面数、成功数、失败数

5. 实现 crawler/run_crawler.py:
   - 命令行脚本，可以直接 python -m crawler.run_crawler 运行
   - 打印进度

6. 实现 scripts/crawl.sh:
   #!/bin/bash
   cd /app && python -m crawler.run_crawler
```

---

## Phase 2: HTML解析与清洗

### Claude Code 指令:

```
实现 imorules.com HTML解析管线。

## 网站HTML结构特征（非常重要，请严格参考）

每个页面的HTML结构为:
- 外层<table>包含整个页面
- 第一个<td>: 面包屑路径，格式 "Clasification Society 2024 - Version 9.40 --- ... - SOLAS - Chapter V"
- 第二个<td>: 主要内容区域
  - 标题（文本）
  - 正文: 法规条文，带编号（如 "1.1", "2.3", ".1", ".2"）
  - 子链接列表: <li><a href="xxx.html">子页面标题</a></li>
  - 交叉引用: <a href="GUID-xxx.html">regulation II-1/3-6</a>
  - 表格: 嵌套<table>
- 最后一个<td>: 版权声明 "Copyright 2022 Clasifications Register..."
- "Parent topic:" 文本后跟父页面链接

## URL命名规律
- 公约入口: SOLAS.html, MARPOL.html
- 章节索引: SOLAS_REGII-1.html, SOLAS_REGV.html
- 具体条款: SOLAS_REGV.A.19.html
- 详细内容: GUID-{UUID}.html (叶子节点，包含实际法规正文)
- 决议: MSCRES_158.78.html, IMORES_A1078.28.html
- 通函: MSCCIRC_1663.html
- 集合页: COLLECTION-_-_{N}.html
- 脚注: Chunk{ID}.html

## 实现 parser/html_parser.py

class ParsedRegulation (dataclass):
    doc_id: str              # 从URL生成: SOLAS_REGV.A.19 或 GUID-xxx
    url: str
    breadcrumb: str          # 完整面包屑
    collection: str          # convention/code/resolution/circular/guideline/specification/conference
    document: str            # SOLAS/MARPOL/ISM Code 等
    chapter: str             # Chapter II-1, Annex I 等
    part: str                # Part A, Part B
    regulation: str          # Regulation 3-6, Rule 14
    paragraph: str           # 段落编号
    title: str               # 页面标题
    body_text: str           # 清洗后纯文本（移除版权、导航）
    body_structured: list    # [{type, number, text}] 结构化条目
    parent_url: str          # 父页面URL
    child_urls: list         # 子页面URL列表
    cross_references: list   # [{target_url, target_text, context}]
    page_type: str           # index(有>2子链接)/content(叶子)/footnote(Chunk)/collection
    version: str             # Rulefinder版本号

class IMOHTMLParser:
    公约名称识别列表:
    CONVENTIONS = ['SOLAS', 'MARPOL', 'STCW', 'COLREG', 'Load Lines', 'Tonnage', 'CLC', 'OPRC', 'AFS', 'BWM', 'SAR', 'SUA']
    CODES = ['ISM', 'ISPS', 'LSA', 'FSS', 'FTP', 'IBC', 'IGC', 'IGF', 'IMDG', 'CSS', 'CTU', 'HSC', 'MODU', 'ESP', 'Grain', 'NOx', 'OSV', 'Polar', 'SPS', 'IMSBC']

    方法:
    - parse_page(raw_data) → ParsedRegulation
    - _identify_collection(): 从breadcrumb识别顶级分类
    - _identify_document(): 从URL前缀和breadcrumb识别所属文档
    - _parse_breadcrumb(): 提取chapter/part/regulation/paragraph
    - _extract_body(): 提取正文，结构化为段落/列表/表格
    - _extract_cross_references(): 提取所有内链引用
    - _clean_text(): 移除版权声明、导航文本、多余空白

## 实现 parser/quality_check.py

对解析结果运行质量检查:
- 统计: 总文档数、按collection分布、按document分布
- 检查: body_text为空的文档、breadcrumb为空的文档
- 输出: 质量报告

## 管线
输入: data/raw/pages.jsonl
输出: data/parsed/regulations.jsonl
命令: python -m parser.html_parser
```

---

## Phase 3: 智能分块

### Claude Code 指令:

```
实现海事法规专用分块器。

## 实现 chunker/regulation_chunker.py

class Chunk (dataclass):
    chunk_id: str              # {doc_id}__chunk_{index}
    doc_id: str
    url: str
    text: str                  # 原始文本
    text_for_embedding: str    # 增强文本 = "[面包屑路径] 标题\n\n" + 原始文本
    metadata: dict             # 丰富的metadata用于过滤
    token_count: int

metadata结构:
{
    "collection": "convention",
    "document": "SOLAS",
    "chapter": "Chapter II-1",
    "part": "Part B",
    "regulation": "Regulation 3-6",
    "title": "Access to and Within Spaces...",
    "breadcrumb": "SOLAS > Chapter II-1 > Regulation 3-6",
    "page_type": "content",
    "regulation_number": "SOLAS II-1/3-6",   # 标准化编号，极其重要
    "url": "https://www.imorules.com/GUID-xxx.html",
    "has_table": false,
}

class RegulationChunker:
    __init__(target_tokens=512, max_tokens=1024, overlap_tokens=64)
    使用 tiktoken cl100k_base 编码器

分块策略:
1. 索引页(page_type=index/collection): 跳过，不创建chunk
2. 脚注页(page_type=footnote): 整页作为单个chunk
3. 内容页(page_type=content):
   a. 如有 body_structured → 按结构化条目累积分块
      - 以编号段落为自然边界
      - 累积到 target_tokens 时切分
      - 保留64 token overlap（前一个chunk最后一个段落的开头200字符）
   b. 如无结构 → 按句子边界分块

4. text_for_embedding 增强:
   在原文前加面包屑前缀，帮助embedding理解上下文
   例: "[SOLAS > Chapter II-1 > Regulation 3-6] Access to and Within Spaces\n\n原文..."

5. regulation_number 标准化:
   从 regulation 字段提取，格式: "{document} {regulation编号}"
   例: "SOLAS II-1/3-6", "MARPOL Annex VI/14"

## 实现 chunker/chunk_stats.py

统计报告:
- 总chunk数
- 平均/最小/最大 token数
- 按document分布
- 按collection分布

## 管线
输入: data/parsed/regulations.jsonl
输出: data/chunks/chunks.jsonl
命令: python -m chunker.regulation_chunker
```

---

## Phase 4: 数据库Schema与入库

### Claude Code 指令:

```
实现 PostgreSQL 数据库schema和数据入库管线。
PostgreSQL用来替代 Elasticsearch(全文检索) 和 Neo4j(知识图谱)。

## 实现 db/schema.sql

-- ==========================================
-- 1. 法规文本表（含全文检索）
-- ==========================================
CREATE TABLE IF NOT EXISTS regulations (
    doc_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    breadcrumb TEXT,
    collection TEXT,           -- convention/code/resolution/circular/guideline
    document TEXT,             -- SOLAS/MARPOL/ISM Code 等
    chapter TEXT,
    part TEXT,
    regulation TEXT,
    paragraph TEXT,
    body_text TEXT,
    page_type TEXT,            -- index/content/footnote/collection
    version TEXT,
    parent_doc_id TEXT,        -- 父页面doc_id (替代Neo4j的CONTAINS关系)

    -- PostgreSQL 全文检索向量 (替代Elasticsearch)
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(regulation, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(breadcrumb, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(body_text, '')), 'C')
    ) STORED,

    created_at TIMESTAMP DEFAULT NOW()
);

-- 全文检索GIN索引
CREATE INDEX IF NOT EXISTS idx_regulations_search ON regulations USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_regulations_document ON regulations (document);
CREATE INDEX IF NOT EXISTS idx_regulations_collection ON regulations (collection);
CREATE INDEX IF NOT EXISTS idx_regulations_parent ON regulations (parent_doc_id);

-- ==========================================
-- 2. Chunk表
-- ==========================================
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES regulations(doc_id),
    url TEXT,
    text TEXT NOT NULL,
    text_for_embedding TEXT NOT NULL,
    metadata JSONB NOT NULL,
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks (doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON chunks USING GIN (metadata);

-- ==========================================
-- 3. 交叉引用关系表 (替代Neo4j的REFERENCES边)
-- ==========================================
CREATE TABLE IF NOT EXISTS cross_references (
    id SERIAL PRIMARY KEY,
    source_doc_id TEXT REFERENCES regulations(doc_id),
    target_doc_id TEXT,        -- 目标可能不在库中
    target_url TEXT,
    anchor_text TEXT,          -- 引用锚文本如 "regulation II-1/3-6"
    context TEXT,              -- 引用上下文(前后文200字符)
    relation_type TEXT DEFAULT 'REFERENCES',
    -- relation_type: REFERENCES / INTERPRETS / AMENDS
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_xref_source ON cross_references (source_doc_id);
CREATE INDEX IF NOT EXISTS idx_xref_target ON cross_references (target_doc_id);
CREATE INDEX IF NOT EXISTS idx_xref_type ON cross_references (relation_type);

-- ==========================================
-- 4. 概念实体表 (替代Neo4j的Concept节点)
-- ==========================================
CREATE TABLE IF NOT EXISTS concepts (
    concept_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT              -- ship_type / equipment / concept
);

CREATE TABLE IF NOT EXISTS regulation_concepts (
    doc_id TEXT REFERENCES regulations(doc_id),
    concept_id TEXT REFERENCES concepts(concept_id),
    PRIMARY KEY (doc_id, concept_id)
);

-- 预插入概念实体
INSERT INTO concepts (concept_id, name, category) VALUES
    ('oil_tanker', 'oil tanker', 'ship_type'),
    ('bulk_carrier', 'bulk carrier', 'ship_type'),
    ('passenger_ship', 'passenger ship', 'ship_type'),
    ('cargo_ship', 'cargo ship', 'ship_type'),
    ('chemical_tanker', 'chemical tanker', 'ship_type'),
    ('gas_carrier', 'gas carrier', 'ship_type'),
    ('container_ship', 'container ship', 'ship_type'),
    ('roro_ship', 'ro-ro ship', 'ship_type'),
    ('fishing_vessel', 'fishing vessel', 'ship_type'),
    ('high_speed_craft', 'high-speed craft', 'ship_type'),
    ('modu', 'MODU', 'ship_type'),
    ('fpso', 'FPSO', 'ship_type'),
    ('offshore_supply', 'offshore supply vessel', 'ship_type'),
    ('fire_safety', 'fire safety', 'concept'),
    ('pollution_prevention', 'pollution prevention', 'concept'),
    ('navigation_safety', 'navigation safety', 'concept'),
    ('life_saving', 'life saving', 'concept'),
    ('stability', 'stability', 'concept'),
    ('machinery', 'machinery', 'concept'),
    ('electrical', 'electrical installations', 'concept'),
    ('security', 'maritime security', 'concept'),
    ('ism_audit', 'ISM audit', 'concept'),
    ('port_state_control', 'port state control', 'concept')
ON CONFLICT DO NOTHING;


## 实现 db/postgres.py

class PostgresDB:
    __init__(database_url): 使用 psycopg2 连接
    init_schema(): 执行 schema.sql
    insert_regulation(parsed_doc): 插入法规记录
    insert_chunk(chunk): 插入chunk记录
    insert_cross_references(doc_id, refs): 批量插入交叉引用
    link_concepts(doc_id, body_text): 扫描body_text，自动关联匹配的概念实体
    batch_insert_regulations(docs, batch_size=500): 批量插入
    batch_insert_chunks(chunks, batch_size=500): 批量插入


## 实现 db/bm25_search.py (替代Elasticsearch)

class BM25Search:
    __init__(database_url)

    search(query, top_k=10, document_filter=None) → List[Dict]:
        使用 PostgreSQL ts_rank_cd + plainto_tsquery 实现BM25风格搜索

        SQL模板:
        SELECT doc_id, title, breadcrumb, url,
               ts_rank_cd(search_vector, query, 32) as score
        FROM regulations
        WHERE search_vector @@ plainto_tsquery('english', $1)
          AND ($2::text IS NULL OR document = $2)
        ORDER BY score DESC
        LIMIT $3

    search_by_regulation_number(reg_number) → 精确匹配法规编号
        WHERE regulation ILIKE '%{reg_number}%'
          OR breadcrumb ILIKE '%{reg_number}%'


## 实现 db/graph_queries.py (替代Neo4j)

class GraphQueries:
    __init__(database_url)

    get_children(doc_id) → 获取子页面
    get_parent_chain(doc_id) → 递归获取所有父级直到根
        使用 WITH RECURSIVE CTE:
        WITH RECURSIVE ancestors AS (
            SELECT doc_id, parent_doc_id, title, breadcrumb, 0 as depth
            FROM regulations WHERE doc_id = $1
            UNION ALL
            SELECT r.doc_id, r.parent_doc_id, r.title, r.breadcrumb, a.depth + 1
            FROM regulations r JOIN ancestors a ON r.doc_id = a.parent_doc_id
        ) SELECT * FROM ancestors ORDER BY depth DESC

    get_interpretations(doc_id) → 找到解释该法规的通函
        SELECT * FROM cross_references
        WHERE target_doc_id = $1 AND relation_type = 'INTERPRETS'

    get_amendments(doc_id) → 找到修订该法规的决议
    get_related_by_concept(concept_name) → 找到涉及某概念的所有法规
    get_cross_document_regulations(doc_id) → 找到被引用和引用的文档


## 实现 pipeline/ingest.py

完整入库管线:
1. 读取 data/parsed/regulations.jsonl
2. 初始化PostgreSQL schema
3. 批量插入regulations表
4. 插入cross_references
5. 自动关联concepts
6. 读取 data/chunks/chunks.jsonl
7. 批量插入chunks表
8. 连接Qdrant Cloud (BV-RAG集群)，创建collection:
   - collection_name = "imo_regulations"
   - vector_size = 1024 (降维!)
   - distance = Cosine
   - quantization = ScalarQuantization(INT8, always_ram=True)  (省内存!)
9. 批量生成embeddings (OpenAI text-embedding-3-large, dimensions=1024)
   - batch_size = 100
   - 每个chunk使用 text_for_embedding 生成embedding
10. 批量上传到Qdrant (payload包含chunk的所有metadata)
11. 创建Qdrant payload索引: collection, document, chapter, regulation_number
12. 打印统计: PG行数、Qdrant点数、耗时、预估embedding成本

命令: python -m pipeline.ingest
```

---

## Phase 5: 混合检索

### Claude Code 指令:

```
实现三路混合检索系统。

## 实现 retrieval/query_router.py

class QueryRouter:
    分析用户查询，决定最佳检索策略。

    route(query) → {"strategy": str, "entities": dict}

    策略判断规则:
    1. 检测精确法规编号 (正则):
       r'(SOLAS|MARPOL|STCW|COLREG|ISM|ISPS)\s*(regulation|chapter|annex|rule|part|section)\s*[IVXLC\d\-\/\.]+'
       → strategy = "keyword"  (BM25优先)

    2. 检测关系型查询 (关键词):
       ['哪些', '所有', 'all related', 'which', '修改', 'amend', '解释', 'interpret', '引用', 'reference', '适用于', 'apply to']
       → strategy = "hybrid"  (三路全开)

    3. 其他
       → strategy = "hybrid"  (默认混合)

    4. 从查询中提取实体:
       - document_filter: 识别出的公约/规则名 (SOLAS/MARPOL等)
       - concept: 识别出的概念 (fire safety/bulk carrier等)


## 实现 retrieval/vector_store.py

class VectorStore:
    __init__(qdrant_url, qdrant_api_key, openai_api_key)
    使用 qdrant_client.QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    search(query_text, top_k=10, document_filter=None, collection_filter=None):
        1. 调用 OpenAI embedding API: model="text-embedding-3-large", dimensions=1024
        2. 在Qdrant中搜索，支持metadata过滤:
           - document_filter → FieldCondition(key="document", match=MatchValue(...))
           - collection_filter → FieldCondition(key="collection", match=MatchValue(...))
        3. 返回 [{chunk_id, text, score, metadata}]


## 实现 retrieval/hybrid_retriever.py

class HybridRetriever:
    __init__(vector_store, bm25_search, graph_queries)

    retrieve(query, top_k=10, strategy="auto"):

        1. 如果strategy="auto", 调用QueryRouter判断
        2. 根据策略执行检索:
           - "keyword": 只用BM25
           - "semantic": 只用向量
           - "hybrid": 三路全开

        3. 向量检索: vector_store.search(query, top_k=top_k*2)
        4. BM25检索: bm25_search.search(query, top_k=top_k*2)
        5. 图谱检索:
           - 如果路由识别出concept → graph_queries.get_related_by_concept(concept)
           - 如果路由识别出具体法规 → graph_queries.get_interpretations(doc_id) + get_amendments(doc_id)

        6. RRF融合 (Reciprocal Rank Fusion):
           对每个来源的结果，按原始分数排序后计算:
           rrf_score = Σ 1/(k + rank)  其中 k=60

        7. 按rrf_score降序排列，取top_k

        8. 上下文扩展:
           对top结果，查询图谱补充父级面包屑路径和是否有统一解释

        9. 返回 [{chunk_id, text, score, fused_score, metadata, graph_context}]
```

---

## Phase 6: 答案生成

### Claude Code 指令:

```
实现 LLM 答案生成层。

## 实现 generation/prompts.py

SYSTEM_PROMPT = """你是一个专业的海事法规助手，专门服务于验船师(marine surveyors)。
你的知识来源是 imorules.com (Classification Society Rulefinder 2024) 上的IMO法规全文。

## 回答规则

1. **必须引用具体法规条文**，格式: [SOLAS II-1/3-6.2.3]
   - 每个事实性陈述都要有引用
   - 引用条文时使用 blockquote 引述原文

2. **按层级组织回答**:
   - 主要要求（公约强制条款，"shall"）
   - 配套规则和标准
   - 统一解释（Unified Interpretations / Circulars）
   - 适用指南

3. **明确区分**:
   - 强制要求 (shall) vs 建议 (should) vs 指南

4. **对适用性问题，必须说明**:
   - 适用船型 + 吨位门槛
   - 适用日期（新建船/现有船）
   - 豁免或等效条件

5. **对数值问题（验船师最常问的）**:
   - 直接给出数字，加粗显示
   - 注明单位和测量条件
   - 引用精确条款

6. **语言**: 与用户相同。用户中文则中文回答，但法规引用和术语保留英文。

7. **如果检索内容不足以回答**: 明确说明哪些部分有依据、哪些需要查证。

## 回答末尾

附 "参考来源" 列表:
- [SOLAS II-1/3-6] Access to and Within Spaces... → https://www.imorules.com/GUID-xxx.html
"""


## 实现 generation/generator.py

class AnswerGenerator:
    __init__(anthropic_api_key, primary_model, fast_model)
    使用 anthropic.Anthropic(api_key=...)

    generate(query, retrieved_chunks, conversation_history=None, user_context=None):

        1. 选择模型:
           - 如果查询包含精确法规编号且检索结果score > 0.8 → fast_model (Haiku)
           - 否则 → primary_model (Sonnet)

        2. 组装上下文:
           - 按document分组检索结果
           - 每个chunk显示: **[面包屑路径]** (Source: URL)\n内容
           - 如有graph_context，追加"相关统一解释"和"修订历史"

        3. 构建messages:
           - 如有conversation_history: 加入最近6条消息
           - 如有user_context: 在system prompt末尾附加用户偏好
           - 当前查询 + 检索上下文

        4. 调用 Anthropic API:
           model=选定模型, max_tokens=4096, system=SYSTEM_PROMPT

        5. 后处理:
           - 提取引用: 正则 r'\[(SOLAS|MARPOL|MSC|MEPC|ISM|ISPS|Resolution|LSA|FSS)[^\]]*\]'
           - 评估置信度: 基于top检索分数 (>0.85=high, >0.6=medium, else low)

        6. 返回:
           {
               "answer": 答案文本,
               "citations": [{citation, verified}],
               "confidence": "high/medium/low",
               "model_used": 模型名,
               "sources": [{chunk_id, url, breadcrumb, score}],
           }
```

---

## Phase 7: 语音服务

### Claude Code 指令:

```
实现语音转文字和文字转语音服务。

## 实现 voice/stt_service.py

class STTService:
    __init__(openai_api_key, model="gpt-4o-mini-transcribe")

    async transcribe(audio_data: bytes, audio_format="webm", language=None) → dict:
        1. 构建文件对象: io.BytesIO(audio_data), name=f"audio.{audio_format}"
        2. 调用 openai.audio.transcriptions.create(model=self.model, file=audio_file, language=language)
        3. 如果失败，回退到 whisper-1
        4. 返回 {"text": str, "language": str, "model_used": str, "latency_ms": int}

    注意:
    - 支持格式: webm(浏览器默认), mp3, wav, m4a
    - language参数可选: None=自动, "zh"=中文, "en"=英文
    - 验船师可能中英文混杂，默认自动检测


## 实现 voice/tts_service.py

class TTSService:
    __init__(openai_api_key, model="gpt-4o-mini-tts", voice="ash")

    MARITIME_INSTRUCTIONS = (
        "Speak clearly and at a moderate pace. "
        "When reading regulation numbers like 'II-1/3-6' or 'SOLAS Chapter XII', "
        "pronounce each part distinctly with a brief pause between segments. "
        "Emphasize numerical values such as dimensions, tonnage, and dates. "
        "Maintain a professional, authoritative tone."
    )

    synthesize(text, output_format="mp3") → bytes:
        调用 openai.audio.speech.create(
            model=self.model, voice=self.voice, input=text,
            instructions=self.MARITIME_INSTRUCTIONS,
            response_format=output_format,
        )
        返回 response.content

    synthesize_stream(text, output_format="mp3") → Generator[bytes]:
        同上但流式: response.iter_bytes(chunk_size=4096)

    prepare_tts_text(answer: str, max_length=1500) → str:
        为TTS优化文本:
        - 移除 Markdown (** ## > 等)
        - 移除 URL
        - 简化引用标记 [SOLAS II-1/3-6] → SOLAS II-1/3-6
        - 移除末尾 "参考来源" 部分
        - 截断超长文本（在句号处截断）
```

---

## Phase 8: 上下文记忆

### Claude Code 指令:

```
实现基于Redis的上下文记忆系统。

## 实现 memory/conversation_memory.py

数据结构:
- 会话存储: Redis key = "session:{session_id}", TTL = 24小时
- 用户画像: Redis key = "user_profile:{user_id}", 永久存储

class ConversationTurn (dataclass):
    turn_id: str
    role: str              # "user" / "assistant"
    content: str
    timestamp: float
    input_mode: str        # "voice" / "text"
    metadata: dict         # 可含 retrieved_regulations, confidence 等

class SessionContext (dataclass):
    session_id: str
    user_id: str
    turns: list[ConversationTurn]
    active_regulations: list[str]    # 当前对话涉及的法规编号
    active_topics: list[str]
    active_ship_type: str | None


class ConversationMemory:
    __init__(redis_url, anthropic_api_key, max_turns=10, session_ttl_hours=24)

    create_session(user_id) → SessionContext
    get_session(session_id) → SessionContext | None
    add_turn(session, role, content, input_mode, metadata) → SessionContext

    build_llm_context(session, current_query) → (messages: list, enhanced_query: str):
        核心方法:

        1. 取最近 max_turns*2 条消息作为history

        2. 如果总轮次超过阈值，对早期对话用 Claude Haiku 生成摘要:
           "Summarize this maritime regulation Q&A in 2-3 sentences,
            preserving regulation references and topics"

        3. 指代消解 (关键功能):
           检测指代词: ['这个','那个','该','它','上面','之前','this','that','it','the above','same']
           如果检测到且 active_regulations 非空:
             调用 Claude Haiku:
             "Given context: active_regulations=[...], last 3 exchanges=[...]
              Rewrite query '{query}' to be self-contained.
              Return ONLY the rewritten query."
           例: "这个规定适用于FPSO吗？" → "SOLAS Regulation II-1/3-6适用于FPSO吗？"

        4. 返回 (messages列表, 增强后的query)

    update_user_profile(user_id, session):
        统计常查法规、常见船型、总查询次数

    get_user_context(user_id) → str:
        返回用户画像摘要，注入system prompt
        例: "用户常查法规: SOLAS II-1/3-6(15次), MARPOL Annex VI/14(8次)"
```

---

## Phase 9: 端到端管线与API

### Claude Code 指令:

```
整合所有组件，实现端到端管线和API。

## 实现 pipeline/voice_qa_pipeline.py

class VoiceQAPipeline:
    __init__(stt, tts, memory, retriever, generator)

    async process_voice_query(audio_data, session_id, audio_format="webm"):
        计时每步:
        1. STT: audio → text                          (timing.stt_ms)
        2. Memory: 获取session + 指代消解              (timing.memory_ms)
        3. Retrieval: 混合检索 enhanced_query          (timing.retrieval_ms)
        4. Generation: Claude 生成答案                 (timing.generation_ms)
        5. TTS: 答案文本 → prepare_tts_text → 语音    (timing.tts_ms)
        6. 更新会话记忆

        返回 {session_id, transcription, enhanced_query, answer_text,
               answer_audio(bytes), citations, sources, confidence, timing}

    async process_text_query(text, session_id, generate_audio=True):
        跳过STT，其余同上


## 实现 api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # 启动时初始化所有服务
    from config.settings import settings
    app.state.stt = STTService(settings.openai_api_key, settings.stt_model)
    app.state.tts = TTSService(settings.openai_api_key, settings.tts_model, settings.tts_voice)
    app.state.memory = ConversationMemory(settings.redis_url, settings.anthropic_api_key)
    app.state.vector_store = VectorStore(settings.qdrant_url, settings.qdrant_api_key, settings.openai_api_key)
    app.state.bm25 = BM25Search(settings.database_url)
    app.state.graph = GraphQueries(settings.database_url)
    app.state.retriever = HybridRetriever(app.state.vector_store, app.state.bm25, app.state.graph)
    app.state.generator = AnswerGenerator(settings.anthropic_api_key, settings.llm_model_primary, settings.llm_model_fast)
    app.state.pipeline = VoiceQAPipeline(
        app.state.stt, app.state.tts, app.state.memory,
        app.state.retriever, app.state.generator
    )
    yield
    # 关闭连接

app = FastAPI(title="BV-RAG Maritime Regulations", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "bv-rag"}


## 实现 api/routes/voice.py

POST /api/v1/voice/query
    接收: audio文件(UploadFile) + session_id(Form, 可选) + language(Form, 可选)
    调用: pipeline.process_voice_query()
    返回: {session_id, transcription, answer_text, answer_audio_base64(mp3), citations, confidence, timing}

POST /api/v1/voice/text-query
    接收: text(Form) + session_id(Form, 可选) + generate_audio(Form, 默认true)
    调用: pipeline.process_text_query()
    返回: 同上

WebSocket /api/v1/voice/ws/{session_id}
    接收 JSON: {"type": "audio", "audio": "base64..."} 或 {"type": "text", "text": "..."}
    发送 JSON: {"type": "response", "answer_text": ..., "answer_audio_base64": ..., ...}


## 实现 api/routes/search.py

POST /api/v1/search
    接收: {"query": str, "top_k": int, "document_filter": str|null}
    纯检索，返回 [{chunk_id, text, score, metadata}]

GET /api/v1/regulation/{doc_id}
    查看单条法规: 从PostgreSQL返回完整记录 + 交叉引用 + 子页面


## 实现 api/routes/admin.py

GET /api/v1/admin/stats
    返回: {total_regulations, total_chunks, qdrant_points, redis_sessions}

POST /api/v1/admin/reindex
    触发重新embedding和索引（谨慎使用）


## 实现 scripts/seed_data.py

初始化数据库:
1. 连接PostgreSQL
2. 执行 db/schema.sql
3. 打印"Schema initialized"
命令: python -m scripts.seed_data
```

---

## Phase 10: 前端界面

### Claude Code 指令:

```
创建移动优先的语音问答前端界面。

## 技术: 单个 HTML 文件 (内联 CSS + JS，可直接serve)

保存为 static/index.html，由 FastAPI 的 StaticFiles 提供。

## 界面设计

深蓝色海事主题配色 (#0a1628 背景, #1e3a5f 卡片, #3b82f6 主按钮)

布局 (从上到下):
┌────────────────────────────┐
│  ⚓ BV-RAG                 │  标题栏，深蓝背景
│  Maritime Regulation AI     │
├────────────────────────────┤
│                            │
│  对话气泡区域              │  可滚动
│  ┌──────────────────────┐  │
│  │ 🎤 用户语音消息       │  │  右侧，蓝色气泡
│  └──────────────────────┘  │
│  ┌──────────────────────┐  │
│  │ 🤖 AI回答            │  │  左侧，深灰气泡
│  │ 法规引用高亮          │  │  引用[SOLAS...]可点击
│  │ 🔊 播放语音 ▶️       │  │  内嵌播放按钮
│  │ 置信度: ●●●○ High    │  │
│  │ ⏱️ 3.2s              │  │
│  └──────────────────────┘  │
│                            │
├────────────────────────────┤
│  ┌──────────────────────┐  │  输入区域
│  │ 输入你的问题...     🎤│  │  文字框 + 录音按钮
│  └──────────────────────┘  │
│  [按住说话] 大按钮         │  按住录音，松开发送
└────────────────────────────┘

## 核心功能

1. 录音:
   - 使用 MediaRecorder API
   - mimeType: "audio/webm;codecs=opus"
   - 按住 "按住说话" 按钮开始录音
   - 松开后自动发送到 POST /api/v1/voice/query
   - 录音时显示红色脉动动画

2. 文字输入:
   - 回车或点击发送图标
   - 发送到 POST /api/v1/voice/text-query

3. 回答展示:
   - Markdown渲染（简单的bold/heading/blockquote/list）
   - 法规引用 [SOLAS ...] 高亮为蓝色可点击链接
     点击跳转: https://www.imorules.com/ + 从sources中找对应URL
   - 内嵌音频播放器: 将base64 mp3转为Blob URL, <audio>标签播放
   - 自动播放回答语音

4. 会话管理:
   - 页面加载时生成 session_id (随机UUID)
   - 每次请求携带 session_id
   - 支持连续对话（上下文记忆由后端处理）

5. 状态指示:
   - 录音中: 红色脉动 + "正在录音..."
   - 处理中: 蓝色loading动画 + "正在查询法规..."
   - 每条回答显示耗时 timing.total_ms

6. 响应式:
   - 移动端全宽
   - 桌面端最大宽度 768px 居中

7. PWA (可选):
   - 添加 manifest.json
   - 支持添加到手机主屏幕

注意: 前端通过相对路径 /api/v1/... 调用API（同域，无跨域问题）。
将 static/ 目录挂载到 FastAPI:
app.mount("/", StaticFiles(directory="static", html=True), name="static")
注意API路由必须在StaticFiles之前注册。
```

---

## Phase 11: Railway部署

### Claude Code 指令:

```
配置 Railway 部署。

## Railway 项目设置步骤 (手动在 Railway Dashboard 操作):

1. 创建新项目: railway.com/new
2. 添加 Redis: Ctrl+K → 输入 "Redis" → 选择官方模板
3. 添加 PostgreSQL: Ctrl+K → 输入 "PostgreSQL" → 选择官方模板
4. 添加 App Service: 从 GitHub repo 部署 (连接你的 bv-rag repo)
5. 配置环境变量 (在App Service的Variables标签):
   - 手动添加: OPENAI_API_KEY, ANTHROPIC_API_KEY, QDRANT_URL, QDRANT_API_KEY
   - 引用Railway服务: DATABASE_URL = ${{Postgres.DATABASE_URL}}
   - 引用Railway服务: REDIS_URL = ${{Redis.REDIS_URL}}
   - 其余变量按 .env.example 添加

## 确保以下文件正确:

### Dockerfile (已在Phase 0创建)

### railway.toml (已在Phase 0创建)

### 数据入库流程

数据入库(爬取+解析+分块+indexing)在本地执行，不在Railway上运行:

本地执行顺序:
1. python -m crawler.run_crawler            # 爬取 → data/raw/pages.jsonl
2. python -m parser.html_parser             # 解析 → data/parsed/regulations.jsonl
3. python -m chunker.regulation_chunker     # 分块 → data/chunks/chunks.jsonl
4. python -m scripts.seed_data              # 初始化PG schema (连接Railway的PG)
5. python -m pipeline.ingest                # 入库到 Railway PG + Qdrant Cloud

本地运行时需要设置环境变量指向Railway的数据库:
- DATABASE_URL: 从Railway Dashboard → PostgreSQL服务 → Variables → DATABASE_PUBLIC_URL 获取
- REDIS_URL: 从Railway Dashboard → Redis服务 → Variables → REDIS_PUBLIC_URL 获取
- QDRANT_URL 和 QDRANT_API_KEY: 从 Qdrant Cloud Dashboard 获取

### 验证部署

部署后检查:
1. 访问 https://your-app.railway.app/health → {"status": "ok"}
2. 访问 https://your-app.railway.app/ → 前端界面
3. 在前端界面输入 "What is SOLAS?" → 应返回答案
4. 测试语音: 按住说话 → 应识别并返回答案+语音
```

---

## Phase 12: 评估与调优

### Claude Code 指令:

```
实现评估体系。

## 实现 evaluation/test_queries.json

至少20个测试用例，覆盖所有查询类型:

{
  "test_cases": [
    {"id": "exact_01", "category": "exact_reference", "query": "What are the requirements of SOLAS Regulation II-1/3-6?", "expected_document": "SOLAS", "difficulty": "easy"},
    {"id": "exact_02", "category": "exact_reference", "query": "MARPOL Annex VI Regulation 14 sulphur limits?", "expected_document": "MARPOL", "difficulty": "easy"},
    {"id": "number_01", "category": "numerical", "query": "SOLAS对散货船货舱通道开口的最小尺寸是多少？", "expected_document": "SOLAS", "difficulty": "medium"},
    {"id": "number_02", "category": "numerical", "query": "What is the maximum sulphur content allowed under MARPOL?", "expected_document": "MARPOL", "difficulty": "medium"},
    {"id": "semantic_01", "category": "semantic", "query": "What fire safety equipment is required for passenger ships?", "expected_document": "SOLAS", "difficulty": "medium"},
    {"id": "semantic_02", "category": "semantic", "query": "油轮需要什么防污染设备？", "expected_document": "MARPOL", "difficulty": "medium"},
    {"id": "applicability_01", "category": "applicability", "query": "Does SOLAS II-1/3-6 apply to FPSO vessels?", "expected_answer_contains": "not normally", "difficulty": "medium"},
    {"id": "applicability_02", "category": "applicability", "query": "ISM Code applies to which ship types?", "expected_document": "ISM", "difficulty": "medium"},
    {"id": "cross_doc_01", "category": "cross_document", "query": "Which circulars provide unified interpretations for SOLAS Chapter II-1?", "difficulty": "hard"},
    {"id": "cross_doc_02", "category": "cross_document", "query": "MARPOL Annex VI所有相关的统一解释和通函?", "difficulty": "hard"},
    {"id": "relation_01", "category": "relationship", "query": "What resolutions have amended SOLAS Chapter V?", "difficulty": "hard"},
    {"id": "comparison_01", "category": "comparison", "query": "ISM Code和ISPS Code对船舶运营商的要求有什么区别？", "difficulty": "hard"},
    {"id": "context_01", "category": "context_followup", "query_sequence": ["What is SOLAS Regulation II-1/3-6?", "Does this apply to FPSO?"], "difficulty": "medium"},
    {"id": "context_02", "category": "context_followup", "query_sequence": ["MARPOL Annex VI Regulation 14的硫氧化物限制是多少？", "那ECA区域的要求呢？"], "difficulty": "medium"},
    {"id": "voice_01", "category": "voice_natural", "query": "散货船的额外安全要求是啥", "difficulty": "easy"},
    {"id": "voice_02", "category": "voice_natural", "query": "ECDIS的配备要求帮我查查", "difficulty": "easy"},
    {"id": "timeline_01", "category": "temporal", "query": "What SOLAS regulations take effect for ships built after 1 January 2026?", "difficulty": "hard"},
    {"id": "equipment_01", "category": "equipment", "query": "VDR voyage data recorder requirements under SOLAS?", "difficulty": "medium"},
    {"id": "general_01", "category": "general", "query": "What is the purpose of the ISM Code?", "expected_document": "ISM", "difficulty": "easy"},
    {"id": "general_02", "category": "general", "query": "How many annexes does MARPOL have and what do they cover?", "expected_document": "MARPOL", "difficulty": "easy"}
  ]
}


## 实现 evaluation/run_eval.py

对每个测试用例:
1. 调用 pipeline.process_text_query(query, generate_audio=False)
2. 记录: answer, citations, confidence, sources, timing
3. 检查:
   - 是否命中expected_document
   - 是否包含expected_answer_contains
   - citations是否非空
   - timing是否合理(<5s)
4. 对context_followup: 在同一session中按sequence依次查询
5. 输出: 评估报告 (总通过率, 按category分组的通过率, 平均延迟)
```

---

## 执行顺序总览

| 阶段 | 说明 | 预计耗时 | 在哪运行 |
|------|------|---------|---------|
| Phase 0 | 项目初始化 | 0.5天 | 本地 |
| Phase 1 | 全站爬取 | 2-3天(含爬取) | 本地 |
| Phase 2 | HTML解析 | 1天 | 本地 |
| Phase 3 | 智能分块 | 0.5天 | 本地 |
| Phase 4 | 数据库+入库 | 1天 | 本地→远程DB |
| Phase 5 | 混合检索 | 1天 | 本地 |
| Phase 6 | 答案生成 | 1天 | 本地 |
| Phase 7 | 语音服务 | 0.5天 | 本地 |
| Phase 8 | 上下文记忆 | 1天 | 本地 |
| Phase 9 | API整合 | 1天 | 本地 |
| Phase 10 | 前端界面 | 1天 | 本地 |
| Phase 11 | Railway部署 | 0.5天 | Railway |
| Phase 12 | 评估调优 | 2天 | 本地+远程 |
| **总计** | | **~13天** | |

**喂给 Claude Code 的方式**: 按 Phase 0 → Phase 1 → ... 顺序，每次粘贴一个阶段的"Claude Code 指令"部分。每个阶段完成后测试验证，再进入下一阶段。
