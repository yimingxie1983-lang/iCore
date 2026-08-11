

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx
import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

logger = structlog.get_logger()

_PMID_RE = re.compile(r"^\d{1,9}$")

_DOI_RE = re.compile(r"^10\.\d{4,9}/[\w\-\.\(\)/:;]+$", re.IGNORECASE)

_ABSTRACT_SNIPPET_CHARS = 320

_PUBMED_BATCH = 100

_DEFAULT_TIMEOUT = 15

_POLITE_UA = "iCore/1.0 (mailto:onekeyjune@gmail.com)"

def _classify_id(raw: str) -> tuple[str, str]:

    s = (raw or "").strip()
    if not s:
        return "unknown", ""


    low = s.lower()
    for prefix in ("pmid:", "pubmed:"):
        if low.startswith(prefix):
            s = s[len(prefix):].strip()
            low = s.lower()
            break
    for prefix in ("doi:",):
        if low.startswith(prefix):
            s = s[len(prefix):].strip()
            low = s.lower()
            break

    for marker in ("doi.org/", "dx.doi.org/"):
        idx = low.find(marker)
        if idx >= 0:
            s = s[idx + len(marker):].strip()
            low = s.lower()
            break
    if "pubmed.ncbi.nlm.nih.gov/" in low:



        tail = s.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        tail = tail.rsplit("/", 1)[-1]
        if tail.isdigit():
            return "pmid", tail

    if _PMID_RE.match(s):
        return "pmid", s
    if _DOI_RE.match(s):
        return "doi", s
    return "unknown", s

def _make_pubmed_url(pmid: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

def _make_doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}"

def _snip(text: str, n: int = _ABSTRACT_SNIPPET_CHARS) -> str:

    if not text:
        return ""
    text = text.strip()
    if len(text) <= n:
        return text
    return text[:n].rstrip() + "…"

async def _fetch_pubmed(
    client: httpx.AsyncClient, pmids: list[str], *, fetch_abstract: bool
) -> dict[str, dict[str, Any]]:

    results: dict[str, dict[str, Any]] = {}
    if not pmids:
        return results


    for start in range(0, len(pmids), _PUBMED_BATCH):
        batch = pmids[start:start + _PUBMED_BATCH]
        try:
            resp = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={"db": "pubmed", "id": ",".join(batch), "retmode": "json"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.warning("pubmed_esummary_failed", batch_size=len(batch), error=str(e))
            continue

        result_block = (payload or {}).get("result") or {}
        for pmid in batch:
            entry = result_block.get(pmid)
            if not isinstance(entry, dict) or entry.get("error"):
                continue

            authors_list = entry.get("authors") or []
            authors = [a.get("name", "") for a in authors_list if isinstance(a, dict)]
            authors = [a for a in authors if a]

            pubdate = entry.get("pubdate") or ""
            year = ""
            if pubdate:
                m = re.match(r"^(\d{4})", pubdate.strip())
                year = m.group(1) if m else ""


            elocation = entry.get("elocationid") or ""
            doi_match = re.search(r"10\.\d{4,9}/[\w\-\.\(\)/:;]+", elocation)
            doi_in_meta = doi_match.group(0) if doi_match else ""

            results[pmid] = {
                "type": "pmid",
                "id": pmid,
                "title": (entry.get("title") or "").strip().rstrip("."),
                "authors": authors,
                "journal": entry.get("source") or entry.get("fulljournalname") or "",
                "year": year,
                "pubdate": pubdate,
                "volume": entry.get("volume") or "",
                "issue": entry.get("issue") or "",
                "pages": entry.get("pages") or "",
                "doi": doi_in_meta,
                "abstract": "",
                "url": _make_pubmed_url(pmid),
                "source": "pubmed",
            }


    if fetch_abstract and results:
        try:
            resp = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                params={
                    "db": "pubmed",
                    "id": ",".join(results.keys()),
                    "rettype": "abstract",
                    "retmode": "xml",
                },
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.text)

            for article in root.iter("PubmedArticle"):
                pmid_el = article.find(".//PMID")
                if pmid_el is None:
                    continue
                pmid = (pmid_el.text or "").strip()
                if pmid not in results:
                    continue
                abstract_parts: list[str] = []
                for at in article.iter("AbstractText"):
                    label = at.attrib.get("Label", "").strip()
                    text = "".join(at.itertext()).strip()
                    if not text:
                        continue
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
                if abstract_parts:
                    results[pmid]["abstract"] = _snip(" ".join(abstract_parts))
        except Exception as e:
            logger.warning("pubmed_efetch_abstract_failed", error=str(e))

    return results

async def _fetch_crossref(
    client: httpx.AsyncClient, dois: list[str]
) -> dict[str, dict[str, Any]]:

    results: dict[str, dict[str, Any]] = {}
    if not dois:
        return results

    headers = {"User-Agent": _POLITE_UA, "Accept": "application/json"}
    for doi in dois:
        try:
            resp = await client.get(
                f"https://api.crossref.org/works/{doi}", headers=headers
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.warning("crossref_failed", doi=doi, error=str(e))
            continue

        msg = (payload or {}).get("message") or {}
        title_list = msg.get("title") or []
        title = title_list[0].strip() if title_list else ""

        container = msg.get("container-title") or []
        journal = container[0].strip() if container else ""


        authors_raw = msg.get("author") or []
        authors: list[str] = []
        for a in authors_raw:
            if not isinstance(a, dict):
                continue
            family = (a.get("family") or "").strip()
            given = (a.get("given") or "").strip()
            if family and given:
                authors.append(f"{family} {given[0]}")
            elif family:
                authors.append(family)
            elif a.get("name"):
                authors.append(a["name"].strip())


        year = ""
        for key in ("published-print", "published-online", "issued", "published"):
            block = msg.get(key)
            if isinstance(block, dict):
                parts = block.get("date-parts") or []
                if parts and parts[0]:
                    year = str(parts[0][0])
                    break


        pmid = ""
        for rel in (msg.get("relation") or {}).get("has-relation") or []:
            if isinstance(rel, dict) and rel.get("id-type") == "pmid":
                pmid = rel.get("id", "")
                break

        abstract = msg.get("abstract") or ""

        abstract = re.sub(r"<[^>]+>", " ", abstract)
        abstract = re.sub(r"\s+", " ", abstract).strip()

        results[doi] = {
            "type": "doi",
            "id": doi,
            "title": title,
            "authors": authors,
            "journal": journal,
            "year": year,
            "pubdate": "",
            "volume": msg.get("volume") or "",
            "issue": msg.get("issue") or "",
            "pages": msg.get("page") or "",
            "doi": doi,
            "pmid": pmid,
            "abstract": _snip(abstract),
            "url": _make_doi_url(doi),
            "source": "crossref",
        }

    return results

class CitationResolveTool(BaseTool):


    @property
    def name(self) -> str:
        return "citation_resolve"

    @property
    def description(self) -> str:
        return (
            "把 PMID / DOI 列表解析成可验证的引用元数据（标题 / 作者 / 期刊 / 年份 / "
            "摘要 / 链接），数据源 PubMed 与 Crossref，**专治幻觉引用**。"
            "交付综述、起草 SCI、引用临床指南前应主动批量调用本工具核对每条 id 真实存在；"
            "前端会把 [PMID:xxx] / [DOI:xxx] 渲染成可点击气泡，气泡卡片就走这个接口。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "citation_resolve",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ids": {
                            "description": (
                                "要解析的引用 id 列表。支持 PMID（纯数字）、DOI（10.xxx/yyy）、"
                                "前缀写法（'PMID:xxx' / 'DOI:xxx'）以及 pubmed.ncbi.nlm.nih.gov / "
                                "doi.org URL；混合输入会自动按类型分流。"
                                "也可以传单个字符串（用逗号分隔多个 id）。"
                            ),
                            "oneOf": [
                                {"type": "array", "items": {"type": "string"}},
                                {"type": "string"},
                            ],
                        },
                        "fetch_abstract": {
                            "type": "boolean",
                            "description": "是否额外拉摘要片段（默认 false，省一次 PubMed efetch 往返）",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "请求超时秒数（默认 15）",
                            "default": _DEFAULT_TIMEOUT,
                        },
                    },
                    "required": ["ids"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_ids = kwargs.get("ids")
        if raw_ids is None:
            return ToolResult(success=False, error="ids 不能为空")


        if isinstance(raw_ids, str):
            ids_list = [s.strip() for s in raw_ids.split(",") if s.strip()]
        elif isinstance(raw_ids, list):
            ids_list = [str(s).strip() for s in raw_ids if str(s).strip()]
        else:
            return ToolResult(
                success=False, error=f"ids 应为字符串或列表，收到 {type(raw_ids).__name__}"
            )

        if not ids_list:
            return ToolResult(success=False, error="ids 解析后为空")

        fetch_abstract = bool(kwargs.get("fetch_abstract", False))
        timeout = int(kwargs.get("timeout") or _DEFAULT_TIMEOUT)


        pmids: list[str] = []
        dois: list[str] = []
        invalid: list[tuple[str, str]] = []

        order: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for raw in ids_list:
            kind, normalized = _classify_id(raw)
            if kind == "unknown":
                invalid.append((raw, normalized))
                order.append(("unknown", normalized or raw, raw))
                continue
            key = (kind, normalized)
            if key in seen:
                order.append((kind, normalized, raw))
                continue
            seen.add(key)
            if kind == "pmid":
                pmids.append(normalized)
            else:
                dois.append(normalized)
            order.append((kind, normalized, raw))


        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                         headers={"User-Agent": _POLITE_UA}) as client:
                pubmed_map = await _fetch_pubmed(client, pmids, fetch_abstract=fetch_abstract)
                crossref_map = await _fetch_crossref(client, dois)
        except Exception as e:
            return ToolResult(success=False, error=f"远程查询失败: {e}")


        items: list[dict[str, Any]] = []
        emitted: set[tuple[str, str]] = set()
        n_resolved = 0
        n_not_found = 0
        for kind, normalized, original in order:
            key = (kind, normalized)
            if key in emitted:
                continue
            emitted.add(key)

            if kind == "unknown":
                items.append({
                    "type": "unknown",
                    "id": original,
                    "ok": False,
                    "error": "无法识别为 PMID 或 DOI（PMID 应为纯数字，DOI 应以 10. 开头含 /）",
                })
                continue

            data_map = pubmed_map if kind == "pmid" else crossref_map
            meta = data_map.get(normalized)
            if meta is None:
                items.append({
                    "type": kind,
                    "id": normalized,
                    "ok": False,
                    "error": "未在远程数据库找到该条目（可能是错号 / 已撤稿 / 数据尚未索引）",
                    "url": _make_pubmed_url(normalized) if kind == "pmid" else _make_doi_url(normalized),
                })
                n_not_found += 1
            else:
                meta_with_ok = dict(meta)
                meta_with_ok["ok"] = True
                items.append(meta_with_ok)
                n_resolved += 1

        stats = {
            "requested": len(order),
            "unique": len(seen) + len(invalid),
            "resolved": n_resolved,
            "not_found": n_not_found,
            "invalid": len(invalid),
        }


        output = _render_output(items, stats)
        return ToolResult(success=True, output=output, data={"items": items, "stats": stats})

def _render_output(items: list[dict[str, Any]], stats: dict[str, int]) -> str:

    lines: list[str] = []
    lines.append(
        f"已解析 {stats['resolved']} / {stats['requested']} 条引用 "
        f"（未找到 {stats['not_found']}，非法 {stats['invalid']}）"
    )
    for i, it in enumerate(items, 1):
        if not it.get("ok"):
            lines.append(f"{i}. ❌ [{it['type']}:{it['id']}] — {it.get('error', '失败')}")
            continue
        authors = it.get("authors") or []
        if len(authors) > 3:
            author_str = ", ".join(authors[:3]) + ", et al"
        else:
            author_str = ", ".join(authors) if authors else "(no authors)"
        bib = f"{author_str}. {it.get('title') or '(no title)'}."
        journal_bits = [it.get("journal", "")]
        if it.get("year"):
            journal_bits.append(it["year"])
        vol = it.get("volume", "")
        issue = it.get("issue", "")
        pages = it.get("pages", "")
        if vol or pages:
            cite = vol + (f"({issue})" if issue else "") + (f":{pages}" if pages else "")
            journal_bits.append(cite)
        journal_line = "; ".join([b for b in journal_bits if b])
        if journal_line:
            bib += " " + journal_line + "."
        marker = "PMID" if it["type"] == "pmid" else "DOI"
        lines.append(
            f"{i}. ✅ {bib} [{marker}:{it['id']}]({it.get('url', '')})"
        )
        if it.get("abstract"):
            lines.append(f"   摘要: {it['abstract']}")
    return "\n".join(lines)

async def resolve_ids(
    ids: list[str], *, fetch_abstract: bool = False, timeout: int = _DEFAULT_TIMEOUT
) -> dict[str, Any]:

    tool = CitationResolveTool()
    result = await tool.execute(ids=ids, fetch_abstract=fetch_abstract, timeout=timeout)
    return {
        "ok": result.success,
        "items": result.data.get("items", []),
        "stats": result.data.get("stats", {}),
        "error": result.error if not result.success else "",
    }
