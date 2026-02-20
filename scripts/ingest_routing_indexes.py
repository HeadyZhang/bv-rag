"""Ingest regulation routing index curated chunks.

Provides chapter-level routing guides for LLM to correctly identify
which chapter/regulation covers a given topic. Bilingual EN+ZH.

Usage:
    python -m scripts.ingest_routing_indexes
"""
import logging
import sys

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from config.settings import settings
from db.postgres import PostgresDB

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROUTING_INDEX_DATA = [
    # ================================================================
    # Chunk 1: SOLAS Convention — Full chapter index
    # ================================================================
    {
        "id": "solas-convention-chapter-index",
        "source": "SOLAS",
        "document": "SOLAS",
        "chapter": "ALL",
        "regulation": "SOLAS Convention",
        "title": "SOLAS Convention – Complete Chapter Index and Routing Guide",
        "breadcrumb": "SOLAS > Convention Overview > Chapter Index",
        "body_text": (
            "SOLAS – International Convention for the Safety of Life at Sea\n"
            "Complete Chapter Structure and Routing Guide / 国际海上人命安全公约章节索引\n\n"
            "| Chapter | English Title | 中文标题 | Key Regulations |\n"
            "|---------|-------------|---------|------------------|\n"
            "| I | General Provisions | 总则 | Reg.1-12: Survey, certificates |\n"
            "| II-1 | Construction – Subdivision and Stability | 构造-分舱与稳性 | "
            "Reg.1-45: Subdivision, stability, machinery, electrical |\n"
            "| II-2 | Construction – Fire Protection | 构造-防火 | "
            "Reg.1-20: Fire safety, detection, firefighting |\n"
            "| III | Life-Saving Appliances | 救生设备与布置 | "
            "Reg.1-37: Lifeboats, liferafts, LSA |\n"
            "| IV | Radiocommunications | 无线电通信 | "
            "Reg.1-18: GMDSS, radio equipment |\n"
            "| V | Safety of Navigation | 航行安全 | "
            "Reg.1-35: Navigation equipment, charts, routing |\n"
            "| VI | Carriage of Cargoes | 货物运输 | "
            "Reg.1-9: General cargo safety |\n"
            "| VII | Carriage of Dangerous Goods | 危险货物运输 | "
            "Reg.1-11: IMDG Code, bulk chemicals |\n"
            "| VIII | Nuclear Ships | 核动力船舶 | Reg.1-4 |\n"
            "| IX | Management for Safe Operation | 安全管理/ISM | "
            "Reg.1-6: ISM Code |\n"
            "| X | High-Speed Craft | 高速船 | Reg.1-4: HSC Code |\n"
            "| XI-1 | Special Measures – Safety | 特殊安全措施 | "
            "Reg.1-7: Enhanced surveys, CIC |\n"
            "| XI-2 | Special Measures – Security | 安保/ISPS | "
            "Reg.1-13: ISPS Code |\n"
            "| XII | Additional Safety for Bulk Carriers | 散货船 | "
            "Reg.1-14: Structural requirements |\n"
            "| XIV | Safety for Polar Waters | 极地规则 | "
            "Reg.1-4: Polar Code |\n\n"
            "ROUTING GUIDE / 路由指引:\n"
            "EN: \"fire protection / fire division / A-class\" → Chapter II-2\n"
            "ZH: \"防火 / 防火分隔 / A级分隔\" → 第II-2章\n\n"
            "EN: \"life-saving / lifeboat / liferaft\" → Chapter III\n"
            "ZH: \"救生设备 / 救生艇 / 救生筏\" → 第III章\n\n"
            "EN: \"navigation / ECDIS / AIS / VDR\" → Chapter V\n"
            "ZH: \"航行安全 / 电子海图 / AIS / 航行数据记录仪\" → 第V章\n\n"
            "EN: \"dangerous goods / tanker / inert gas\" → Chapter II-2 (Reg.4 & Reg.11)\n"
            "ZH: \"危险货物 / 油轮 / 惰气系统\" → 第II-2章（第4条和第11条）\n\n"
            "EN: \"ISM / safety management\" → Chapter IX\n"
            "ZH: \"安全管理 / ISM体系\" → 第IX章\n\n"
            "EN: \"ISPS / ship security\" → Chapter XI-2\n"
            "ZH: \"船舶安保 / ISPS\" → 第XI-2章\n\n"
            "EN: \"stability / subdivision / watertight\" → Chapter II-1\n"
            "ZH: \"稳性 / 分舱 / 水密\" → 第II-1章\n\n"
            "EN: \"steering gear / rudder\" → Chapter II-1 Reg.29\n"
            "ZH: \"舵机 / 操舵装置\" → 第II-1章第29条\n\n"
            "COMMON CONFUSION:\n"
            "- Fire protection equipment (extinguishers, CO2) → II-2 (NOT II-1)\n"
            "- Inert gas systems → II-2/4.5.5 (NOT a separate chapter)\n"
            "- ECDIS/AIS → Chapter V (NOT Chapter IV which is radio)\n"
            "- ISM Code → Chapter IX (NOT ISPS which is XI-2)"
        ),
        "metadata_extra": {
            "topic": "routing_index",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS", "convention", "chapter index", "routing guide",
            "fire protection", "life-saving", "navigation", "ISM", "ISPS",
            "subdivision", "stability", "cargo", "dangerous goods",
        ],
        "keywords_zh": [
            "国际海上人命安全公约", "SOLAS公约", "章节索引",
            "防火", "救生", "航行安全", "无线电通信", "货物运输", "危险货物",
            "安全管理", "船舶安保", "散货船", "高速船", "极地规则",
            "构造", "分舱", "稳性", "消防", "灭火",
        ],
    },
    # ================================================================
    # Chunk 2: MARPOL Convention — Annex index
    # ================================================================
    {
        "id": "marpol-convention-annex-index",
        "source": "MARPOL",
        "document": "MARPOL",
        "chapter": "ALL",
        "regulation": "MARPOL Convention",
        "title": "MARPOL Convention – Complete Annex Index and Routing Guide",
        "breadcrumb": "MARPOL > Convention Overview > Annex Index",
        "body_text": (
            "MARPOL – International Convention for the Prevention of Pollution from Ships\n"
            "Complete Annex Structure and Routing Guide / 国际防止船舶造成污染公约附则索引\n\n"
            "| Annex | English Title | 中文标题 | Key Regulations |\n"
            "|-------|-------------|---------|------------------|\n"
            "| I | Prevention of Pollution by Oil | 防止油污染 | "
            "Reg.1-39: ODME, OWS, oil record book, SBT, COW |\n"
            "| II | Control of Pollution by Noxious Liquid Substances | 控制有害液体物质污染 | "
            "Reg.1-21: Chemical tanker discharge, P&A manual |\n"
            "| III | Prevention of Pollution by Harmful Substances in Packaged Form | "
            "防止以包装形式运输有害物质的污染 | Reg.1-10: IMDG Code reference |\n"
            "| IV | Prevention of Pollution by Sewage | 防止生活污水污染 | "
            "Reg.1-14: STP, holding tank, discharge limits |\n"
            "| V | Prevention of Pollution by Garbage | 防止垃圾污染 | "
            "Reg.1-10: Garbage management, record book |\n"
            "| VI | Prevention of Air Pollution | 防止大气污染 | "
            "Reg.1-22: SOx, NOx, EEDI, ECA/SECA |\n\n"
            "ROUTING GUIDE / 路由指引:\n"
            "EN: \"oil discharge / ODME / 1/30000\" → Annex I Reg.29/34\n"
            "ZH: \"排油 / 排油监控 / 总排油量\" → 附则I 第29/34条\n\n"
            "EN: \"bilge water / OWS / 15 ppm\" → Annex I Reg.15\n"
            "ZH: \"舱底水 / 油水分离器\" → 附则I 第15条\n\n"
            "EN: \"sewage / black water / STP\" → Annex IV Reg.11\n"
            "ZH: \"生活污水 / 黑水 / 污水处理\" → 附则IV 第11条\n\n"
            "EN: \"garbage / plastic / food waste\" → Annex V Reg.4-6\n"
            "ZH: \"垃圾 / 塑料 / 食物废弃物\" → 附则V 第4-6条\n\n"
            "EN: \"SOx / sulphur / SECA\" → Annex VI Reg.14\n"
            "ZH: \"硫含量 / 低硫燃油 / 排放控制区\" → 附则VI 第14条\n\n"
            "EN: \"NOx / emission tier / ECA\" → Annex VI Reg.13\n"
            "ZH: \"氮氧化物 / 排放等级 / 排放控制区\" → 附则VI 第13条\n\n"
            "EN: \"EEDI / CII / carbon intensity\" → Annex VI Reg.21-28\n"
            "ZH: \"能效指数 / 碳排放强度\" → 附则VI 第21-28条\n\n"
            "COMMON CONFUSION:\n"
            "- Cargo area oil discharge (tankers) → Annex I Reg.34 (NOT Reg.15)\n"
            "- Machinery space bilge → Annex I Reg.15 (NOT Reg.34)\n"
            "- Chemical tanker discharge → Annex II (NOT Annex I)\n"
            "- Ballast water → BWM Convention (NOT MARPOL)"
        ),
        "metadata_extra": {
            "topic": "routing_index",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "MARPOL", "convention", "annex index", "routing guide",
            "oil pollution", "sewage", "garbage", "air pollution",
            "NOx", "SOx", "EEDI", "ECA", "SECA", "OWS", "ODME",
        ],
        "keywords_zh": [
            "国际防止船舶造成污染公约", "MARPOL公约", "附则索引",
            "油污染", "有害液体物质", "包装有害物质", "生活污水", "垃圾",
            "大气污染", "排放控制区", "硫含量", "氮氧化物", "压载水",
            "油类记录簿", "垃圾记录簿", "排放限制",
        ],
    },
    # ================================================================
    # Chunk 3: SOLAS III — Life-saving regulation index
    # ================================================================
    {
        "id": "solas-iii-regulation-index",
        "source": "SOLAS III",
        "document": "SOLAS",
        "chapter": "III",
        "regulation": "SOLAS III",
        "title": "SOLAS III – Life-Saving Appliances: Regulation Index and Routing Guide",
        "breadcrumb": "SOLAS > Chapter III > Regulation Index",
        "body_text": (
            "SOLAS Chapter III – Life-Saving Appliances and Arrangements\n"
            "Regulation Structure and Routing Guide / 救生设备章节索引\n\n"
            "| Section | Regulations | Topic | 中文 |\n"
            "|---------|-----------|-------|------|\n"
            "| Part A | Reg.1-3 | General (definitions, exemptions) | 总则/定义 |\n"
            "| Part B-1 | Reg.6-10 | Ship requirements (general) | 船舶通用要求 |\n"
            "| Part B-2 | Reg.11-18 | Passenger ship requirements | 客船要求 |\n"
            "| Part B-3 | Reg.19-20 | Ro-Ro passenger ship requirements | 滚装客船要求 |\n"
            "| Part B-4 | Reg.21-30 | Cargo ship requirements (old numbering) | 货船要求 |\n"
            "| Part B-4 | Reg.31 | Cargo ship survival craft/rescue boat | 货船救生艇筏 |\n"
            "| Part B-4 | Reg.32 | Cargo ship personal LSA | 货船个人救生设备 |\n"
            "| Part B-4 | Reg.33 | Cargo ship equipment stowage | 设备存放 |\n"
            "| Part B-5 | Reg.34-35 | Special arrangements (tankers, bulk) | 特殊布置 |\n"
            "| Part C | Reg.36-37 | Alternative designs, arrangements | 替代设计 |\n\n"
            "ROUTING GUIDE / 路由指引:\n"
            "EN: \"lifeboat liferaft number cargo ship\" → Reg.31\n"
            "ZH: \"救生艇 救生筏 数量 货船\" → 第31条\n\n"
            "EN: \"lifejacket lifebuoy immersion suit\" → Reg.32\n"
            "ZH: \"救生衣 救生圈 浸水服\" → 第32条\n\n"
            "EN: \"passenger ship evacuation\" → Reg.21-22 + Part B-3\n"
            "ZH: \"客船疏散 / 客船救生设备\" → 第21-22条\n\n"
            "EN: \"davit launching appliance\" → Reg.31 + LSA Code Ch.6\n"
            "ZH: \"吊架 / 降落设备\" → 第31条 + LSA规则第6章\n\n"
            "EN: \"free-fall lifeboat\" → Reg.31 + LSA Code Ch.4\n"
            "ZH: \"自由降落救生艇\" → 第31条 + LSA规则第4章\n\n"
            "EN: \"muster station / assembly station\" → Reg.11/25\n"
            "ZH: \"集合站 / 登乘站\" → 第11/25条\n\n"
            "COMMON CONFUSION:\n"
            "- Equipment SPECIFICATIONS → LSA Code (NOT Chapter III directly)\n"
            "- Equipment CARRIAGE REQUIREMENTS → Chapter III (the regulation)\n"
            "- Tanker-specific LSA → Reg.34 (separate from general cargo ship Reg.31)"
        ),
        "metadata_extra": {
            "topic": "routing_index",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS III", "life-saving", "regulation index", "routing guide",
            "lifeboat", "liferaft", "davit", "lifejacket", "rescue boat",
            "LSA Code", "survival craft", "muster station",
        ],
        "keywords_zh": [
            "救生设备", "救生艇", "救生筏", "救生圈", "救生衣",
            "吊架", "自由降落", "浸水服", "火箭信号", "应急无线电设备",
            "海上求生", "弃船", "集合站", "登乘站",
        ],
    },
    # ================================================================
    # Chunk 4: SOLAS V — Navigation safety regulation index
    # ================================================================
    {
        "id": "solas-v-regulation-index",
        "source": "SOLAS V",
        "document": "SOLAS",
        "chapter": "V",
        "regulation": "SOLAS V",
        "title": "SOLAS V – Safety of Navigation: Regulation Index and Routing Guide",
        "breadcrumb": "SOLAS > Chapter V > Regulation Index",
        "body_text": (
            "SOLAS Chapter V – Safety of Navigation\n"
            "Regulation Structure and Routing Guide / 航行安全章节索引\n\n"
            "| Regulation | Topic | 中文 |\n"
            "|-----------|-------|------|\n"
            "| Reg.5 | Meteorological services | 气象服务 |\n"
            "| Reg.7 | Search and rescue | 搜救服务 |\n"
            "| Reg.10 | Ship routeing | 船舶定线 |\n"
            "| Reg.11 | Ship reporting systems | 船舶报告系统 |\n"
            "| Reg.14 | Ship's manning | 船舶配员 |\n"
            "| Reg.15 | Bridge design principles | 驾驶台设计原则 |\n"
            "| Reg.19 | Carriage requirements — navigation equipment | 航行设备配备要求 |\n"
            "| Reg.19.2 | AIS requirements | AIS配备要求 |\n"
            "| Reg.20 | Voyage data recorder (VDR) | 航行数据记录仪 |\n"
            "| Reg.22 | Navigation bridge visibility | 驾驶台视野 |\n"
            "| Reg.23 | Pilot transfer arrangements | 引航员上下船设备 |\n"
            "| Reg.26 | Steering gear testing | 操舵装置测试 |\n"
            "| Reg.28 | Records of navigation activities | 航行日志 |\n"
            "| Reg.29 | Life-saving signals | 救生信号 |\n"
            "| Reg.31 | Danger messages | 危险信息 |\n"
            "| Reg.34 | Safe navigation and avoidance of dangerous situations | 安全航行 |\n"
            "| Reg.35 | Misuse of distress signals | 遇险信号误用 |\n\n"
            "ROUTING GUIDE / 路由指引:\n"
            "EN: \"AIS / ECDIS / radar / navigation equipment\" → Reg.19\n"
            "ZH: \"AIS / 电子海图 / 雷达 / 航行设备\" → 第19条\n\n"
            "EN: \"VDR / voyage data recorder\" → Reg.20\n"
            "ZH: \"航行数据记录仪 / VDR\" → 第20条\n\n"
            "EN: \"bridge visibility / window\" → Reg.22\n"
            "ZH: \"驾驶台视野 / 舷窗\" → 第22条\n\n"
            "EN: \"pilot ladder / pilot transfer\" → Reg.23\n"
            "ZH: \"引航员梯 / 引航员登乘\" → 第23条\n\n"
            "EN: \"ship routeing / traffic separation\" → Reg.10\n"
            "ZH: \"船舶定线 / 分道通航\" → 第10条\n\n"
            "COMMON CONFUSION:\n"
            "- Radio equipment (GMDSS) → Chapter IV (NOT Chapter V)\n"
            "- Steering gear mechanical requirements → Chapter II-1 Reg.29 (NOT Chapter V)\n"
            "- Steering gear TESTING during voyage → Chapter V Reg.26\n"
            "- AIS as a device → Chapter V Reg.19; AIS for security → Chapter XI-2"
        ),
        "metadata_extra": {
            "topic": "routing_index",
            "ship_type": "all",
            "curated": True,
        },
        "keywords_en": [
            "SOLAS V", "safety of navigation", "regulation index", "routing guide",
            "AIS", "ECDIS", "VDR", "radar", "pilot ladder", "bridge visibility",
            "ship routeing", "navigation equipment",
        ],
        "keywords_zh": [
            "航行安全", "航行设备", "电子海图", "自动识别系统",
            "航行数据记录仪", "回声测深仪", "陀螺罗经", "磁罗经",
            "测速仪", "雷达", "LRIT", "船舶报告系统", "航线计划",
        ],
    },
]


def _build_regulation_row(entry: dict) -> dict:
    return {
        "doc_id": entry["id"],
        "url": "",
        "title": entry["title"],
        "breadcrumb": entry["breadcrumb"],
        "collection": "imo_regulations",
        "document": entry["document"],
        "chapter": entry["chapter"],
        "part": "",
        "regulation": entry["regulation"],
        "paragraph": "",
        "body_text": entry["body_text"],
        "page_type": "curated",
        "version": "curated-v1",
    }


def _build_chunk_row(entry: dict) -> dict:
    keywords_en = entry.get("keywords_en", [])
    keywords_zh = entry.get("keywords_zh", [])
    text_for_embedding = (
        f"{entry['title']}\n\n{entry['body_text']}\n\n"
        f"Keywords: {' '.join(keywords_en)} {' '.join(keywords_zh)}"
    )
    metadata = {
        "title": entry["title"],
        "breadcrumb": entry["breadcrumb"],
        "collection": "imo_regulations",
        "document": entry["document"],
        "regulation_number": entry["regulation"],
        "url": "",
    }
    metadata.update(entry.get("metadata_extra", {}))
    return {
        "chunk_id": f"chunk-{entry['id']}",
        "doc_id": entry["id"],
        "url": "",
        "text": entry["body_text"],
        "text_for_embedding": text_for_embedding,
        "metadata": metadata,
        "token_count": len(text_for_embedding) // 4,
    }


def ingest_to_postgres(db: PostgresDB):
    logger.info("Ingesting routing index chunks to PostgreSQL...")
    for entry in ROUTING_INDEX_DATA:
        reg = _build_regulation_row(entry)
        db.insert_regulation(reg)
        chunk = _build_chunk_row(entry)
        db.insert_chunk(chunk)
        logger.info(f"  PG: {entry['id']}")
    db.conn.commit()
    logger.info(f"PostgreSQL: {len(ROUTING_INDEX_DATA)} routing indexes inserted")


def ingest_to_qdrant():
    logger.info("Ingesting routing index chunks to Qdrant...")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    collection = "imo_regulations"
    if not client.collection_exists(collection):
        logger.error(f"Collection '{collection}' does not exist in Qdrant")
        sys.exit(1)

    base_id = 80000  # routing index offset

    points = []
    for i, entry in enumerate(ROUTING_INDEX_DATA):
        chunk = _build_chunk_row(entry)
        text = chunk["text_for_embedding"]

        response = oai.embeddings.create(
            model=settings.embedding_model,
            input=[text],
            dimensions=settings.embedding_dimensions,
        )
        vector = response.data[0].embedding

        payload = {**chunk["metadata"]}
        payload["chunk_id"] = chunk["chunk_id"]
        payload["doc_id"] = chunk["doc_id"]
        payload["text"] = chunk["text"]
        payload["text_for_embedding"] = chunk["text_for_embedding"]
        payload["token_count"] = chunk["token_count"]

        points.append(PointStruct(
            id=base_id + i,
            vector=vector,
            payload=payload,
        ))
        logger.info(f"  Qdrant: embedded {entry['id']} ({len(vector)} dims)")

    client.upsert(collection_name=collection, points=points)
    logger.info(f"Qdrant: {len(points)} routing index points upserted")


def verify_qdrant_search():
    logger.info("\n=== Qdrant Vector Search Verification ===")
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60,
    )
    oai = openai.OpenAI(api_key=settings.openai_api_key)

    test_queries = [
        ("SOLAS convention chapter structure overview", "solas-convention-chapter-index"),
        ("SOLAS公约章节结构概述", "solas-convention-chapter-index"),
        ("MARPOL annex overview pollution prevention", "marpol-convention-annex-index"),
        ("MARPOL公约附则概述", "marpol-convention-annex-index"),
        ("SOLAS III life-saving regulation structure", "solas-iii-regulation-index"),
        ("救生设备章节结构索引", "solas-iii-regulation-index"),
        ("SOLAS V navigation equipment regulation index", "solas-v-regulation-index"),
        ("航行安全法规索引", "solas-v-regulation-index"),
    ]

    all_pass = True
    for query, expected_doc_id in test_queries:
        resp = oai.embeddings.create(
            model=settings.embedding_model,
            input=[query],
            dimensions=settings.embedding_dimensions,
        )
        vec = resp.data[0].embedding
        results = client.query_points(
            collection_name="imo_regulations",
            query=vec,
            limit=5,
            with_payload=["doc_id"],
        )
        top5_ids = [r.payload.get("doc_id", "") for r in results.points]
        hit = expected_doc_id in top5_ids
        rank = top5_ids.index(expected_doc_id) + 1 if hit else "-"
        status = "PASS" if hit else "FAIL"
        if not hit:
            all_pass = False
        logger.info(f"  {status}: \"{query[:50]}\" -> rank={rank}")
        if not hit:
            logger.info(f"         top-5: {top5_ids}")

    logger.info(f"\nVector search: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return all_pass


def main():
    logger.info("=== Routing Index Curated Chunks Ingestion ===\n")

    db = PostgresDB(settings.database_url)
    try:
        ingest_to_postgres(db)
    finally:
        db.close()

    ingest_to_qdrant()
    verify_qdrant_search()


if __name__ == "__main__":
    main()
