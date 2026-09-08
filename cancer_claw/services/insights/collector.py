"""行业资讯采集器：RSS / arXiv / PubMed → insight_items。

设计要点：
- 纯标准库 + httpx，无新增第三方依赖；
- 按 URL 去重（数据库唯一索引兜底），单源失败不影响其它源；
- 可选 AI 中文摘要（复用 model_router.chat_simple），失败自动降级保留原文摘要；
- 后台循环由 runtime.bootstrap 启动，shutdown 取消。
"""

from __future__ import annotations

import asyncio
import email.utils
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx
import structlog

from cancer_claw.config import settings
from cancer_claw.db import get_db

logger = structlog.get_logger()

COLLECT_INTERVAL_MIN = 30
FETCH_TIMEOUT = 20
MAX_PER_SOURCE = 15
MAX_SUMMARIES_PER_RUN = 8
RETENTION_DAYS = 7

def _google_news_rss(query: str) -> str:
    from urllib.parse import urlencode

    return (
        "https://news.google.com/rss/search?"
        + urlencode({"q": query + " when:7d", "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-HanS"})
    )


DEFAULT_SOURCES: list[dict[str, Any]] = [
    {
        "name": "arXiv · 医学 AI（q-bio / cs.AI）",
        "kind": "arxiv",
        "url": '(cat:q-bio.QM OR cat:cs.AI) AND (all:"medical" OR all:"clinical")',
        "category": "research",
    },
    {
        "name": "PubMed · Artificial Intelligence",
        "kind": "pubmed",
        "url": 'artificial intelligence[Title] AND (medicine[Title/Abstract] OR clinical[Title/Abstract])',
        "category": "research",
    },
    {
        "name": "Nature Medicine RSS",
        "kind": "rss",
        "url": "https://www.nature.com/nm.rss",
        "category": "research",
    },
    {
        "name": "The Lancet Digital Health RSS",
        "kind": "rss",
        "url": "https://www.thelancet.com/digital-health/rssfeed/CurrentIssue",
        "category": "research",
    },
    # —— 覆盖空缺类别：Google News 中文资讯（无需 API Key，稳定可用）——
    {
        "name": "政策监管 · 医学 AI",
        "kind": "rss",
        "url": _google_news_rss("(NMPA OR FDA OR 药监局 OR 卫健委) 人工智能 医疗"),
        "category": "policy",
    },
    {
        "name": "产业动态 · 医学 AI",
        "kind": "rss",
        "url": _google_news_rss("医疗人工智能 OR 医学AI 产业"),
        "category": "industry",
    },
    {
        "name": "融资上市 · 医学 AI",
        "kind": "rss",
        "url": _google_news_rss("医疗人工智能 OR 医学AI 融资 OR上市"),
        "category": "funding",
    },
    {
        "name": "会议活动 · 医学 AI",
        "kind": "rss",
        "url": _google_news_rss("医疗人工智能 OR 医学AI 大会 OR 论坛 OR 峰会"),
        "category": "conference",
    },
]

_loop_task: asyncio.Task | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def ensure_default_sources() -> int:
    """按类别补缺播种默认采集源（幂等：每个类别已有源则跳过）。"""
    db = await get_db()
    cur = await db.execute("SELECT DISTINCT category FROM insight_sources")
    have = {r[0] for r in await cur.fetchall()}
    added = 0
    for s in DEFAULT_SOURCES:
        if s["category"] in have:
            continue
        await db.execute(
            "INSERT INTO insight_sources (name, kind, url, category, enabled) "
            "VALUES (?, ?, ?, ?, 1)",
            (s["name"], s["kind"], s["url"], s["category"]),
        )
        have.add(s["category"])
        added += 1
    if added:
        await db.commit()
        logger.info("insights_sources_seeded", added=added)
    return added


# ---------------------------------------------------------------- 解析层

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").replace("&amp;", "&").strip()


def _clean_summary(text: str, max_len: int = 400) -> str:
    t = _strip_html(text)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(el: Any, name: str) -> str:
    """按 localname 取子元素文本（兼容 RSS 2.0 与 RSS 1.0/RDF 命名空间）。"""
    for ch in el:
        if _local_name(ch.tag) == name:
            return (ch.text or "").strip()
    return ""


def _parse_rss(xml_text: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue
        title = _child_text(item, "title")
        link = _child_text(item, "link")
        if not title or not link:
            continue
        pub_raw = _child_text(item, "pubDate") or _child_text(item, "date")
        published = ""
        if pub_raw:
            try:
                published = email.utils.parsedate_to_datetime(pub_raw).astimezone(
                    timezone.utc
                ).isoformat(timespec="seconds")
            except Exception:
                published = ""
        media_name = _child_text(item, "source") or source["name"]
        items.append(
            {
                "title": title,
                "summary": _clean_summary(_child_text(item, "description")),
                "source": media_name,
                "url": link,
                "category": source.get("category") or "research",
                "tags": ["RSS"],
                "published_at": published or _now_iso(),
            }
        )
        if len(items) >= MAX_PER_SOURCE:
            break
    return items


def _parse_arxiv(xml_text: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link = ""
        for l in entry.findall("a:link", ns):
            if l.get("type") == "application/pdf" or not link:
                link = l.get("href") or ""
        if not title or not link:
            continue
        published = entry.findtext("a:published", default="", namespaces=ns) or ""
        items.append(
            {
                "title": re.sub(r"\s+", " ", title),
                "summary": _clean_summary(entry.findtext("a:summary", default="", namespaces=ns) or ""),
                "source": "arXiv",
                "url": link,
                "category": source.get("category") or "research",
                "tags": ["arXiv"],
                "published_at": (published[:19] + "+00:00") if published else _now_iso(),
            }
        )
        if len(items) >= MAX_PER_SOURCE:
            break
    return items


async def _fetch_pubmed(query: str) -> list[dict[str, Any]]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
        esearch = await client.get(
            f"{base}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmax": MAX_PER_SOURCE,
                "sort": "date",
                "retmode": "json",
            },
        )
        esearch.raise_for_status()
        ids = (esearch.json().get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return []
        efetch = await client.get(
            f"{base}/efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
        )
        efetch.raise_for_status()
    root = ET.fromstring(efetch.text)
    items: list[dict[str, Any]] = []
    for art in root.iter("PubmedArticle"):
        pmid_el = art.find(".//PubmedArticleSet/PubmedArticle/MedlineCitation/PMID")
        if pmid_el is None:
            for el in art.iter("PMID"):
                pmid_el = el
                break
        pmid = (pmid_el.text or "").strip() if pmid_el is not None else ""
        title_el = art.find(".//ArticleTitle")
        title = _strip_html(title_el.text or "") if title_el is not None and title_el.text else ""
        if not title or not pmid:
            continue
        abstract = " ".join(
            (t.text or "") for t in art.iter("AbstractText")
        )
        year = art.findtext(".//ArticleDate/Year") or art.findtext(".//PubDate/Year") or ""
        month = art.findtext(".//ArticleDate/Month") or art.findtext(".//PubDate/Month") or "1"
        day = art.findtext(".//ArticleDate/Day") or art.findtext(".//PubDate/Day") or "1"
        try:
            dt = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
            published = dt.isoformat(timespec="seconds")
        except Exception:
            published = _now_iso()
        items.append(
            {
                "title": title,
                "summary": _clean_summary(abstract),
                "source": "PubMed",
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "category": "research",
                "tags": ["PubMed"],
                "published_at": published,
            }
        )
    return items


async def _fetch_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    kind = source["kind"]
    if kind == "pubmed":
        return await _fetch_pubmed(source["url"])
    if kind == "arxiv":
        url = (
            "http://export.arxiv.org/api/query?search_query="
            + quote(source["url"])
            + f"&sortBy=submittedDate&sortOrder=descending&max_results={MAX_PER_SOURCE}"
        )
    else:
        url = source["url"]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 iCoreInsights/0.1"
        )
    }
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, headers=headers, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code == 429:
            # arXiv 等源偶发限流：等待后重试一次
            await asyncio.sleep(5)
            resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text
    if kind == "arxiv":
        return _parse_arxiv(text, source)
    return _parse_rss(text, source)


# ---------------------------------------------------------------- AI 摘要

_SUMMARY_PROMPT = (
    "你是医学 AI 行业资讯编辑。请把下面这条英文/原始资讯压缩成 80~120 字的简体中文摘要，"
    "保留关键事实（对象、方法、结论/影响），不要编造，直接输出摘要正文：\n\n"
    "标题：{title}\n原文摘要：{summary}"
)


def _looks_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


async def _ai_summarize(item: dict[str, Any]) -> str | None:
    try:
        from cancer_claw.services.model_router import get_router

        messages = [
            {
                "role": "user",
                "content": _SUMMARY_PROMPT.format(
                    title=item["title"][:200], summary=(item.get("summary") or "")[:1500]
                ),
            }
        ]
        resp = await asyncio.wait_for(
            get_router().chat_simple(messages, task_type="general"), timeout=40
        )
        text = (resp.content or "").strip() if hasattr(resp, "content") else ""
        if text and len(text) >= 20:
            return text[:500]
    except Exception as e:
        logger.info("insights_ai_summary_skipped", url=item.get("url"), error=str(e))
    return None


# ---------------------------------------------------------------- 主流程

async def collect_now() -> dict[str, int]:
    db = await get_db()
    cur = await db.execute("SELECT id, name, kind, url, category FROM insight_sources WHERE enabled = 1")
    sources = [
        {"id": r[0], "name": r[1], "kind": r[2], "url": r[3], "category": r[4]}
        for r in await cur.fetchall()
    ]

    results = await asyncio.gather(
        *(_fetch_source(s) for s in sources), return_exceptions=True
    )
    fetched = 0
    batch: dict[str, dict[str, Any]] = {}
    for src, res in zip(sources, results):
        if isinstance(res, Exception):
            logger.warning("insights_source_failed", source=src["name"], error=str(res))
            continue
        fetched += len(res)
        for it in res:
            u = it.get("url") or ""
            if u and u not in batch:
                batch[u] = it

    if not batch:
        return {
            "sources": len(sources),
            "fetched": fetched,
            "inserted": 0,
            "summarized": 0,
        }

    urls = list(batch.keys())
    existing: set[str] = set()
    for i in range(0, len(urls), 50):
        chunk = urls[i : i + 50]
        qs = ",".join("?" for _ in chunk)
        cur = await db.execute(
            f"SELECT url FROM insight_items WHERE url IN ({qs})", tuple(chunk)
        )
        existing.update(r[0] for r in await cur.fetchall())

    retention_cutoff = (
        datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    ).isoformat(timespec="seconds")
    fresh = [
        batch[u]
        for u in urls
        if u not in existing and str(batch[u].get("published_at") or "") >= retention_cutoff
    ]

    summarized = 0
    ai_on = bool(getattr(settings.features, "insights_ai_summary", True))
    for it in fresh:
        summary = it.get("summary") or ""
        if ai_on and summarized < MAX_SUMMARIES_PER_RUN and not _looks_chinese(summary):
            zh = await _ai_summarize(it)
            if zh:
                it["summary"] = zh
                summarized += 1
        await db.execute(
            "INSERT OR IGNORE INTO insight_items "
            "(title, summary, source, url, category, tags, published_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                it["title"],
                it.get("summary") or "",
                it.get("source") or "",
                it.get("url") or "",
                it.get("category") or "research",
                json.dumps(it.get("tags") or [], ensure_ascii=False),
                it.get("published_at") or _now_iso(),
            ),
        )
    await db.commit()
    inserted = len(fresh)

    logger.info(
        "insights_collected",
        sources=len(sources),
        fetched=fetched,
        inserted=inserted,
        summarized=summarized,
    )
    return {
        "sources": len(sources),
        "fetched": fetched,
        "inserted": inserted,
        "summarized": summarized,
    }


async def _collection_loop() -> None:
    # 启动后先等一小段时间，让主服务完成初始化，再进入周期采集
    await asyncio.sleep(20)
    while True:
        try:
            await collect_now()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("insights_collect_loop_error", error=str(e))
        await asyncio.sleep(COLLECT_INTERVAL_MIN * 60)


def start_insights_loop() -> None:
    global _loop_task
    if not bool(getattr(settings.features, "insights_collect", True)):
        logger.info("insights_collect_disabled")
        return
    if _loop_task is not None and not _loop_task.done():
        return
    _loop_task = asyncio.create_task(_collection_loop())
    logger.info("insights_collect_loop_started", interval_min=COLLECT_INTERVAL_MIN)


async def stop_insights_loop() -> None:
    global _loop_task
    if _loop_task is None:
        return
    _loop_task.cancel()
    try:
        await _loop_task
    except (asyncio.CancelledError, Exception):
        pass
    _loop_task = None
