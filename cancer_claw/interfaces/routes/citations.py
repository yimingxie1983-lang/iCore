

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from cancer_claw.config import settings
from cancer_claw.capabilities.toolkit._web_fetch import WebFetchError, fetch_text, html_to_text
from cancer_claw.capabilities.toolkit.builtins.citation_resolve import resolve_ids

logger = structlog.get_logger()
router = APIRouter()

_RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

class CitationResolveRequest(BaseModel):
    ids: list[str] = Field(..., description="PMID 或 DOI 列表（混合允许）")
    fetch_abstract: bool = Field(
        default=False,
        description="是否额外拉摘要片段（多一次 PubMed efetch 往返，约 +300ms）",
    )
    timeout: int = Field(default=15, ge=1, le=60, description="远程请求超时（秒）")

class CitationItem(BaseModel):


    type: str = ""
    id: str = ""
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    year: str = ""
    pubdate: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    pmid: str = ""
    abstract: str = ""
    url: str = ""
    source: str = ""
    is_authority: bool = False
    ok: bool = True
    error: str = ""

class CitationResolveResponse(BaseModel):
    ok: bool = True
    items: list[CitationItem] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    error: str = ""

class PolicyVerifyRequest(BaseModel):
    urls: list[str] = Field(..., description="要核验的政策原文 URL 列表")
    timeout: int = Field(default=15, ge=1, le=60, description="单条抓取超时（秒）")

@router.post(
    "/citations/resolve",
    response_model=CitationResolveResponse,
    summary="批量解析 PMID/DOI → 引用元数据（PubMed + Crossref 实时）",
)
async def resolve_citations(req: CitationResolveRequest) -> CitationResolveResponse:

    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    if len(req.ids) > 200:
        raise HTTPException(
            status_code=400, detail=f"单次最多 200 条，收到 {len(req.ids)}"
        )

    result = await resolve_ids(
        req.ids,
        fetch_abstract=req.fetch_abstract,
        timeout=req.timeout,
    )
    return _to_response(result)

@router.get(
    "/citations/resolve",
    response_model=CitationResolveResponse,
    summary="批量解析 PMID/DOI（GET 快路，逗号分隔）",
)
async def resolve_citations_get(
    ids: str = Query(..., description="逗号分隔的 PMID / DOI 列表"),
    fetch_abstract: bool = Query(default=False),
    timeout: int = Query(default=15, ge=1, le=60),
) -> CitationResolveResponse:

    parsed = [s.strip() for s in ids.split(",") if s.strip()]
    if not parsed:
        raise HTTPException(status_code=400, detail="ids 为空")
    if len(parsed) > 200:
        raise HTTPException(
            status_code=400, detail=f"单次最多 200 条，收到 {len(parsed)}"
        )

    result = await resolve_ids(
        parsed, fetch_abstract=fetch_abstract, timeout=timeout
    )
    return _to_response(result)

def _to_response(result: dict[str, Any]) -> CitationResolveResponse:

    items_in = result.get("items", []) or []
    items_out: list[CitationItem] = []
    for raw in items_in:
        if not isinstance(raw, dict):
            continue
        items_out.append(CitationItem(**{
            "type": str(raw.get("type", "")),
            "id": str(raw.get("id", "")),
            "title": str(raw.get("title", "")),
            "authors": list(raw.get("authors") or []),
            "journal": str(raw.get("journal", "")),
            "year": str(raw.get("year", "")),
            "pubdate": str(raw.get("pubdate", "")),
            "volume": str(raw.get("volume", "")),
            "issue": str(raw.get("issue", "")),
            "pages": str(raw.get("pages", "")),
            "doi": str(raw.get("doi", "")),
            "pmid": str(raw.get("pmid", "")),
            "abstract": str(raw.get("abstract", "")),
            "url": str(raw.get("url", "")),
            "source": str(raw.get("source", "")),
            "ok": bool(raw.get("ok", True)),
            "error": str(raw.get("error", "")),
        }))
    return CitationResolveResponse(
        ok=bool(result.get("ok", True)),
        items=items_out,
        stats=dict(result.get("stats", {})),
        error=str(result.get("error", "")),
    )

def _extract_title(html: str, fallback: str) -> str:

    m = _RE_TITLE.search(html or "")
    if not m:
        return fallback
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    return title or fallback

async def _verify_one_policy_url(url: str, timeout: int) -> dict[str, Any]:

    url = (url or "").strip()
    domain = urlparse(url).netloc
    base = {
        "type": "gov",
        "id": url,
        "url": url,
        "source": domain,
        "authority_sites": settings.citations.authority_sites,
    }
    if not (url.startswith("http://") or url.startswith("https://")):
        return {**base, "ok": False, "error": f"非法 URL（需 http/https）: {url}"}

    is_authority = any(
        domain == s or domain.endswith("." + s)
        for s in settings.citations.authority_sites
    )
    try:
        status, html, final_url = await fetch_text(url, timeout=timeout)
    except WebFetchError as e:
        return {**base, "ok": False, "error": f"无法访问该链接：{e}"}

    if status >= 400:
        hint = "（JS 挑战型 WAF，纯抓取无法核验，请人工点开链接确认）" if status == 412 else ""
        return {**base, "ok": False, "error": f"链接返回 HTTP {status}{hint}"}

    title = _extract_title(html, domain or url)
    text = html_to_text(html)
    snippet = text[:280].strip()
    if len(text) > 280:
        snippet += "…"
    return {
        **base,
        "url": final_url or url,
        "title": title,
        "abstract": snippet,
        "is_authority": is_authority,
        "ok": True,
    }

def _to_policy_response(items: list[dict[str, Any]]) -> CitationResolveResponse:

    out: list[CitationItem] = []
    ok_count = 0
    for raw in items:
        item = CitationItem(
            type=str(raw.get("type", "gov")),
            id=str(raw.get("id", "")),
            title=str(raw.get("title", "")),
            source=str(raw.get("source", "")),
            url=str(raw.get("url", "")),
            abstract=str(raw.get("abstract", "")),
            is_authority=bool(raw.get("is_authority", False)),
            ok=bool(raw.get("ok", True)),
            error=str(raw.get("error", "")),
        )
        if item.ok:
            ok_count += 1
        out.append(item)
    return CitationResolveResponse(
        ok=True,
        items=out,
        stats={"total": len(out), "ok": ok_count, "failed": len(out) - ok_count},
    )

@router.post(
    "/citations/verify-url",
    response_model=CitationResolveResponse,
    summary="核验政策原文 URL → 标题/来源/权威标记/正文摘要（实时抓取）",
)
async def verify_policy_urls(req: PolicyVerifyRequest) -> CitationResolveResponse:

    if not req.urls:
        raise HTTPException(status_code=400, detail="urls 不能为空")
    if len(req.urls) > 50:
        raise HTTPException(status_code=400, detail=f"单次最多 50 条，收到 {len(req.urls)}")

    items = [await _verify_one_policy_url(u, req.timeout) for u in req.urls]
    return _to_policy_response(items)

@router.get(
    "/citations/verify-url",
    response_model=CitationResolveResponse,
    summary="核验政策原文 URL（GET 快路，逗号分隔）",
)
async def verify_policy_urls_get(
    urls: str = Query(..., description="逗号分隔的政策 URL 列表"),
    timeout: int = Query(default=15, ge=1, le=60),
) -> CitationResolveResponse:

    parsed = [s.strip() for s in urls.split(",") if s.strip()]
    if not parsed:
        raise HTTPException(status_code=400, detail="urls 为空")
    if len(parsed) > 50:
        raise HTTPException(status_code=400, detail=f"单次最多 50 条，收到 {len(parsed)}")
    items = [await _verify_one_policy_url(u, timeout) for u in parsed]
    return _to_policy_response(items)
