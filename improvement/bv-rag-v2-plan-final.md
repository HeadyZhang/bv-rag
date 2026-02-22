# BV-RAG v2 产品开发方案（最终版）

> **从"法规翻译官"进化为"验船师的 Copilot"——不是帮你翻译，是帮你写。**

---

## 一、核心理念转变

### 1.1 v1 方案的根本问题

| v1 思路（翻译） | v2 思路（预测补全） |
|---|---|
| 验船师已经知道要写什么 | 验船师可能还没想好写什么 |
| 需要先写完中文，再选中右键翻译 | 光标进入输入框就自动出建议 |
| 本质是翻译工具 | 本质是智能填表助手 |
| 用户动作：写 → 选 → 右键 → 等 → 粘贴 | 用户动作：看建议 → 点一下 |
| 减少 1 次切窗口 | 减少整个"思考+打字"过程 |

### 1.2 一句话定义

> **"验船师的 GitHub Copilot"** —— 根据船型、检查区域、检查类型等上下文，自动预测缺陷描述并补全标准法规表述。验船师只需点击或微调，不需要从零开始写。

### 1.3 核心用户故事

```
场景 A：零输入预测

验船师在 PSC 检查系统里已填好：
  - 船名: OCEAN STAR
  - 船型: Bulk Carrier
  - 检查类型: Initial Inspection
  - 检查区域: Engine Room

光标点进「缺陷描述」输入框 →
插件自动弹出下拉建议列表：

  1. Piping in engine room found with excessive corrosion/wastage.
     (Ref: SOLAS Reg II-1/3-2.2)
  2. Oily water separator found defective / not operational.
     (Ref: MARPOL Annex I, Reg 14)
  3. Emergency fire pump failed to start on testing.
     (Ref: SOLAS Reg II-2/10.2.1)
  4. Insulation of exhaust pipe in engine room found deteriorated.
     (Ref: SOLAS Reg II-2/4.5)

验船师点击第 2 条 → 直接填入输入框。完成。
```

```
场景 B：输入补全

验船师在「缺陷描述」输入框打了两个字："油水"
→ 建议列表实时过滤为油水分离器相关项：

  1. Oily water separator found defective, unable to maintain 15ppm discharge limit.
     (Ref: MARPOL Annex I, Reg 14)
  2. Oil filtering equipment alarm found defective / bypassed.
     (Ref: MARPOL Annex I, Reg 14.7)
  3. Oil record book Part I — incomplete entries for oily water separator operations.
     (Ref: MARPOL Annex I, Reg 17)

验船师选一个，或继续打字进一步缩小范围。
```

```
场景 C：大白话标准化（兜底）

验船师在输入框里打了一段大白话：
  "机舱里面好几根管子都锈得不行了，有些地方都穿了"

选中 → 右键 → 【验船AI：转标准法规表述】→ 替换为：
  "Multiple piping systems in engine room found with severe corrosion
   and wastage, with localized perforation noted.
   (Ref: SOLAS Reg II-1/3-2.2; Classification Society structural survey requirements)"
```

---

## 二、架构决策：同项目部署（非微服务拆分）

### 2.1 决策结论

**在现有 bv-rag Railway 项目中直接新增 `api/routes/extension.py` 路由，不另建项目。**

### 2.2 核心依据

v2 的 extension 端点是现有能力的"薄壳包装"：

| 端点 | 实际调用 | 需要 LLM？ |
|---|---|---|
| `/predict` | `DefectKnowledgeBase.query()` 查表（80%）；fallback 调 `retriever` + `generator` | 20% 用 Haiku |
| `/complete` | `kb.search_by_keyword()` 本地匹配；不够时调 `retriever` + `generator` | 有时用 Haiku |
| `/fill` | `kb.exact_match()` 快速路径；否则 `retriever` + `generator` | 需要 |
| `/explain` | `retriever.retrieve()` + `generator` | 需要 |
| `/chat` | 直接代理 `pipeline.process_text_query()` | 需要 |
| `/feedback` | 纯 PG insert | 不需要 |

5 个端点中 4 个需要直接访问 `HybridRetriever`、`AnswerGenerator`、`VectorStore`（Qdrant）、`BM25Search`（PG），这些全部已在 `app.state` 中初始化好。

### 2.3 分拆方案（方案 B）的致命问题

| 问题 | 具体影响 |
|---|---|
| 重复连接 | Qdrant Cloud 免费层有连接数限制；PG/Redis 双倍连接池占用内存 |
| 延迟恶化 | predict 目标 <300ms，加一跳 Railway 内网 HTTP 至少 +50-100ms |
| 代码重复 | `HybridRetriever`、`QueryEnhancer`、`AnswerGenerator` 全部要 import 一遍或做成 pip 包 |
| 双倍环境变量 | ANTHROPIC_API_KEY、OPENAI_API_KEY、COHERE_API_KEY、QDRANT_URL、DATABASE_URL、REDIS_URL 全配两份 |
| 双倍部署成本 | Railway 两个 service，基础月费翻倍 |
| Auth 共享 | JWT_SECRET 需要同步，或者做跨服务认证 |

### 2.4 实际改动量

```
现有代码量: 88 个 Python 文件, ~20,860 行
路由文件:   voice.py(191L) + search.py(62L) + admin.py(83L) + auth.py(97L) = 433 行

v2 新增:
├── api/routes/extension.py     ~200 行（6个端点）
├── knowledge/defect_kb.py      ~150 行（知识库查询类）
├── data/defect_kb.json         数据文件（非代码）
├── generation/generator.py     新增 ~80 行（3个新方法）
└── api/main.py                 +3 行（注册路由 + 初始化 KB）

总新增: ~430 行 Python 代码，占现有的 2%
```

### 2.5 项目结构

```
bv-rag/                            # 同一个 Railway 项目 / 同一个 git repo
├── api/
│   ├── main.py                    # 注册 extension_router
│   └── routes/
│       ├── voice.py               # 现有
│       ├── search.py              # 现有
│       ├── admin.py               # 现有
│       ├── auth.py                # 现有
│       └── extension.py           # 【新增】6 个 extension 端点
├── knowledge/
│   ├── defect_kb.py               # 【新增】DefectKnowledgeBase 类
│   └── practical/                 # 现有
├── data/
│   └── defect_kb.json             # 【新增】100 条核心缺陷
├── generation/
│   └── generator.py               # 【修改】新增 3 个方法
├── chrome-extension/              # 【新增】独立子目录
│   ├── manifest.json
│   ├── background.js
│   ├── content.js
│   ├── sidepanel.html
│   ├── sidepanel.js
│   ├── popup.html
│   ├── popup.js
│   ├── styles/
│   │   └── content.css
│   ├── icons/
│   └── lib/
│       ├── api-client.js
│       ├── suggestion-dropdown.js
│       └── defect-cache.js
├── .github/
│   └── workflows/
│       ├── backend-ci.yml         # 【新增】Python 后端 CI
│       └── extension-ci.yml      # 【新增】Chrome 扩展 CI
├── .dockerignore                  # 排除 chrome-extension/
└── ...（其余不变）
```

### 2.6 分拆触发阈值（定量退出条件）

不需要定性争论"该不该拆"，看数字：

| 指标 | 当前预期 | 分拆评估触发线 | 监控方式 |
|---|---|---|---|
| extension `/predict` p95 延迟 | <300ms | >600ms（目标 2x） | Prometheus / 日志统计 |
| extension `/fill` p95 延迟 | <2s | >4s（目标 2x） | 同上 |
| chatbot `/text-query` p95 延迟 | <5s | >10s（因 extension 流量导致） | 同上 |
| 总并发请求数 | <15 | >50 持续 5 分钟 | Railway 监控 |
| 活跃用户数 | 10-20 | >100 | 业务统计 |
| Railway 单实例 CPU | <60% | >85% 持续 10 分钟 | Railway 监控 |

**规则**：当上述任意 2 项持续超过触发线 1 周，启动分拆评估。在此之前，monolith 是正确选择。

### 2.7 CI/CD 策略（Monorepo 双流水线）

同一个 repo 中有 Python 后端 + Chrome 扩展，需要两条独立的 CI pipeline：

**后端 CI（`.github/workflows/backend-ci.yml`）**：

```yaml
name: Backend CI
on:
  push:
    paths:
      - 'api/**'
      - 'generation/**'
      - 'retrieval/**'
      - 'knowledge/**'
      - 'pipeline/**'
      - 'config/**'
      - 'db/**'
      - 'tests/**'
      - 'pyproject.toml'
  pull_request:
    paths:
      - 'api/**'
      - 'generation/**'
      - 'retrieval/**'
      - 'knowledge/**'
      - 'pipeline/**'
      - 'config/**'
      - 'db/**'
      - 'tests/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e ".[test]"
      - run: pytest tests/ -v --tb=short
      - run: python -m py_compile api/main.py  # 语法检查

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install ruff
      - run: ruff check api/ generation/ retrieval/ knowledge/ pipeline/
```

**Chrome 扩展 CI（`.github/workflows/extension-ci.yml`）**：

```yaml
name: Extension CI
on:
  push:
    paths:
      - 'chrome-extension/**'
  pull_request:
    paths:
      - 'chrome-extension/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate manifest.json
        run: |
          python -c "
          import json, sys
          m = json.load(open('chrome-extension/manifest.json'))
          assert m['manifest_version'] == 3, 'Must be Manifest V3'
          assert 'background' in m, 'Missing background service worker'
          assert 'content_scripts' in m, 'Missing content scripts'
          print(f'Manifest valid: {m[\"name\"]} v{m[\"version\"]}')
          "
      - name: Check JS syntax
        run: |
          npx acorn --ecma2020 chrome-extension/background.js
          npx acorn --ecma2020 chrome-extension/content.js
          npx acorn --ecma2020 chrome-extension/lib/api-client.js
          npx acorn --ecma2020 chrome-extension/lib/suggestion-dropdown.js
          npx acorn --ecma2020 chrome-extension/lib/defect-cache.js

  package:
    runs-on: ubuntu-latest
    needs: validate
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Package extension
        run: |
          cd chrome-extension
          zip -r ../bv-extension-${{ github.sha }}.zip . -x "*.DS_Store"
      - uses: actions/upload-artifact@v4
        with:
          name: chrome-extension
          path: bv-extension-*.zip
```

**`.dockerignore` 配置**：

```
chrome-extension/
.github/
*.md
backups/
reports/
improvement/
scripts/audit_*
scripts/diagnose_*
```

Railway 部署只打包 Python 后端代码，Chrome 扩展通过 GitHub Actions artifact 或手动 zip 分发。

---

## 三、产品架构

### 3.1 三层交互模型

| 层级 | 名称 | 触发方式 | 场景 | 延迟目标 |
|---|---|---|---|---|
| **L1** | **预测建议** | 光标进入输入框（focus） | 验船师还没想好写什么 | <300ms（预计算查表） |
| **L2** | **输入补全** | 用户打了几个字（input） | 验船师知道大概方向 | <500ms（本地过滤）+ <1.5s（LLM 深度补全） |
| **L3** | **右键标准化** | 用户写完大白话，选中右键 | 验船师写了但需要标准化 | <2s（RAG + LLM） |

额外兜底：侧边栏 Chatbot —— 当以上三层都不够用、需要深度提问时展开。

### 3.2 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│  Chrome Extension (Manifest V3)                          │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │Content Script │  │ Background   │  │  Side Panel   │  │
│  │              │←→│ Service      │←→│  (Chatbot)    │  │
│  │ - focus 监听  │  │ Worker       │  │  默认折叠      │  │
│  │ - input 监听  │  │              │  │               │  │
│  │ - 右键菜单    │  │ - API 调度    │  │               │  │
│  │ - 建议下拉框  │  │ - 缓存管理    │  │               │  │
│  │ - 文字替换    │  │ - 预计算索引  │  │               │  │
│  └──────────────┘  └──────┬───────┘  └───────────────┘  │
│                           │                              │
└───────────────────────────┼──────────────────────────────┘
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────┐
│  BV-RAG Backend (Railway) — 同一进程                     │
│                                                          │
│  ┌─ KB-Only 路径 (KB_ONLY_SEMAPHORE=10) ─────────────┐  │
│  │  /api/v1/extension/predict  ← L1 预测建议          │  │
│  │  /api/v1/extension/complete ← L2 输入补全(查表路径) │  │
│  │  /api/v1/extension/kb-version ← 版本检查           │  │
│  │  /api/v1/extension/kb-update  ← 增量更新           │  │
│  │  /api/v1/extension/feedback   ← 反馈收集           │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ LLM 路径 (LLM_SEMAPHORE=3) ─────────────────────┐  │
│  │  /api/v1/extension/fill     ← L3 右键标准化        │  │
│  │  /api/v1/extension/explain  ← 划词解释             │  │
│  │  /api/v1/extension/chat     ← 侧边栏对话          │  │
│  │  /api/v1/extension/complete ← L2 补全(LLM fallback)│  │
│  │  /api/v1/voice/text-query   ← 现有 chatbot        │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌───────────────┐ ┌──────────────┐ ┌────────────────┐  │
│  │ DefectKnowled-│ │ Hybrid       │ │ Answer         │  │
│  │ geBase        │ │ Retriever    │ │ Generator      │  │
│  │ (预计算索引)   │ │ (RAG 检索)   │ │ (Claude LLM)   │  │
│  └───────┬───────┘ └──────┬───────┘ └────────┬───────┘  │
│          │                │                   │          │
│  ┌───────┴───────┐ ┌──────┴───────┐ ┌────────┴───────┐  │
│  │ defect_kb.json│ │Qdrant+PG     │ │Anthropic API   │  │
│  │ + 用户反馈池  │ │+Graph        │ │(Haiku/Sonnet)  │  │
│  └───────────────┘ └──────────────┘ └────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 3.3 并发隔离模型（按资源消耗分层）

查表请求和 LLM 请求的资源消耗差 100 倍以上，不能混用同一个信号量：

```python
import asyncio

# ── 两级信号量：按"是否调 LLM"隔离 ──

# 查表路径：predict/complete 的 80% 走这条，纯内存操作 <50ms
# 高并发无压力，不占 LLM 资源
KB_ONLY_SEMAPHORE = asyncio.Semaphore(10)

# LLM 路径：fill/explain/chat + complete 的 20% fallback
# 受 Anthropic API 并发限制，需要严格控制
LLM_SEMAPHORE = asyncio.Semaphore(3)

# 现有 chatbot 也走 LLM_SEMAPHORE，共享同一个池
# 这样 chatbot 和 extension 的 LLM 调用互相感知，不会超载
```

**为什么这样分**：

| 信号量 | 保护的资源 | 并发槽 | 典型延迟 | 使用者 |
|---|---|---|---|---|
| `KB_ONLY_SEMAPHORE` | CPU + 内存（JSON 查表） | 10 | <50ms | predict、complete(查表路径)、kb-version、kb-update、feedback |
| `LLM_SEMAPHORE` | Anthropic API 并发 + Qdrant 连接 | 3 | 1-5s | fill、explain、chat、complete(LLM fallback)、现有 text-query |

**关键保证**：predict 的 <300ms 永远不会被 LLM 请求阻塞。即使 3 个 LLM 槽全部占满，predict 仍然可以在 KB_ONLY_SEMAPHORE 下正常返回。

### 3.4 Chrome 扩展目录结构

```
chrome-extension/
├── manifest.json              # Manifest V3
├── background.js              # Service Worker（API调度、缓存管理、预计算索引）
├── content.js                 # Content Script（DOM交互、focus/input监听、建议下拉框）
├── sidepanel.html             # Side Panel UI（Chatbot 兜底）
├── sidepanel.js               # Side Panel 逻辑
├── popup.html                 # Popup（登录 + 设置）
├── popup.js                   # Popup 逻辑
├── styles/
│   └── content.css            # 建议下拉框样式、loading、toast
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── lib/
    ├── api-client.js          # 封装后端通信
    ├── suggestion-dropdown.js # 建议下拉框组件
    └── defect-cache.js        # 本地缓存管理
```

### 3.5 Manifest V3 配置

```json
{
  "manifest_version": 3,
  "name": "BV Maritime Regulation Assistant",
  "version": "0.2.0",
  "description": "验船师的智能填表助手——自动预测缺陷描述，一键填入标准法规表述",
  "permissions": [
    "contextMenus",
    "activeTab",
    "sidePanel",
    "storage"
  ],
  "host_permissions": [
    "https://your-railway-domain.up.railway.app/*"
  ],
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [{
    "matches": ["<all_urls>"],
    "js": ["lib/suggestion-dropdown.js", "content.js"],
    "css": ["styles/content.css"]
  }],
  "side_panel": {
    "default_path": "sidepanel.html"
  },
  "action": {
    "default_popup": "popup.html",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  }
}
```

---

## 四、缺陷知识库设计（核心竞争力）

### 4.1 知识库概述

这是整个系统的"快速大脑"。不调 LLM，直接查表返回结果，保证 <300ms 响应。

### 4.2 数据结构

```json
{
  "version": "1.0.0",
  "updated_at": "2026-02-20",
  "defects": [
    {
      "id": "DEF-001",
      "category": "structural",
      "subcategory": "corrosion",
      "chinese_triggers": ["锈蚀", "腐蚀", "锈穿", "锈烂", "管子锈了", "管路腐蚀"],
      "standard_text_en": "Piping in engine room found with excessive corrosion and wastage.",
      "standard_text_zh": "机舱管路发现严重锈蚀及减薄。",
      "regulation_refs": [
        {
          "convention": "SOLAS",
          "ref": "Reg II-1/3-2.2",
          "full_text": "Corrosion prevention of seawater ballast tanks and cargo oil tanks"
        }
      ],
      "applicable_ship_types": ["all"],
      "applicable_areas": ["engine_room", "cargo_hold", "ballast_tank"],
      "applicable_inspections": ["PSC", "FSI", "annual_survey"],
      "detention_risk": "high",
      "frequency_rank": 3,
      "paris_mou_code": "01110",
      "tokyo_mou_code": "0115",
      "variants": [
        {
          "condition": "with perforation",
          "text_en": "Piping in engine room found with severe corrosion and wastage, with localized perforation noted.",
          "text_zh": "机舱管路发现严重锈蚀及减薄，局部已穿孔。",
          "additional_refs": ["Classification Society structural survey requirements"]
        },
        {
          "condition": "temporary repair",
          "text_en": "Piping in engine room found with temporary/cement box repair on corroded section, permanent repair required.",
          "text_zh": "机舱管路锈蚀部位使用临时/水泥箱修复，需进行永久性修理。",
          "additional_refs": ["SOLAS Reg II-1/3-2.2", "Class requirements"]
        }
      ]
    },
    {
      "id": "DEF-002",
      "category": "fire_safety",
      "subcategory": "fire_extinguisher",
      "chinese_triggers": ["灭火器", "灭火器过期", "灭火器压力不足", "灭火器缺失"],
      "standard_text_en": "Portable fire extinguisher(s) found expired / not maintained as required.",
      "standard_text_zh": "手提式灭火器超过检验有效期/未按要求维护保养。",
      "regulation_refs": [
        {
          "convention": "SOLAS",
          "ref": "Reg II-2/10.3",
          "full_text": "Portable fire extinguishers"
        },
        {
          "convention": "FSS Code",
          "ref": "Chapter 4",
          "full_text": "Fire extinguishers"
        }
      ],
      "applicable_ship_types": ["all"],
      "applicable_areas": ["engine_room", "bridge", "accommodation", "deck"],
      "applicable_inspections": ["PSC", "FSI", "safety_equipment_survey"],
      "detention_risk": "medium",
      "frequency_rank": 7,
      "variants": [
        {
          "condition": "missing",
          "text_en": "Required portable fire extinguisher(s) found missing from designated location.",
          "text_zh": "指定位置的手提式灭火器缺失。"
        },
        {
          "condition": "pressure low",
          "text_en": "Portable fire extinguisher(s) found with pressure gauge indicating discharge / low pressure.",
          "text_zh": "手提式灭火器压力表显示已释放/压力不足。"
        }
      ]
    }
  ],

  "index": {
    "by_area": {
      "engine_room": ["DEF-001", "DEF-003", "DEF-005", "DEF-008", "DEF-012"],
      "bridge": ["DEF-015", "DEF-016", "DEF-017", "DEF-021"],
      "deck": ["DEF-002", "DEF-025", "DEF-030"],
      "cargo_hold": ["DEF-001", "DEF-040", "DEF-041"],
      "accommodation": ["DEF-002", "DEF-050"],
      "life_saving": ["DEF-060", "DEF-061", "DEF-062", "DEF-063"]
    },
    "by_ship_type": {
      "bulk_carrier": ["DEF-001", "DEF-040", "DEF-041"],
      "oil_tanker": ["DEF-070", "DEF-071", "DEF-072"],
      "container_ship": ["DEF-080", "DEF-081"],
      "general_cargo": ["DEF-001", "DEF-090"]
    },
    "by_category": {
      "structural": ["DEF-001", "DEF-040", "DEF-041"],
      "fire_safety": ["DEF-002", "DEF-003", "DEF-004"],
      "life_saving": ["DEF-060", "DEF-061", "DEF-062"],
      "navigation": ["DEF-015", "DEF-016", "DEF-017"],
      "pollution_prevention": ["DEF-070", "DEF-071"],
      "crew_certification": ["DEF-100", "DEF-101"],
      "ism_code": ["DEF-110", "DEF-111"],
      "isps_code": ["DEF-120", "DEF-121"]
    },
    "chinese_keyword_map": {
      "锈蚀": ["DEF-001"],
      "腐蚀": ["DEF-001"],
      "灭火器": ["DEF-002"],
      "油水分离器": ["DEF-003"],
      "救生筏": ["DEF-060"],
      "救生艇": ["DEF-061"],
      "海图": ["DEF-015"],
      "磁罗经": ["DEF-016"],
      "消防水带": ["DEF-004"],
      "应急舵": ["DEF-017"]
    }
  }
}
```

### 4.3 数据来源与构建策略

| 数据来源 | 内容 | 获取方式 | 预估条目 |
|---|---|---|---|
| **Paris MOU 年度报告** | PSC 高频缺陷统计、滞留原因 Top 20 | 公开 PDF，手动提取 + LLM 辅助结构化 | 50-80 条 |
| **Tokyo MOU 年度报告** | 亚太区 PSC 缺陷统计 | 公开 PDF | 50-80 条 |
| **USCG PSC 缺陷数据** | 美国海岸警卫队检查数据库 | 公开 Web（可爬取） | 100+ 条 |
| **BV-RAG 已有法规库** | 283K chunks 中的检查要求和 checklist 条目 | 从 Qdrant 中按类目检索提取 | 200+ 条 |
| **验船师反馈** | 用户纠正 / 补充的真实缺陷描述 | `/feedback` API 收集 | 持续增长 |
| **IMO 公约原文** | SOLAS / MARPOL / STCW / MLC / ISM / ISPS 条款 | 已在 RAG 库中 | 法规引用覆盖 |

**Phase 0 目标**：先构建 **100 条核心缺陷**，覆盖 PSC 检查中 80% 的常见场景。

```
Priority 1 (30条): PSC 年度报告 Top 30 滞留原因
Priority 2 (30条): 按检查区域补充（Engine Room / Bridge / Deck / Life Saving 各 ~8 条）
Priority 3 (40条): 按船型补充特殊缺陷（Bulk Carrier / Tanker / Container 各 ~12 条）
```

### 4.4 知识库版本管理与热更新

```python
# 后端提供知识库版本检查和增量更新接口

# GET /api/v1/extension/kb-version
# → {"version": "1.0.3", "updated_at": "2026-02-20", "defect_count": 142}

# GET /api/v1/extension/kb-update?since_version=1.0.1
# → 返回增量更新的 defect 条目（新增 + 修改）

# Chrome Extension 启动时检查版本，增量更新本地缓存
```

---

## 五、功能详细设计

### 5.1 功能一：L1 预测建议（核心 MVP）

**触发条件**：用户光标进入（focus）任何可识别的缺陷描述输入框

**交互流程**：

```
1. 验船师已在表单中填写了上下文字段（船型、检查区域等）
2. 光标点进「缺陷描述」输入框（focus 事件）
3. Content Script 立即采集表单上下文
4. 两路并行：
   a. 本地查表（<100ms）：
      从 defect_cache 中按 (ship_type × area × inspection_type) 索引
      → 返回 Top 5-8 条预计算建议 → 立即显示下拉框
   b. 后端深度预测（<1.5s）（可选，用于补充本地没有的建议）：
      调 /predict API → 返回更多上下文相关建议 → 追加到下拉框
5. 验船师点击某条建议 → 直接填入输入框
6. 或者验船师忽略建议，开始自己打字 → 进入 L2 输入补全模式
```

**建议下拉框 UI**：

```
┌──────────────────────────────────────────────────────┐
│  BV AI Suggestions (Bulk Carrier · Engine Room)       │
│                                                       │
│  > Piping in engine room found with excessive         │
│    corrosion and wastage.                             │
│    SOLAS Reg II-1/3-2.2                      [#3]     │
│  ──────────────────────────────────────────────────── │
│  > Oily water separator found defective /             │
│    not operational.                                   │
│    MARPOL Annex I, Reg 14                    [#5]     │
│  ──────────────────────────────────────────────────── │
│  > Emergency fire pump failed to start on testing.    │
│    SOLAS Reg II-2/10.2.1                     [#8]     │
│  ──────────────────────────────────────────────────── │
│  > Insulation of exhaust pipe deteriorated.           │
│    SOLAS Reg II-2/4.5                        [#12]    │
│                                                       │
│  [显示更多...]  [不需要建议，自己输入]                    │
│  ─────────────────────────────────────────────────── │
│  ↑↓ 导航  Enter 选择  Esc 关闭  输入文字过滤           │
└──────────────────────────────────────────────────────┘
```

**Content Script 上下文采集逻辑**：

```javascript
function getFormContext(element) {
  const context = {
    fieldLabel: '',
    shipType: '',
    shipName: '',
    inspectionType: '',
    inspectionArea: '',
    otherFields: {}
  };

  context.fieldLabel = getFieldLabel(element);

  const form = element.closest('form')
             || element.closest('table')
             || element.closest('[role="form"]');
  if (!form) return context;

  const inputs = form.querySelectorAll('input, select, textarea');
  inputs.forEach(inp => {
    if (inp === element) return;
    const key = getFieldLabel(inp).toLowerCase();
    const val = inp.value?.trim() || '';
    if (!key || !val || val.length > 200) return;

    if (matchesAny(key, ['ship type', '船型', 'vessel type', 'type of ship'])) {
      context.shipType = val;
    } else if (matchesAny(key, ['ship name', '船名', 'vessel name'])) {
      context.shipName = val;
    } else if (matchesAny(key, ['inspection type', '检查类型', 'survey type'])) {
      context.inspectionType = val;
    } else if (matchesAny(key, ['area', '检查区域', 'location', 'space'])) {
      context.inspectionArea = val;
    } else {
      context.otherFields[key.slice(0, 50)] = val.slice(0, 200);
    }
  });

  return context;
}

function getFieldLabel(element) {
  const id = element.id || element.name;
  if (id) {
    const label = document.querySelector(`label[for="${id}"]`);
    if (label) return label.textContent.trim();
  }
  if (element.placeholder) return element.placeholder;
  const parent = element.closest('div, td, th, li, dt');
  if (parent) {
    const textNodes = [...parent.childNodes]
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent.trim())
      .filter(Boolean);
    if (textNodes.length) return textNodes.join(' ').slice(0, 100);
  }
  return '';
}

function matchesAny(text, patterns) {
  const lower = text.toLowerCase();
  return patterns.some(p => lower.includes(p.toLowerCase()));
}
```

**Focus 事件监听与建议触发**：

```javascript
const DEFECT_FIELD_PATTERNS = [
  'defect', 'deficiency', 'finding', 'observation', 'remark',
  'description', '缺陷', '描述', '不符合', '发现'
];

function isDefectField(element) {
  const label = getFieldLabel(element).toLowerCase();
  const name = (element.name || '').toLowerCase();
  const placeholder = (element.placeholder || '').toLowerCase();
  const combined = `${label} ${name} ${placeholder}`;
  return DEFECT_FIELD_PATTERNS.some(p => combined.includes(p));
}

document.addEventListener('focusin', async (e) => {
  const el = e.target;
  if (!isEditableElement(el)) return;
  if (!isDefectField(el)) return;

  const formContext = getFormContext(el);

  // 立即从本地缓存加载建议（<100ms）
  const localSuggestions = await getLocalPredictions(formContext);
  if (localSuggestions.length > 0) {
    showSuggestionDropdown(el, localSuggestions);
  }

  // 同时请求后端深度预测（<1.5s），拿到后追加
  try {
    const remoteSuggestions = await requestPredictions(formContext);
    mergeSuggestions(el, localSuggestions, remoteSuggestions);
  } catch (err) {
    console.warn('Remote prediction failed, using local only:', err.message);
  }
});

function isEditableElement(el) {
  if (el.tagName === 'INPUT' && el.type === 'text') return true;
  if (el.tagName === 'TEXTAREA') return true;
  if (el.isContentEditable) return true;
  return false;
}
```

### 5.2 功能二：L2 输入补全

**触发条件**：用户在缺陷描述输入框中开始打字

```javascript
let debounceTimer = null;
let currentSuggestions = [];

document.addEventListener('input', (e) => {
  const el = e.target;
  if (!isEditableElement(el) || !isDefectField(el)) return;

  const partialInput = el.value.trim();

  // 1. 立即本地过滤（同步，<50ms）
  const filtered = filterSuggestionsLocally(currentSuggestions, partialInput);
  updateSuggestionDropdown(el, filtered);

  // 2. Debounce 300ms 后请求后端补全
  clearTimeout(debounceTimer);
  if (partialInput.length >= 2) {
    debounceTimer = setTimeout(async () => {
      const formContext = getFormContext(el);
      try {
        const completions = await requestCompletion(formContext, partialInput);
        const merged = mergeSuggestions(el, filtered, completions);
        currentSuggestions = merged;
      } catch (err) {
        // 静默失败，保持本地过滤结果
      }
    }, 300);
  }
});

function filterSuggestionsLocally(suggestions, input) {
  if (!input) return suggestions;
  const lower = input.toLowerCase();

  return suggestions
    .map(s => {
      let score = 0;
      if (s.chinese_triggers?.some(t => t.includes(input))) score += 10;
      if (s.text_en.toLowerCase().includes(lower)) score += 5;
      if (s.text_zh?.includes(input)) score += 8;
      if (s.category.toLowerCase().includes(lower)) score += 3;
      return { ...s, matchScore: score };
    })
    .filter(s => s.matchScore > 0)
    .sort((a, b) => b.matchScore - a.matchScore);
}
```

**键盘导航**：

```javascript
document.addEventListener('keydown', (e) => {
  if (!isSuggestionDropdownVisible()) return;

  switch(e.key) {
    case 'ArrowDown':
      e.preventDefault();
      highlightNextSuggestion();
      break;
    case 'ArrowUp':
      e.preventDefault();
      highlightPrevSuggestion();
      break;
    case 'Enter':
      if (getHighlightedSuggestion()) {
        e.preventDefault();
        selectHighlightedSuggestion();
      }
      break;
    case 'Escape':
      hideSuggestionDropdown();
      break;
    case 'Tab':
      if (getHighlightedSuggestion()) {
        e.preventDefault();
        selectHighlightedSuggestion();
      }
      break;
  }
});
```

### 5.3 功能三：L3 右键标准化

**触发条件**：用户在输入框中写了中文大白话，选中后右键

```javascript
// background.js — 右键菜单

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'bv-fill-en',
    title: '验船AI：转标准英文法规表述',
    contexts: ['selection']
  });
  chrome.contextMenus.create({
    id: 'bv-fill-zh',
    title: '验船AI：转标准中文法规表述',
    contexts: ['selection']
  });
  chrome.contextMenus.create({
    id: 'bv-explain',
    title: '验船AI：用中文解释这段法规',
    contexts: ['selection']
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'bv-fill-en') {
    chrome.tabs.sendMessage(tab.id, {
      type: 'FILL_REQUEST',
      selectedText: info.selectionText,
      targetLang: 'en'
    });
  } else if (info.menuItemId === 'bv-fill-zh') {
    chrome.tabs.sendMessage(tab.id, {
      type: 'FILL_REQUEST',
      selectedText: info.selectionText,
      targetLang: 'zh'
    });
  } else if (info.menuItemId === 'bv-explain') {
    chrome.tabs.sendMessage(tab.id, {
      type: 'EXPLAIN_REQUEST',
      selectedText: info.selectionText
    });
  }
});
```

### 5.4 功能四：用户反馈闭环（MVP 必须有）

每次自动填入完成后弹出反馈气泡：

```
┌──────────────────────────┐
│ > 已填入                  │
│ [准确] [不准确] [撤销]     │
└──────────────────────────┘
```

点击 [不准确] 展开纠正文本框，提交后存入 `extension_feedback` 表。

### 5.5 功能五：侧边栏 Chatbot（兜底）

默认折叠，当 L1/L2/L3 都不够用时手动展开。复用现有 BV-RAG 对话能力。

### 5.6 功能六：划词解释

在任何网页上选中英文法规文本 → 右键 → Side Panel 展示中文解释。

---

## 六、后端 API 设计

### 6.1 API 端点总览

| 端点 | 方法 | 信号量 | 模型 | 延迟目标 |
|---|---|---|---|---|
| `/api/v1/extension/predict` | POST | `KB_ONLY` (查表) / `LLM` (fallback) | 无 / Haiku | <300ms / <1.5s |
| `/api/v1/extension/complete` | POST | `KB_ONLY` (查表) / `LLM` (fallback) | 无 / Haiku | <500ms / <1.5s |
| `/api/v1/extension/fill` | POST | `LLM` | Haiku / Sonnet | <2s |
| `/api/v1/extension/explain` | POST | `LLM` | Haiku | <2s |
| `/api/v1/extension/chat` | POST | `LLM` | Smart Routing | 首 token <1s |
| `/api/v1/extension/feedback` | POST | `KB_ONLY` | 无 | <200ms |
| `/api/v1/extension/kb-version` | GET | 无 | 无 | <100ms |
| `/api/v1/extension/kb-update` | GET | `KB_ONLY` | 无 | <500ms |

### 6.2 信号量实现

```python
# api/routes/extension.py

import asyncio

KB_ONLY_SEMAPHORE = asyncio.Semaphore(10)   # 查表路径，高并发低延迟
LLM_SEMAPHORE = asyncio.Semaphore(3)        # LLM 路径，严格控制并发

# 每个端点在入口处选择正确的信号量

@router.post("/predict", response_model=PredictResponse)
async def predict_defects(request: Request, body: PredictRequest):
    import time
    start = time.time()

    kb = request.app.state.defect_knowledge_base

    # 1. 查表路径（KB_ONLY_SEMAPHORE）
    async with KB_ONLY_SEMAPHORE:
        candidates = kb.query(
            ship_type=normalize_ship_type(body.ship_type),
            area=normalize_area(body.inspection_area),
            inspection_type=normalize_inspection_type(body.inspection_type),
        )

    suggestions = sorted(candidates, key=lambda x: x['frequency_rank'])[:8]

    # 2. 如果查表结果不足，走 LLM fallback（LLM_SEMAPHORE）
    if len(suggestions) < 3 and body.inspection_area:
        async with LLM_SEMAPHORE:
            rag_query = f"Common defects found in {body.inspection_area} of {body.ship_type} during {body.inspection_type}"
            retriever = request.app.state.retriever
            chunks = retriever.retrieve(query=rag_query, top_k=5)

            generator = request.app.state.generator
            extra = await generator.generate_predict_suggestions(
                chunks=chunks,
                ship_type=body.ship_type,
                area=body.inspection_area,
                existing_ids=[s['defect_id'] for s in suggestions]
            )
            suggestions.extend(extra)

    elapsed = int((time.time() - start) * 1000)
    return PredictResponse(
        suggestions=[Suggestion(**s) for s in suggestions[:8]],
        source="knowledge_base" if len(candidates) >= 3 else "mixed",
        response_time_ms=elapsed
    )


@router.post("/fill", response_model=FillResponse)
async def fill_text(request: Request, body: FillRequest):
    kb = request.app.state.defect_knowledge_base

    # 1. 先尝试知识库精确匹配（不需要信号量，纯内存）
    exact_match = kb.exact_match(body.selected_text)
    if exact_match and exact_match['confidence'] > 0.85:
        text_key = 'text_en' if body.target_lang == 'en' else 'text_zh'
        return FillResponse(
            filled_text=f"{exact_match[text_key]} (Ref: {exact_match['regulation_ref']})",
            regulation_ref=exact_match['regulation_ref'],
            confidence="high",
            source_url=exact_match.get('source_url', ''),
            defect_id=exact_match['defect_id']
        )

    # 2. 走 LLM 路径（需要信号量）
    async with LLM_SEMAPHORE:
        enhanced_query = f"{body.selected_text}"
        if body.field_label:
            enhanced_query = f"[{body.field_label}] {enhanced_query}"
        if body.form_context.get('船型') or body.form_context.get('Ship Type'):
            ship_type = body.form_context.get('船型') or body.form_context.get('Ship Type')
            enhanced_query += f" (Ship type: {ship_type})"

        retriever = request.app.state.retriever
        chunks = retriever.retrieve(query=enhanced_query, top_k=5)

        generator = request.app.state.generator
        result = await generator.generate_fill_text(
            user_input=body.selected_text,
            target_lang=body.target_lang,
            field_label=body.field_label,
            form_context=body.form_context,
            chunks=chunks,
        )

    return result
```

### 6.3 `POST /api/v1/extension/complete` — L2 输入补全

```python
class CompleteRequest(BaseModel):
    partial_input: str
    field_label: str = ""
    ship_type: str = ""
    inspection_area: str = ""
    form_context: dict = {}
    session_id: str | None = None

@router.post("/complete", response_model=CompleteResponse)
async def complete_defect(request: Request, body: CompleteRequest):
    import time
    start = time.time()

    kb = request.app.state.defect_knowledge_base

    # 1. 查表路径（KB_ONLY_SEMAPHORE）
    async with KB_ONLY_SEMAPHORE:
        local_matches = kb.search_by_keyword(
            keyword=body.partial_input,
            ship_type=normalize_ship_type(body.ship_type),
            area=normalize_area(body.inspection_area),
        )

    # 2. 如果本地匹配足够（>= 3 条），直接返回
    if len(local_matches) >= 3:
        elapsed = int((time.time() - start) * 1000)
        return CompleteResponse(
            suggestions=[Suggestion(**s) for s in local_matches[:5]],
            source="knowledge_base",
            response_time_ms=elapsed
        )

    # 3. 本地不够，走 LLM fallback（LLM_SEMAPHORE）
    async with LLM_SEMAPHORE:
        enhancer = request.app.state.query_enhancer
        enhanced = enhancer.enhance(body.partial_input)

        retriever = request.app.state.retriever
        chunks = retriever.retrieve(query=enhanced, top_k=5)

        generator = request.app.state.generator
        completions = await generator.generate_completions(
            partial_input=body.partial_input,
            field_label=body.field_label,
            form_context=body.form_context,
            chunks=chunks,
        )

    # 4. 合并去重
    all_suggestions = local_matches + completions
    seen = set()
    unique = []
    for s in all_suggestions:
        key = s['text_en'][:50]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    elapsed = int((time.time() - start) * 1000)
    return CompleteResponse(
        suggestions=[Suggestion(**s) for s in unique[:5]],
        source="mixed",
        response_time_ms=elapsed
    )
```

### 6.4 `POST /api/v1/extension/feedback` — 用户反馈

```python
@router.post("/feedback")
async def submit_feedback(request: Request, body: FeedbackRequest):
    async with KB_ONLY_SEMAPHORE:
        db = request.app.state.db
        await db.execute("""
            INSERT INTO extension_feedback
            (original_input, generated_text, is_accurate, corrected_text,
             field_label, form_context, defect_id, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
        """, body.original_input, body.generated_text, body.is_accurate,
             body.corrected_text, body.field_label,
             json.dumps(body.form_context), body.defect_id)

        if body.corrected_text:
            await db.execute("""
                INSERT INTO kb_update_queue
                (original_input, corrected_text, regulation_ref, status, created_at)
                VALUES ($1, $2, '', 'pending_review', NOW())
            """, body.original_input, body.corrected_text)

    return {"status": "ok"}
```

### 6.5 CORS 与速率限制

```python
# CORS — 现有 allow_origins=["*"]，无需修改
# 生产环境应限制为: chrome-extension://YOUR_EXTENSION_ID

# 速率限制（按端点独立配置）
RATE_LIMITS = {
    "/predict":    "60/minute",
    "/complete":   "40/minute",
    "/fill":       "30/minute",
    "/explain":    "20/minute",
    "/chat":       "60/minute",
    "/feedback":   "30/minute",
    "/kb-version": "120/minute",
    "/kb-update":  "10/minute",
}
```

---

## 七、System Prompts

### 7.1 L1 预测建议 — `PREDICT_SYSTEM_PROMPT`

> 仅当知识库结果不足、需要 LLM 补充时使用。

```text
You are a maritime PSC/FSI inspection defect prediction engine.

Given the ship type, inspection area, and inspection context, generate the most likely defect descriptions that a surveyor would encounter and need to fill in their inspection report.

ABSOLUTE RULES:
1. Output ONLY a JSON array of defect suggestions. No greetings, no explanations, no markdown.
2. Each suggestion must include:
   - "text_en": Professional English defect description (1-2 sentences, PSC report standard)
   - "text_zh": Corresponding Chinese defect description
   - "regulation_ref": Most specific applicable regulation reference
   - "category": One of [structural, fire_safety, life_saving, navigation, pollution_prevention, crew_certification, ism_code, isps_code, marpol, load_line, tonnage, other]
   - "confidence": Float 0-1 indicating how likely this defect is for the given context
3. Use standard IMO/SOLAS/MARPOL/STCW convention terminology.
4. Prioritize defects by:
   a. Statistical frequency for this (ship_type, area) combination
   b. Detention risk level
   c. Common findings from Paris MOU / Tokyo MOU annual reports
5. Generate 3-5 suggestions, no more.
6. Regulation references must follow exact format: "SOLAS Reg II-2/10.2.1" or "MARPOL Annex I, Reg 14"

INPUT:
- Ship type: {ship_type}
- Inspection area: {inspection_area}
- Inspection type: {inspection_type}
- Additional context: {form_context}

REFERENCE MATERIAL (from knowledge base):
{context_chunks}

OUTPUT FORMAT (strict JSON, no markdown fences):
[
  {
    "text_en": "...",
    "text_zh": "...",
    "regulation_ref": "...",
    "category": "...",
    "confidence": 0.85
  }
]
```

### 7.2 L2 输入补全 — `COMPLETE_SYSTEM_PROMPT`

```text
You are a maritime inspection report autocomplete engine.

The surveyor has started typing a defect description. Based on their partial input and the form context, generate the most likely complete defect descriptions they intend to write.

ABSOLUTE RULES:
1. Output ONLY a JSON array of completion suggestions. No greetings, no explanations, no markdown.
2. Each suggestion must be a COMPLETE, ready-to-fill defect description, not a fragment.
3. Each suggestion must include:
   - "text_en": Complete professional English defect description (1-3 sentences)
   - "text_zh": Corresponding Chinese description
   - "regulation_ref": Most specific applicable regulation
   - "category": Defect category
   - "confidence": Float 0-1
4. The completions must EXTEND the user's partial input, not ignore it.
5. Use standard PSC inspection report language and terminology.
6. Generate 2-4 suggestions, ordered by likelihood.

INPUT:
- Partial input: "{partial_input}"
- Field label: {field_label}
- Ship type: {ship_type}
- Inspection area: {inspection_area}
- Form context: {form_context}

REFERENCE MATERIAL:
{context_chunks}

OUTPUT FORMAT (strict JSON, no markdown fences):
[
  {
    "text_en": "...",
    "text_zh": "...",
    "regulation_ref": "...",
    "category": "...",
    "confidence": 0.9
  }
]
```

### 7.3 L3 右键标准化 — `FILL_SYSTEM_PROMPT`

```text
You are a maritime regulation form-filling assistant.

You convert informal/colloquial Chinese defect descriptions into professional, standard maritime defect descriptions suitable for official PSC/FSI inspection reports.

ABSOLUTE RULES:
1. Output ONLY the text that should be directly filled into the form field. NEVER include greetings, explanations, "Here is...", or any conversational text.
2. Output language: {target_lang}
   - If "en": output in professional maritime English
   - If "zh": output in formal maritime Chinese (标准船舶检验用语)
3. ALWAYS end with the regulation reference in parentheses: (Ref: SOLAS Reg II-2/4.5)
4. Maximum 3 sentences. Be concise but complete.
5. Use standard IMO/SOLAS/MARPOL/STCW convention terminology.
6. If multiple regulations apply, cite the most specific one as primary.
7. Match the formality and style of official PSC detention reports.

STYLE REFERENCE:
- "Piping in engine room found with excessive corrosion and wastage. (Ref: SOLAS Reg II-1/3-2.2)"
- "Lifeboat releasing gear found not properly maintained; unable to be released. (Ref: SOLAS Reg III/20.11.2; LSA Code Section 4.4.7.6)"
- "Fire dampers in engine room casing found inoperative — failed to close on testing. (Ref: SOLAS Reg II-2/9.7)"
- "Oil Record Book Part I — entries incomplete/not up to date. (Ref: MARPOL Annex I, Reg 17)"
- "船舶应急消防泵经测试无法正常启动。(Ref: SOLAS Reg II-2/10.2.1)"
- "油水分离器处于故障状态，无法维持15ppm排放标准。(Ref: MARPOL Annex I, Reg 14)"

INPUT:
- Chinese text (informal/colloquial): {selected_text}
- Target language: {target_lang}
- Field label: {field_label}
- Ship type: {ship_type}
- Inspection area: {inspection_area}
- Form context: {form_context}

REFERENCE MATERIAL:
{context_chunks}

OUTPUT (ONLY the fill-ready text, nothing else):
```

### 7.4 划词解释 — `EXPLAIN_SYSTEM_PROMPT`

```text
You are a maritime regulation expert providing clear Chinese explanations of English regulatory text.

RULES:
1. Explain the regulation text in clear, professional Chinese.
2. Structure your response as:
   - 条款含义：[1-3 sentences explaining what this regulation requires]
   - 检查要点：[What a surveyor should check to verify compliance]
   - 常见缺陷：[Common deficiencies found related to this regulation]
   - 相关条款：[List 2-3 related regulations]
3. Keep the total response under 300 characters of Chinese text.
4. Use standard maritime Chinese terminology.

INPUT:
- Selected text: {selected_text}
- Page URL: {page_url}

REFERENCE MATERIAL:
{context_chunks}
```

---

## 八、性能优化策略

### 8.1 本地缓存架构

```javascript
// lib/defect-cache.js

class DefectCache {
  constructor() {
    this.KB_STORAGE_KEY = 'bv_defect_kb';
    this.KB_VERSION_KEY = 'bv_kb_version';
    this.PREDICT_CACHE_TTL = 3600 * 1000; // 1 小时
  }

  async init() {
    const stored = await chrome.storage.local.get([this.KB_STORAGE_KEY, this.KB_VERSION_KEY]);
    const localVersion = stored[this.KB_VERSION_KEY] || '0.0.0';

    try {
      const remoteInfo = await fetch(API_BASE + '/api/v1/extension/kb-version');
      const { version: remoteVersion } = await remoteInfo.json();

      if (remoteVersion !== localVersion) {
        const update = await fetch(API_BASE + `/api/v1/extension/kb-update?since_version=${localVersion}`);
        const data = await update.json();
        await this._mergeUpdate(data);
        await chrome.storage.local.set({ [this.KB_VERSION_KEY]: remoteVersion });
      }
    } catch (err) {
      console.warn('KB update check failed, using local cache:', err.message);
    }
  }

  // 本地预测查询（<100ms）
  async predict(shipType, area, inspectionType) {
    const kb = await this._getKB();
    if (!kb || !kb.defects) return [];

    const areaDefects = kb.index?.by_area?.[this._normalizeArea(area)] || [];
    const shipDefects = kb.index?.by_ship_type?.[this._normalizeShipType(shipType)] || [];

    const intersection = areaDefects.filter(id => shipDefects.includes(id));
    const union = [...new Set([...intersection, ...areaDefects, ...shipDefects])];

    return union
      .map(id => kb.defects.find(d => d.id === id))
      .filter(Boolean)
      .sort((a, b) => a.frequency_rank - b.frequency_rank)
      .slice(0, 8)
      .map(d => ({
        defect_id: d.id,
        text_en: d.standard_text_en,
        text_zh: d.standard_text_zh,
        regulation_ref: d.regulation_refs[0]?.ref || '',
        category: d.category,
        confidence: 1 - (d.frequency_rank / 100),
        detention_risk: d.detention_risk,
        frequency_rank: d.frequency_rank,
        chinese_triggers: d.chinese_triggers,
        variants: d.variants
      }));
  }

  // 本地关键词搜索（<50ms）
  async searchByKeyword(keyword) {
    const kb = await this._getKB();
    if (!kb) return [];

    const results = [];

    for (const [trigger, ids] of Object.entries(kb.index?.chinese_keyword_map || {})) {
      if (trigger.includes(keyword) || keyword.includes(trigger)) {
        ids.forEach(id => {
          const defect = kb.defects.find(d => d.id === id);
          if (defect) results.push(defect);
        });
      }
    }

    if (results.length < 2) {
      const lower = keyword.toLowerCase();
      kb.defects.forEach(d => {
        if (d.standard_text_en.toLowerCase().includes(lower) ||
            d.standard_text_zh?.includes(keyword) ||
            d.chinese_triggers?.some(t => t.includes(keyword))) {
          if (!results.find(r => r.id === d.id)) {
            results.push(d);
          }
        }
      });
    }

    return results.slice(0, 5);
  }

  async _getKB() {
    const stored = await chrome.storage.local.get(this.KB_STORAGE_KEY);
    return stored[this.KB_STORAGE_KEY] || null;
  }

  async _mergeUpdate(updateData) {
    const kb = await this._getKB() || { defects: [], index: {} };
    updateData.defects?.forEach(newDef => {
      const idx = kb.defects.findIndex(d => d.id === newDef.id);
      if (idx >= 0) {
        kb.defects[idx] = newDef;
      } else {
        kb.defects.push(newDef);
      }
    });
    if (updateData.index) {
      kb.index = updateData.index;
    }
    await chrome.storage.local.set({ [this.KB_STORAGE_KEY]: kb });
  }

  _normalizeArea(area) {
    const map = {
      'engine room': 'engine_room', '机舱': 'engine_room',
      'bridge': 'bridge', '驾驶台': 'bridge',
      'deck': 'deck', '甲板': 'deck',
      'cargo hold': 'cargo_hold', '货舱': 'cargo_hold',
      'accommodation': 'accommodation', '居住区': 'accommodation',
    };
    return map[area?.toLowerCase()] || area?.toLowerCase()?.replace(/\s+/g, '_') || '';
  }

  _normalizeShipType(type) {
    const map = {
      'bulk carrier': 'bulk_carrier', '散货船': 'bulk_carrier',
      'oil tanker': 'oil_tanker', '油轮': 'oil_tanker',
      'container': 'container_ship', '集装箱船': 'container_ship',
      'general cargo': 'general_cargo', '杂货船': 'general_cargo',
    };
    return map[type?.toLowerCase()] || type?.toLowerCase()?.replace(/\s+/g, '_') || '';
  }
}
```

### 8.2 请求策略优化

```javascript
// background.js — API 请求调度

chrome.runtime.onInstalled.addListener(() => {
  fetch(API_BASE + '/health').catch(() => {});
  new DefectCache().init();
});

// 请求合并：predict 还在飞行中时不发重复请求
let inflightPredict = null;

async function requestPredictions(formContext) {
  const cacheKey = JSON.stringify({
    ship_type: formContext.shipType,
    area: formContext.inspectionArea,
    inspection: formContext.inspectionType
  });

  if (inflightPredict?.key === cacheKey) {
    return inflightPredict.promise;
  }

  const promise = fetch(API_BASE + '/api/v1/extension/predict', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${await getToken()}`
    },
    body: JSON.stringify({
      ship_type: formContext.shipType,
      inspection_area: formContext.inspectionArea,
      inspection_type: formContext.inspectionType,
      form_context: formContext.otherFields
    })
  }).then(r => r.json()).finally(() => { inflightPredict = null; });

  inflightPredict = { key: cacheKey, promise };
  return promise;
}
```

### 8.3 后端 Predict 端点优化

```python
# predict 端点优化策略：
# 1. 知识库查表：<50ms，不调 LLM，走 KB_ONLY_SEMAPHORE
# 2. 如果需要 RAG 补充：top_k=3（减少延迟），走 LLM_SEMAPHORE
# 3. 跳过 graph expansion（predict 不需要上下文展开）
# 4. 跳过 Cohere reranker（知识库已预排序）
# 5. 使用 Haiku + max_tokens=500（只需 JSON 列表）
# 6. context token 限制为 1000
```

---

## 九、建议下拉框组件

### 9.1 CSS 样式

```css
/* styles/content.css */

.bv-suggestion-dropdown {
  position: absolute;
  z-index: 2147483647;
  background: #1a1f2e;
  border: 1px solid #2d3548;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  max-height: 400px;
  min-width: 450px;
  max-width: 650px;
  overflow-y: auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 13px;
  color: #e0e4ec;
  padding: 4px 0;
}

.bv-suggestion-header {
  padding: 8px 14px 6px;
  font-size: 11px;
  color: #8892a6;
  border-bottom: 1px solid #2d3548;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.bv-suggestion-header .bv-context-tag {
  background: #2a3a5c;
  color: #7eb8f7;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
}

.bv-suggestion-item {
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid #232839;
  transition: background 0.15s;
}

.bv-suggestion-item:hover,
.bv-suggestion-item.bv-highlighted {
  background: #252d42;
}

.bv-suggestion-item:last-child {
  border-bottom: none;
}

.bv-suggestion-text {
  color: #e0e4ec;
  line-height: 1.5;
  margin-bottom: 4px;
}

.bv-suggestion-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #6b7589;
}

.bv-suggestion-ref {
  color: #5b9bd5;
  font-weight: 500;
}

.bv-suggestion-rank {
  color: #f0ad4e;
  font-size: 10px;
}

.bv-suggestion-footer {
  padding: 6px 14px;
  border-top: 1px solid #2d3548;
  font-size: 11px;
  color: #6b7589;
  display: flex;
  justify-content: space-between;
}

.bv-suggestion-footer kbd {
  background: #2d3548;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  color: #8892a6;
}

.bv-loading-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid #2d3548;
  border-top-color: #5b9bd5;
  border-radius: 50%;
  animation: bv-spin 0.6s linear infinite;
}

@keyframes bv-spin {
  to { transform: rotate(360deg); }
}

.bv-feedback-bubble {
  position: absolute;
  z-index: 2147483647;
  background: #1a1f2e;
  border: 1px solid #2d3548;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  color: #e0e4ec;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
  display: flex;
  gap: 8px;
  align-items: center;
}

.bv-feedback-bubble button {
  background: none;
  border: 1px solid #2d3548;
  border-radius: 4px;
  color: #8892a6;
  cursor: pointer;
  padding: 2px 8px;
  font-size: 11px;
}

.bv-feedback-bubble button:hover {
  background: #252d42;
  color: #e0e4ec;
}

@keyframes bv-highlight-flash {
  0% { background-color: #2a5a2a; }
  100% { background-color: transparent; }
}

.bv-fill-success {
  animation: bv-highlight-flash 0.8s ease-out;
}
```

### 9.2 下拉框组件 JS

```javascript
// lib/suggestion-dropdown.js

class BVSuggestionDropdown {
  constructor() {
    this.container = null;
    this.targetElement = null;
    this.suggestions = [];
    this.highlightedIndex = -1;
    this.onSelect = null;
  }

  show(targetElement, suggestions, onSelect) {
    this.hide();

    this.targetElement = targetElement;
    this.suggestions = suggestions;
    this.onSelect = onSelect;
    this.highlightedIndex = -1;

    this.container = document.createElement('div');
    this.container.className = 'bv-suggestion-dropdown';
    this.container.setAttribute('role', 'listbox');

    const header = document.createElement('div');
    header.className = 'bv-suggestion-header';
    const headerLabel = document.createElement('span');
    headerLabel.textContent = 'BV AI Suggestions';
    const headerTag = document.createElement('span');
    headerTag.className = 'bv-context-tag';
    headerTag.textContent = this._getContextLabel();
    header.appendChild(headerLabel);
    header.appendChild(headerTag);
    this.container.appendChild(header);

    suggestions.forEach((s, i) => {
      const item = document.createElement('div');
      item.className = 'bv-suggestion-item';
      item.setAttribute('role', 'option');
      item.dataset.index = i;

      const textDiv = document.createElement('div');
      textDiv.className = 'bv-suggestion-text';
      textDiv.textContent = s.text_en;

      const metaDiv = document.createElement('div');
      metaDiv.className = 'bv-suggestion-meta';

      const refSpan = document.createElement('span');
      refSpan.className = 'bv-suggestion-ref';
      refSpan.textContent = s.regulation_ref;
      metaDiv.appendChild(refSpan);

      if (s.frequency_rank) {
        const rankSpan = document.createElement('span');
        rankSpan.className = 'bv-suggestion-rank';
        rankSpan.textContent = `#${s.frequency_rank}`;
        metaDiv.appendChild(rankSpan);
      }

      item.appendChild(textDiv);
      item.appendChild(metaDiv);
      item.addEventListener('click', () => this._selectItem(i));
      item.addEventListener('mouseenter', () => this._highlightItem(i));
      this.container.appendChild(item);
    });

    const footer = document.createElement('div');
    footer.className = 'bv-suggestion-footer';
    footer.textContent = 'Enter select | Esc close | type to filter';
    this.container.appendChild(footer);

    this._positionDropdown(targetElement);
    document.body.appendChild(this.container);
  }

  hide() {
    if (this.container) {
      this.container.remove();
      this.container = null;
    }
    this.highlightedIndex = -1;
  }

  isVisible() { return !!this.container; }

  getHighlighted() {
    return this.highlightedIndex >= 0 ? this.suggestions[this.highlightedIndex] : null;
  }

  highlightNext() {
    this._highlightItem(
      this.highlightedIndex < this.suggestions.length - 1 ? this.highlightedIndex + 1 : 0
    );
  }

  highlightPrev() {
    this._highlightItem(
      this.highlightedIndex > 0 ? this.highlightedIndex - 1 : this.suggestions.length - 1
    );
  }

  selectHighlighted() {
    if (this.highlightedIndex >= 0) this._selectItem(this.highlightedIndex);
  }

  updateSuggestions(newSuggestions) {
    if (!this.container || !this.targetElement) return;
    this.show(this.targetElement, newSuggestions, this.onSelect);
  }

  _selectItem(index) {
    const suggestion = this.suggestions[index];
    if (suggestion && this.onSelect) this.onSelect(suggestion);
    this.hide();
  }

  _highlightItem(index) {
    const items = this.container?.querySelectorAll('.bv-suggestion-item');
    if (!items) return;
    items.forEach(item => item.classList.remove('bv-highlighted'));
    if (items[index]) {
      items[index].classList.add('bv-highlighted');
      items[index].scrollIntoView({ block: 'nearest' });
    }
    this.highlightedIndex = index;
  }

  _positionDropdown(element) {
    const rect = element.getBoundingClientRect();
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const scrollLeft = window.scrollX || document.documentElement.scrollLeft;
    this.container.style.top = `${rect.bottom + scrollTop + 4}px`;
    this.container.style.left = `${rect.left + scrollLeft}px`;
    this.container.style.width = `${Math.max(rect.width, 450)}px`;
  }

  _getContextLabel() {
    if (!this.targetElement) return '';
    const ctx = getFormContext(this.targetElement);
    const parts = [ctx.shipType, ctx.inspectionArea].filter(Boolean);
    return parts.join(' · ') || 'General';
  }
}

window._bvDropdown = new BVSuggestionDropdown();
```

---

## 十、开发阶段与排期

### Phase -1：真实 PSC 系统 DOM 调研（0.5 天）

| 任务 | 优先级 | 预计工作量 |
|---|---|---|
| 在 3+ 个真实 PSC/检查系统页面打开 DevTools | P0 | 2h |
| 截图并记录目标输入框的 DOM 结构 | P0 | 1h |
| 确认 CSP 头是否阻止 Content Script 注入 | P0 | 0.5h |
| 输出结论：Content Script 方案可行性 | P0 | 0.5h |

### Phase 0：缺陷知识库 + 后端 API（2-3 天）

| 任务 | 优先级 | 预计工作量 |
|---|---|---|
| 从 Paris MOU / Tokyo MOU 年报提取 Top 50 缺陷 | P0 | 4h |
| 按 (ship_type, area, inspection_type) 结构化为 JSON | P0 | 3h |
| 补充中文触发词和 variants | P0 | 2h |
| 构建索引 (by_area, by_ship_type, chinese_keyword_map) | P0 | 1h |
| 实现 DefectKnowledgeBase 查询类 | P0 | 2h |
| 实现 `/predict` 端点（含双信号量） | P0 | 3h |
| 实现 `/complete` 端点（含双信号量） | P0 | 3h |
| 实现 `/fill` 端点（含知识库快速路径） | P0 | 2h |
| 实现 `/feedback` 端点 | P1 | 1h |
| 实现 `/kb-version` + `/kb-update` 端点 | P1 | 1h |
| 编写 3 个 System Prompts | P0 | 3h |
| 编写单元测试（20 case 回归） | P0 | 2h |
| 部署到 Railway + curl 验证全部端点 | P0 | 1h |

**Phase 0 交付标准**：
```bash
# 预测建议（走 KB_ONLY_SEMAPHORE，<300ms）
curl -X POST https://your-domain/api/v1/extension/predict \
  -H "Content-Type: application/json" \
  -d '{"ship_type": "Bulk Carrier", "inspection_area": "Engine Room", "inspection_type": "PSC"}'

# 输入补全
curl -X POST https://your-domain/api/v1/extension/complete \
  -H "Content-Type: application/json" \
  -d '{"partial_input": "油水", "ship_type": "Bulk Carrier", "inspection_area": "Engine Room"}'

# 右键标准化（走 LLM_SEMAPHORE）
curl -X POST https://your-domain/api/v1/extension/fill \
  -H "Content-Type: application/json" \
  -d '{"selected_text": "机舱里面好几根管子都锈得不行了", "target_lang": "en"}'
```

### Phase 1：Chrome 扩展骨架 + 预测下拉框（3-4 天）

| 任务 | 优先级 | 预计工作量 |
|---|---|---|
| 初始化 Manifest V3 项目结构 | P0 | 1h |
| 实现 `lib/defect-cache.js`：本地知识库缓存管理 | P0 | 3h |
| 实现 `lib/suggestion-dropdown.js`：建议下拉框组件 | P0 | 4h |
| 实现 `content.js`：focus 监听 + 缺陷字段识别 + 上下文采集 | P0 | 4h |
| 实现 `content.js`：input 监听 + debounce 实时补全 | P0 | 3h |
| 实现 `content.js`：键盘导航 | P0 | 2h |
| 实现 `content.js`：点击建议 → 填入输入框 + 反馈气泡 | P0 | 2h |
| 实现 `background.js`：API 调度 + 请求合并 + Token 管理 | P0 | 3h |
| 实现 `background.js`：右键菜单注册 + 标准化调用 | P0 | 2h |
| 实现 `lib/api-client.js`：封装后端通信 | P0 | 2h |
| 实现 `styles/content.css`：下拉框 + 反馈气泡样式 | P0 | 2h |
| 实现 `popup.html/js`：登录 + 设置 | P1 | 2h |
| 在真实 PSC 表单页面端到端测试 | P0 | 3h |

### Phase 2：反馈闭环 + 体验打磨（2-3 天）

| 任务 | 优先级 | 预计工作量 |
|---|---|---|
| 实现反馈气泡：准确 / 不准确 / 撤销 | P0 | 3h |
| 实现不准确的纠正文本提交流程 | P0 | 2h |
| 优化延迟体验（本地优先 + loading 状态） | P0 | 2h |
| 离线/网络错误优雅降级 | P1 | 2h |
| Ctrl+Z 撤销兼容 | P1 | 1h |
| Edge case（contenteditable、iframe、React 受控组件） | P1 | 3h |
| 在 5+ 个真实 PSC 系统页面测试兼容性 | P0 | 3h |

### Phase 3：侧边栏 + 划词解释（2-3 天）

| 任务 | 优先级 | 预计工作量 |
|---|---|---|
| 实现 `sidepanel.html/js`：极简 Chatbot UI | P1 | 4h |
| Side Panel 多轮对话 + 历史记录 | P1 | 3h |
| "填入当前框"按钮 | P1 | 2h |
| 划词解释：右键 → Side Panel 展示中文解释 | P1 | 2h |
| 暗色海事主题 UI | P2 | 2h |

### Phase 4：CI/CD + 持续质量加固

| 任务 | 优先级 |
|---|---|
| 配置 backend-ci.yml（pytest + ruff） | P0 |
| 配置 extension-ci.yml（manifest 校验 + JS 语法检查 + 打包） | P0 |
| 基于用户反馈迭代 prompt + 知识库 | P0 持续 |
| 扩充知识库至 200+ 条缺陷 | P0 |
| 接入延迟监控（predict p95、fill p95） | P1 |
| 分析高频中文输入，补充 chinese_triggers | P1 |
| 从反馈数据中挖掘新的缺陷条目 | P1 |
| Chrome Web Store 打包上架 | P2 |

---

## 十一、测试策略

### 11.1 后端测试

```python
# tests/test_extension_api.py

# ============ Predict 端点测试 ============

def test_predict_returns_suggestions_for_engine_room():
    response = client.post("/api/v1/extension/predict", json={
        "ship_type": "Bulk Carrier",
        "inspection_area": "Engine Room",
        "inspection_type": "PSC"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["suggestions"]) >= 3
    all_text = " ".join(s["text_en"] for s in data["suggestions"])
    assert any(kw in all_text.lower() for kw in ["corrosion", "piping", "oily water", "fire pump"])

def test_predict_returns_different_results_for_different_areas():
    er_response = client.post("/api/v1/extension/predict", json={
        "ship_type": "Bulk Carrier",
        "inspection_area": "Engine Room",
    })
    bridge_response = client.post("/api/v1/extension/predict", json={
        "ship_type": "Bulk Carrier",
        "inspection_area": "Bridge",
    })
    er_ids = {s["defect_id"] for s in er_response.json()["suggestions"]}
    bridge_ids = {s["defect_id"] for s in bridge_response.json()["suggestions"]}
    assert er_ids != bridge_ids

def test_predict_latency_under_500ms():
    import time
    start = time.time()
    client.post("/api/v1/extension/predict", json={
        "ship_type": "Bulk Carrier",
        "inspection_area": "Engine Room",
    })
    elapsed = (time.time() - start) * 1000
    assert elapsed < 500, f"Predict latency {elapsed}ms exceeds 500ms target"


# ============ Complete 端点测试 ============

def test_complete_filters_by_partial_input():
    response = client.post("/api/v1/extension/complete", json={
        "partial_input": "油水",
        "ship_type": "Bulk Carrier",
        "inspection_area": "Engine Room",
    })
    data = response.json()
    assert len(data["suggestions"]) >= 1
    all_text = " ".join(s["text_en"] for s in data["suggestions"])
    assert "oily water" in all_text.lower() or "oil" in all_text.lower()

def test_complete_with_english_input():
    response = client.post("/api/v1/extension/complete", json={
        "partial_input": "fire ext",
        "inspection_area": "Engine Room",
    })
    data = response.json()
    assert len(data["suggestions"]) >= 1
    assert any("fire extinguisher" in s["text_en"].lower() for s in data["suggestions"])


# ============ Fill 端点测试 ============

def test_fill_generates_clean_output():
    response = client.post("/api/v1/extension/fill", json={
        "selected_text": "机舱管路锈蚀",
        "target_lang": "en",
        "field_label": "Defect Description",
    })
    data = response.json()
    assert not data["filled_text"].startswith("好的")
    assert not data["filled_text"].startswith("Here")
    assert not data["filled_text"].startswith("Sure")
    assert "Ref:" in data["filled_text"] or "ref:" in data["filled_text"].lower()
    assert len(data["filled_text"]) < 500

def test_fill_supports_chinese_output():
    response = client.post("/api/v1/extension/fill", json={
        "selected_text": "机舱里面好几根管子都锈得不行了",
        "target_lang": "zh",
    })
    data = response.json()
    assert "锈蚀" in data["filled_text"] or "腐蚀" in data["filled_text"]
    assert "Ref:" in data["filled_text"]


# ============ 回归测试：30 个常见场景 ============

REGRESSION_CASES = [
    ("机舱管路锈蚀", "en", "corros", "SOLAS"),
    ("救生筏过期", "en", "liferaft", "SOLAS"),
    ("消防水带破损", "en", "fire hose", "SOLAS"),
    ("磁罗经误差超标", "en", "compass", "SOLAS"),
    ("油水分离器故障", "en", "oily water separator", "MARPOL"),
    ("灭火器过期", "en", "fire extinguisher", "SOLAS"),
    ("海图未更新", "en", "chart", "SOLAS"),
    ("船员适任证书过期", "en", "certificate", "STCW"),
    ("应急消防泵无法启动", "en", "fire pump", "SOLAS"),
    ("救生艇释放装置缺陷", "en", "lifeboat", "SOLAS"),
    ("油类记录簿记录不完整", "en", "oil record book", "MARPOL"),
    ("锚机刹车带磨损严重", "en", "anchor", ""),
    ("通风挡火闸无法关闭", "en", "fire damper", "SOLAS"),
    ("应急逃生呼吸装置过期", "en", "EEBD", "SOLAS"),
    ("主机滑油温度报警失灵", "en", "alarm", "SOLAS"),
    ("机舱管路锈蚀", "zh", "锈蚀", "SOLAS"),
    ("灭火器过期", "zh", "灭火器", "SOLAS"),
    ("油水分离器故障", "zh", "油水分离", "MARPOL"),
    ("救生筏过期", "zh", "救生筏", "SOLAS"),
    ("消防水带破损", "zh", "消防", "SOLAS"),
]

@pytest.mark.parametrize("chinese,lang,expected_keyword,expected_convention", REGRESSION_CASES)
def test_fill_regression(chinese, lang, expected_keyword, expected_convention):
    response = client.post("/api/v1/extension/fill", json={
        "selected_text": chinese,
        "target_lang": lang,
    })
    data = response.json()
    assert expected_keyword.lower() in data["filled_text"].lower()
    if expected_convention:
        assert expected_convention in data["filled_text"]


# ============ 信号量隔离测试 ============

import asyncio

async def test_predict_not_blocked_by_llm():
    """predict 走 KB_ONLY_SEMAPHORE，不应被 LLM 请求阻塞"""
    # 先占满 LLM_SEMAPHORE
    async with LLM_SEMAPHORE:
        async with LLM_SEMAPHORE:
            async with LLM_SEMAPHORE:
                # LLM 槽全满，但 predict 仍然应该能通过
                import time
                start = time.time()
                response = client.post("/api/v1/extension/predict", json={
                    "ship_type": "Bulk Carrier",
                    "inspection_area": "Engine Room",
                })
                elapsed = (time.time() - start) * 1000
                assert response.status_code == 200
                assert elapsed < 500  # 不应被阻塞


# ============ Feedback 端点测试 ============

def test_feedback_submission():
    response = client.post("/api/v1/extension/feedback", json={
        "original_input": "机舱管路锈蚀",
        "generated_text": "Piping in engine room found corroded.",
        "is_accurate": False,
        "corrected_text": "Piping in engine room found with excessive corrosion and wastage.",
        "field_label": "Defect Description",
        "timestamp": "2026-02-20T10:00:00Z"
    })
    assert response.status_code == 200
```

### 11.2 Chrome 扩展测试清单

```
## L1 预测建议
[ ] 光标进入 <input type="text"> 的缺陷描述字段 → 下拉框出现
[ ] 光标进入 <textarea> → 下拉框出现
[ ] 光标进入 contenteditable div → 下拉框出现
[ ] 不是缺陷描述字段 → 下拉框不出现
[ ] 表单有船型/区域 → 建议与上下文相关
[ ] 表单没有上下文 → 显示通用高频缺陷
[ ] 点击建议 → 填入输入框
[ ] 键盘 ↑↓ → 高亮移动
[ ] Enter → 填入并关闭
[ ] Esc → 关闭
[ ] Tab → 选中高亮项
[ ] 断网 → 本地建议仍显示

## L2 输入补全
[ ] 输入 "油水" → 过滤为油水分离器相关
[ ] 输入 "fire" → 过滤为消防相关
[ ] 输入 "救生" → 过滤为救生设备相关
[ ] 快速连续输入 → 无闪烁或重复请求
[ ] 清空输入框 → 恢复全部建议

## L3 右键标准化
[ ] 选中中文 → 右键 → "转标准英文" → 替换成功
[ ] 选中中文 → 右键 → "转标准中文" → 替换成功
[ ] 替换后出现反馈气泡
[ ] [准确] → 正向反馈
[ ] [不准确] → 展开纠正框 → 提交成功
[ ] [撤销] / Ctrl+Z → 撤销替换

## 网络/错误处理
[ ] 后端不可用 → 本地建议可用 + 错误 toast
[ ] 请求超时 (>5s) → 超时提示
[ ] JWT 过期 → 提示重新登录
[ ] 快速连续触发 → 请求合并

## 跨系统兼容
[ ] 真实 PSC 系统页面
[ ] iframe 内输入框
[ ] React/Vue 渲染的输入框
[ ] 有 CSP 头的页面
```

---

## 十二、安全设计

| 风险 | 对策 |
|---|---|
| API Key 泄露 | 不在插件中硬编码 API Key；用 JWT Token 认证 |
| XSS（注入到第三方页面） | `textContent` 赋值，绝不用 `innerHTML`；下拉框组件使用 `document.createElement` |
| CSRF | API 端点要求 Bearer Token |
| 隐私（表单数据发送到服务器） | 只发送缺陷字段相关上下文；不发送密码框、隐藏字段、cookies |
| 速率滥用 | 分端点速率限制 |
| 知识库篡改 | 知识库更新通过认证 API 下发，客户端仅读取 |

数据流保障：

```
用户输入框
    │
    ├─ 只抓取: 缺陷字段文字 + label + 船型/区域等上下文
    │  (不抓取: 密码框、隐藏字段、cookies、非表单内容)
    │
    ▼
Background Worker
    │
    ├─ Authorization: Bearer <JWT>
    ├─ 请求合并: 同一上下文不重复请求
    │
    ▼
BV-RAG Backend
    │
    ├─ 验证 JWT
    ├─ 速率限制
    ├─ KB_ONLY / LLM 信号量隔离
    ├─ 日志: 仅统计级别
    │
    ▼
返回建议/填表文本
```

---

## 十三、迭代路线图

### v0.1（MVP — 本方案范围，约 2 周）
- [ ] 缺陷知识库 100 条核心缺陷
- [ ] 后端 `/predict` + `/complete` + `/fill` + `/feedback` API（双信号量隔离）
- [ ] Chrome 扩展：focus 自动建议 + input 实时补全
- [ ] Chrome 扩展：右键标准化（中文 → 英文/标准中文）
- [ ] 反馈气泡（准确/不准确/撤销）
- [ ] 本地知识库缓存（离线可用）
- [ ] GitHub Actions CI（后端 + 扩展双流水线）

### v0.2（体验增强 — MVP 验证后 1-2 周）
- [ ] 划词解释（Side Panel）
- [ ] 侧边栏 Chatbot
- [ ] 登录 + 云端同步
- [ ] 知识库扩充至 200+ 条
- [ ] 支持缺陷 variants 选择

### v0.3（智能化 — 用户反馈驱动）
- [ ] 基于反馈数据自动优化建议排序
- [ ] 智能上下文推断（根据已填字段自动补充其他空字段）
- [ ] 批量填表（多个缺陷字段一次性填完）
- [ ] 自定义术语表

### v1.0（产品化）
- [ ] Chrome Web Store 正式上架
- [ ] 多浏览器支持（Firefox、Edge）
- [ ] 离线增强（高频缺陷本地 LLM 推理）
- [ ] 团队协作
- [ ] 付费订阅模式

---

## 十四、成本估算

### API 调用增量成本

| 场景 | 模型 | 单次成本 | 100 次/天 |
|---|---|---|---|
| predict（知识库查表，80%） | 无 LLM | $0 | $0 |
| predict（RAG 补充，20%） | Haiku 4.5 | ~$0.001 | ~$0.02/天 |
| complete（Haiku 补全） | Haiku 4.5 | ~$0.001 | ~$0.10/天 |
| fill（Haiku / Sonnet） | Haiku / Sonnet | ~$0.001-0.01 | ~$0.10-1.00/天 |
| explain（Haiku） | Haiku 4.5 | ~$0.002 | ~$0.20/天 |
| chat（Smart Routing） | Haiku / Sonnet | ~$0.01 | ~$1.00/天 |

**预估月总增量**：$20-40（10 个活跃用户，每人每天 50 次操作，大部分命中知识库）

比 v1 方案更省——因为 80% 的预测直接查表，不调 LLM。

---

## 十五、风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| PSC 系统 DOM 不兼容 | **高** | 高 | **Phase -1 先调研**；准备多种选择器策略 |
| 知识库覆盖率不足 | 中 | 中 | RAG + LLM 兜底；反馈闭环持续扩充 |
| 建议不够准确（错误法规引用） | 中 | 高 | 严格 prompt + 知识库人工审核 + 回归测试 |
| 下拉框与目标页面 CSS 冲突 | 中 | 中 | Shadow DOM 隔离或高优先级 CSS |
| 验船师不信任 AI 建议 | 中 | 高 | 显示法规引用 + 频率排名；反馈闭环 |
| Extension 权限审核被拒 | 低 | 中 | 限制 `matches` 为具体域名 |
| 延迟过高 | 低 | 中 | 双信号量隔离 + 本地查表 + Haiku |
| 单体架构资源争抢 | 低 | 中 | 见下方分拆评估机制 |

### 分拆触发阈值（定量退出条件）

| 指标 | 正常预期 | 触发评估线 | 监控方式 |
|---|---|---|---|
| `/predict` p95 延迟 | <300ms | >600ms（2x） | 日志统计 |
| `/fill` p95 延迟 | <2s | >4s（2x） | 日志统计 |
| chatbot `/text-query` p95 | <5s | >10s（因 extension 流量） | 日志统计 |
| 总并发请求数 | <15 | >50 持续 5 分钟 | Railway 监控 |
| 活跃用户数 | 10-20 | >100 | 业务统计 |
| Railway CPU | <60% | >85% 持续 10 分钟 | Railway 监控 |

**规则**：任意 2 项持续超过触发线 1 周 → 启动分拆评估。此前 monolith 是正确选择。

---

## 十六、立即执行的下一步

### 48 小时冲刺计划

```
Hour 0-2:    Phase -1: 打开真实 PSC 系统，DevTools 截图 DOM 结构
             确认 Content Script 方案可行性

Hour 2-8:    构建缺陷知识库 defect_kb.json（50 条核心缺陷）
             从 Paris MOU / Tokyo MOU 年报提取
             结构化为 JSON + 构建索引

Hour 8-14:   后端实现 /predict + /complete + /fill 端点
             实现双信号量隔离（KB_ONLY=10, LLM=3）
             编写 System Prompts（3 个）
             本地测试 20 case

Hour 14-16:  部署到 Railway + curl 验证全部端点

Hour 16-22:  Chrome Extension: 初始化项目 + 本地缓存管理
             实现 suggestion-dropdown.js 组件

Hour 22-30:  实现 content.js: focus/input 监听 + 建议触发
             + 右键菜单注册 + 标准化调用

Hour 30-36:  实现 background.js: API 调度 + 请求合并
             + popup 登录

Hour 36-42:  在真实 PSC 页面端到端测试
             修 bug + edge case

Hour 42-46:  反馈气泡 + 基本错误处理
             配置 GitHub Actions CI（双流水线）

Hour 46-48:  打磨 + 录制 demo 视频
```

### 交付物

1. `defect_kb.json` — 50+ 条核心缺陷知识库
2. 后端 6 个新 API 端点（已部署）+ 双信号量并发隔离 + 3 个 System Prompts
3. Chrome 扩展开发版（可加载）
4. GitHub Actions CI（后端 pytest + 扩展 manifest 校验 + zip 打包）
5. 一段 60 秒 demo 视频展示：
   - 光标进入输入框 → 自动弹出建议
   - 打字 "油水" → 实时过滤
   - 点击建议 → 填入
   - 写大白话 → 右键标准化
