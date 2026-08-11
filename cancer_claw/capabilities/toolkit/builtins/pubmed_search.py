

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.builtins.citation_resolve import (
    _DEFAULT_TIMEOUT,
    _POLITE_UA,
    _fetch_pubmed,
)

logger = structlog.get_logger()

_MAX_RESULTS_HARD_CAP = 50

_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

_OUTPUT_ABSTRACT_PREVIEW = 160

def _get_api_key() -> str:

    return os.environ.get("NCBI_API_KEY", "").strip()

async def _esearch(
    client: httpx.AsyncClient,
    query: str,
    max_results: int,
    sort: str,
) -> dict[str, Any]:

    params: dict[str, str] = {
        "db": "pubmed",
        "term": query,
        "retmax": str(max_results),
        "retmode": "json",
        "sort": sort,
    }
    api_key = _get_api_key()
    if api_key:
        params["api_key"] = api_key

    resp = await client.get(_ESEARCH_URL, params=params)
    resp.raise_for_status()
    payload = resp.json() or {}
    er = payload.get("esearchresult") or {}



    return {
        "idlist": [str(x) for x in (er.get("idlist") or [])],
        "count": int(er.get("count") or 0),
        "retmax": int(er.get("retmax") or 0),
        "query_translation": er.get("querytranslation") or "",
        "warnings": er.get("warninglist") or {},
        "errors": er.get("errorlist") or {},
    }

def _build_web_url(query: str) -> str:

    from urllib.parse import quote_plus

    return f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}"

def _render_output(
    query: str,
    total_count: int,
    items: list[dict[str, Any]],
    query_translation: str,
    web_url: str,
) -> str:

    lines: list[str] = []
    lines.append(
        f"PubMed 检索：`{query}` — 总命中 **{total_count}** 条，本次返回 **{len(items)}** 条。"
    )
    if not items:
        lines.append("")
        lines.append("（未找到任何匹配的文献。请放宽查询或检查拼写。）")
    else:
        lines.append("")
        for i, it in enumerate(items, 1):
            authors = it.get("authors") or []
            first_author = authors[0] if authors else "Unknown"
            et_al = " et al." if len(authors) > 1 else ""
            title = (it.get("title") or "").strip().rstrip(".")
            journal = it.get("journal") or "?"
            year = it.get("year") or "?"
            pmid = it.get("id") or ""
            line = (
                f"{i}. [PMID:{pmid}] **{title}**  \n"
                f"   {first_author}{et_al} · *{journal}* · {year}"
            )
            doi = it.get("doi") or ""
            if doi:
                line += f" · DOI:{doi}"
            lines.append(line)

            ab = (it.get("abstract") or "").strip()
            if ab:
                if len(ab) > _OUTPUT_ABSTRACT_PREVIEW:
                    ab = ab[:_OUTPUT_ABSTRACT_PREVIEW] + "…"
                lines.append(f"   > {ab}")

    if query_translation:
        lines.append("")
        lines.append(f"_PubMed 实际查询_：`{query_translation}`")
    lines.append(f"_网页查看完整结果_：{web_url}")
    return "\n".join(lines)

class PubMedSearchTool(BaseTool):


    @property
    def name(self) -> str:
        return "pubmed_search"

    @property
    def description(self) -> str:
        return (
            "在 PubMed（NCBI 官方 E-utilities）按关键词检索文献，返回结构化列表"
            "（标题 / 作者 / 期刊 / 年份 / DOI / 可选摘要 / 直接的 PubMed 链接）。"
            "\n\n"
            "**优先级铁律**：凡是要查文献，**优先用本工具**，不要用 http_fetch 自己"
            "拼 URL 去爬 pubmed.ncbi.nlm.nih.gov 网页版——网页版有 Akamai 防爬会 403。"
            "本工具走 NCBI 官方 API host（eutils.ncbi.nlm.nih.gov），有 polite UA + "
            "可选 NCBI API key，命中率与稳定性都更好。\n"
            "已经知道 PMID / DOI 想取 metadata → 改用 `citation_resolve`（无需检索）。"
            "\n\n"
            "**支持 PubMed 检索语法**：可以用 field tag，如 "
            "`EGFR[Title/Abstract] AND osimertinib[All Fields] AND 2020:2024[PDAT]`、"
            "`(NSCLC[MeSH] OR \"non-small cell lung cancer\") AND first-line[Title]` 等。"
            "更简单的查询直接传自然语言关键词即可，PubMed 会自动做 MeSH 扩展。"
            "\n\n"
            "**返回**：output 是给模型读的简洁 markdown 摘要清单；data.items 是完整"
            "结构化数据（{pmid, title, authors, journal, year, doi, abstract?, url}）。"
            "fetch_abstract=True 时每条会附 320 字摘要片段（多一次 efetch 往返 ~300ms）。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "pubmed_search",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "PubMed 检索字符串。支持 field tag 如 [Title/Abstract] / "
                                "[MeSH] / [PDAT] / [Author] 等；也支持自然语言关键词。"
                                "示例：'osimertinib first-line EGFR NSCLC 2020:2024[PDAT]'"
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": (
                                f"返回的条目上限，默认 20，硬上限 {_MAX_RESULTS_HARD_CAP}。"
                                "需要更多请分页（暂未支持，留意 total_count）。"
                            ),
                            "default": 20,
                            "minimum": 1,
                            "maximum": _MAX_RESULTS_HARD_CAP,
                        },
                        "sort": {
                            "type": "string",
                            "enum": ["relevance", "pub_date", "first_author"],
                            "description": (
                                "排序：relevance（PubMed Best Match，默认）/ "
                                "pub_date（最新优先）/ first_author（按第一作者姓氏）"
                            ),
                            "default": "relevance",
                        },
                        "fetch_abstract": {
                            "type": "boolean",
                            "description": (
                                "是否同时拉摘要片段（多一次 efetch 往返）。"
                                "做综述/精读时建议 True；只是想看候选清单时 False。"
                            ),
                            "default": False,
                        },
                        "date_range": {
                            "type": "string",
                            "description": (
                                "可选年份过滤，形如 '2020:2024'（包含两端）；"
                                "会作为 [PDAT] 字段追加到 query 末尾。"
                                "如果 query 已经带 PDAT 字段了，本参数会被忽略。"
                            ),
                            "default": "",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": f"请求超时（秒），默认 {_DEFAULT_TIMEOUT}",
                            "default": _DEFAULT_TIMEOUT,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = (kwargs.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, error="query 不能为空")

        max_results = int(kwargs.get("max_results") or 20)
        if max_results < 1:
            max_results = 1
        if max_results > _MAX_RESULTS_HARD_CAP:
            max_results = _MAX_RESULTS_HARD_CAP

        sort = (kwargs.get("sort") or "relevance").strip().lower()
        if sort not in {"relevance", "pub_date", "first_author"}:
            sort = "relevance"

        fetch_abstract = bool(kwargs.get("fetch_abstract", False))
        timeout = int(kwargs.get("timeout") or _DEFAULT_TIMEOUT)


        date_range = (kwargs.get("date_range") or "").strip()
        if date_range and "[pdat]" not in query.lower() and "[PDAT]" not in query:
            query_with_date = f"{query} AND {date_range}[PDAT]"
        else:
            query_with_date = query

        headers = {"User-Agent": _POLITE_UA, "Accept": "application/json"}

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
            ) as client:

                try:
                    search_result = await _esearch(
                        client, query_with_date, max_results, sort
                    )
                except httpx.HTTPStatusError as e:
                    logger.warning(
                        "pubmed_esearch_http_error",
                        status=e.response.status_code,
                        query=query_with_date,
                    )
                    return ToolResult(
                        success=False,
                        error=(
                            f"PubMed esearch 失败：HTTP {e.response.status_code}。"
                            "若长期出现 4xx，请检查 query 语法或暂缓 1 分钟（频次限制）。"
                        ),
                    )
                except httpx.HTTPError as e:
                    logger.warning("pubmed_esearch_net_error", error=str(e))
                    return ToolResult(
                        success=False,
                        error=f"PubMed esearch 网络异常：{e}",
                    )

                pmids = search_result["idlist"]
                total_count = search_result["count"]
                query_translation = search_result["query_translation"]



                if not pmids:
                    web_url = _build_web_url(query_with_date)
                    output = _render_output(
                        query_with_date, total_count, [], query_translation, web_url
                    )
                    return ToolResult(
                        success=True,
                        output=output,
                        data={
                            "query": query_with_date,
                            "total_count": total_count,
                            "returned": 0,
                            "items": [],
                            "query_translation": query_translation,
                            "web_url": web_url,
                        },
                    )



                meta_by_pmid = await _fetch_pubmed(
                    client, pmids, fetch_abstract=fetch_abstract
                )
        except httpx.TimeoutException:
            return ToolResult(success=False, error=f"PubMed 请求超时（{timeout} 秒）")
        except Exception as e:
            logger.warning("pubmed_search_unexpected", error=str(e), error_type=type(e).__name__)
            return ToolResult(success=False, error=f"PubMed 检索异常: {e}")


        items: list[dict[str, Any]] = []
        for pmid in pmids:
            entry = meta_by_pmid.get(pmid)
            if entry:
                items.append(entry)
            else:

                items.append(
                    {
                        "type": "pmid",
                        "id": pmid,
                        "title": "(esummary 未返回元数据)",
                        "authors": [],
                        "journal": "",
                        "year": "",
                        "doi": "",
                        "abstract": "",
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        "source": "pubmed",
                    }
                )

        web_url = _build_web_url(query_with_date)
        output = _render_output(
            query_with_date, total_count, items, query_translation, web_url
        )
        return ToolResult(
            success=True,
            output=output,
            data={
                "query": query_with_date,
                "total_count": total_count,
                "returned": len(items),
                "items": items,
                "query_translation": query_translation,
                "web_url": web_url,
            },
        )
