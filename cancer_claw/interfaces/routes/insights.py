from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cancer_claw.db import get_db
from cancer_claw.services.identity.deps import get_current_user, is_admin

logger = structlog.get_logger()

router = APIRouter(dependencies=[Depends(get_current_user)])

CATEGORY_LABELS: dict[str, str] = {
    "policy": "政策监管",
    "research": "文献前沿",
    "industry": "产业动态",
    "funding": "融资上市",
    "conference": "会议活动",
}

SOURCE_KINDS = {"rss", "arxiv", "pubmed"}
RETENTION_DAYS = 7
MAX_SUBSCRIPTIONS_PER_USER = 20


class InsightItem(BaseModel):
    id: int
    title: str
    summary: str = ""
    source: str = ""
    url: str = ""
    category: str = "industry"
    category_label: str = "产业动态"
    tags: list[str] = Field(default_factory=list)
    published_at: str


class InsightListResp(BaseModel):
    total: int
    items: list[InsightItem]


class InsightStatsResp(BaseModel):
    today: int
    week: int
    total: int
    by_category: dict[str, int]


class SeedResp(BaseModel):
    ok: bool
    inserted: int


class SubscriptionItem(BaseModel):
    id: int
    keyword: str
    hits_week: int = 0
    created_at: str | None = None


class SubscriptionListResp(BaseModel):
    total: int
    items: list[SubscriptionItem]


class SubscriptionCreateReq(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=40, description="订阅关键词")


class SubscriptionHitsResp(BaseModel):
    total_24h: int
    items: list[SubscriptionItem]


class SourceItem(BaseModel):
    id: int
    name: str
    kind: str
    url: str
    category: str
    enabled: bool
    created_at: str | None = None


class SourceListResp(BaseModel):
    total: int
    items: list[SourceItem]


class SourceCreateReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    kind: str
    url: str = Field(..., min_length=1, max_length=500)
    category: str = "research"
    enabled: bool = True


class CollectResp(BaseModel):
    sources: int
    fetched: int
    inserted: int
    summarized: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rowcount(cur: Any) -> int:
    rc = getattr(cur, "rowcount", None)
    try:
        return int(rc) if rc is not None and int(rc) > 0 else 0
    except Exception:
        return 0


def _row_to_item(row: Any) -> InsightItem:
    (
        item_id,
        title,
        summary,
        source,
        url,
        category,
        tags_raw,
        published_at,
    ) = row
    try:
        tags = json.loads(tags_raw or "[]")
        if not isinstance(tags, list):
            tags = []
        tags = [str(t) for t in tags][:8]
    except Exception:
        tags = []
    return InsightItem(
        id=int(item_id),
        title=title,
        summary=summary or "",
        source=source or "",
        url=url or "",
        category=category,
        category_label=CATEGORY_LABELS.get(category, category),
        tags=tags,
        published_at=published_at,
    )


async def _prune_expired(db: Any) -> int:
    cutoff = (_now() - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")
    cur = await db.execute(
        "DELETE FROM insight_items WHERE published_at < ?", (cutoff,)
    )
    if _rowcount(cur):
        await db.commit()
        return _rowcount(cur)
    return 0


async def _count_items(db: Any) -> int:
    cur = await db.execute("SELECT COUNT(*) FROM insight_items")
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def _seed_demo_items(db: Any) -> int:
    now = _now()

    def ago(hours: float) -> str:
        return (now - timedelta(hours=hours)).isoformat(timespec="seconds")

    # 演示数据
    items: list[dict] = [
        {
            "title": "NMPA 发布人工智能医疗器械注册审查指导原则更新",
            "summary": "国家药监局更新 AI 医疗器械注册审查要求，明确算法迭代场景下的变更申报路径与临床评价证据层级，对影像组学类产品的可解释性提出更细颗粒度要求。",
            "source": "国家药品监督管理局",
            "url": "https://www.nmpa.gov.cn/",
            "category": "policy",
            "tags": ["NMPA", "医疗器械", "注册审查"],
            "published_at": ago(5),
        },
        {
            "title": "FDA 更新 AI/ML 医疗器械预定变更控制计划指南",
            "summary": "FDA 就 AI/ML 器械全生命周期管理发布更新草案，允许企业在预定变更控制计划内迭代模型，减少重复申报成本，被业内视为 SaMD 监管风向标。",
            "source": "U.S. Food and Drug Administration",
            "url": "https://www.fda.gov/medical-devices",
            "category": "policy",
            "tags": ["FDA", "SaMD", "PCCP"],
            "published_at": ago(28),
        },
        {
            "title": "国家卫健委部署医学人工智能应用试点工作",
            "summary": "通知要求试点医院建立医学 AI 应用管理制度与数据安全规范，重点覆盖辅助诊断、病历质控与科研平台三类场景，强调全程可追溯。",
            "source": "国家卫生健康委员会",
            "url": "http://www.nhc.gov.cn/",
            "category": "policy",
            "tags": ["卫健委", "试点", "数据安全"],
            "published_at": ago(74),
        },
        {
            "title": "NEJM AI：多模态基础模型在肿瘤影像分组中的前瞻性验证",
            "summary": "研究在多中心队列中前瞻验证多模态基础模型的肿瘤影像分组能力，显示稳定优于传统放射组学流水线，但外部人群泛化仍是主要瓶颈。",
            "source": "NEJM AI",
            "url": "https://ai.nejm.org/",
            "category": "research",
            "tags": ["多模态", "基础模型", "肿瘤影像"],
            "published_at": ago(9),
        },
        {
            "title": "The Lancet Digital Health：LLM 辅助病历质控随机对照研究",
            "summary": "RCT 显示大模型辅助可将病历缺陷检出率显著提升、质控工时下降约四成，作者提示需配合人工复核以控制幻觉风险。",
            "source": "The Lancet Digital Health",
            "url": "https://www.thelancet.com/digital-health",
            "category": "research",
            "tags": ["LLM", "病历质控", "RCT"],
            "published_at": ago(30),
        },
        {
            "title": "arXiv：面向放射组学的可复现特征流水线开源基准",
            "summary": "论文开源了覆盖特征提取、稳定性筛选到建模的端到端基准，指出主流工具链在版本与参数固定下的复现差异仍不可忽视。",
            "source": "arXiv",
            "url": "https://arxiv.org/list/eess.IV/recent",
            "category": "research",
            "tags": ["放射组学", "可复现性", "开源"],
            "published_at": ago(52),
        },
        {
            "title": "Nature Medicine：AI 辅助食管癌早筛模型完成多中心外部验证",
            "summary": "模型在跨区域多中心队列中保持稳健的早筛敏感性，作者认为结合内镜工作流的人机协同模式最具落地价值。",
            "source": "Nature Medicine",
            "url": "https://www.nature.com/nm/",
            "category": "research",
            "tags": ["食管癌", "早筛", "外部验证"],
            "published_at": ago(96),
        },
        {
            "title": "联影智能发布新一代医学影像大模型与全病程解决方案",
            "summary": "新品覆盖影像采集、后处理到随访管理的全链路，强调院内私有化部署与多模态数据贯通，面向三级医院科研与临床双场景。",
            "source": "联影智能",
            "url": "https://www.united-imaging.com/",
            "category": "industry",
            "tags": ["影像大模型", "私有化部署"],
            "published_at": ago(12),
        },
        {
            "title": "数坤科技心血管 AI 产品海外注册取得进展",
            "summary": "公司披露心血管影像 AI 产品在海外多国的注册与商业进展，国际化为国产医学 AI 公司提供增长第二曲线样本。",
            "source": "数坤科技",
            "url": "https://www.shukun.net/",
            "category": "industry",
            "tags": ["心血管", "出海", "注册"],
            "published_at": ago(47),
        },
        {
            "title": "Google DeepMind 更新医疗健康方向模型能力与应用框架",
            "summary": "更新聚焦临床文书理解与多模态检验数据建模，配套安全评估框架，强调在真实医疗工作流中的分阶段落地。",
            "source": "Google DeepMind",
            "url": "https://deepmind.google/",
            "category": "industry",
            "tags": ["DeepMind", "临床文书", "安全评估"],
            "published_at": ago(70),
        },
        {
            "title": "动脉网：医学影像 AI 企业完成新一轮融资",
            "summary": "本轮资金将用于产品矩阵扩展与医院渠道深化，投资方继续看好具备真实临床闭环与付费能力的医学 AI 标的。",
            "source": "动脉网",
            "url": "https://www.vcbeat.top/",
            "category": "funding",
            "tags": ["融资", "医学影像"],
            "published_at": ago(20),
        },
        {
            "title": "RSNA 2026 年会医学 AI 议程公布",
            "summary": "本届 RSNA AI 议程覆盖基础模型、生成式报告与工作流自动化专题，多场焦点报告将讨论影像 AI 的责任边界与临床证据标准。",
            "source": "Radiological Society of North America",
            "url": "https://www.rsna.org/annual-meeting",
            "category": "conference",
            "tags": ["RSNA", "年会", "议程"],
            "published_at": ago(60),
        },
    ]

    inserted = 0
    for it in items:
        cur = await db.execute(
            "INSERT INTO insight_items "
            "(title, summary, source, url, category, tags, published_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                it["title"],
                it["summary"],
                it["source"],
                it["url"],
                it["category"],
                json.dumps(it["tags"], ensure_ascii=False),
                it["published_at"],
            ),
        )
        if _rowcount(cur) or getattr(cur, "lastrowid", None):
            inserted += 1
    await db.commit()
    return inserted


async def _ensure_data(db: Any) -> None:
    await _prune_expired(db)
    if await _count_items(db) == 0:
        await _seed_demo_items(db)


@router.get("/insights", response_model=InsightListResp)
async def list_insights(
    category: str = Query("", description="分类过滤：policy/research/industry/funding/conference"),
    q: str = Query("", max_length=80, description="关键词搜索（标题/摘要/来源）"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> InsightListResp:
    db = await get_db()
    await _ensure_data(db)

    cat = category if category in CATEGORY_LABELS else ""
    kw = q.strip()

    where = "WHERE 1=1"
    params: list[Any] = []
    if cat:
        where += " AND category = ?"
        params.append(cat)
    if kw:
        where += " AND (title LIKE ? OR summary LIKE ? OR source LIKE ?)"
        like = f"%{kw}%"
        params.extend([like, like, like])

    cur = await db.execute(
        f"SELECT COUNT(*) FROM insight_items {where}",
        tuple(params),
    )
    row = await cur.fetchone()
    total = int(row[0]) if row else 0

    cur = await db.execute(
        "SELECT id, title, summary, source, url, category, tags, published_at "
        f"FROM insight_items {where} "
        "ORDER BY published_at DESC LIMIT ? OFFSET ?",
        tuple(params + [limit, offset]),
    )
    rows = await cur.fetchall()
    items = [_row_to_item(r) for r in rows]
    return InsightListResp(total=total, items=items)


@router.get("/insights/stats", response_model=InsightStatsResp)
async def insight_stats() -> InsightStatsResp:
    db = await get_db()
    await _ensure_data(db)

    now = _now()
    today_cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    week_cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")

    async def scalar(sql: str, p: tuple) -> int:
        cur = await db.execute(sql, p)
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    today = await scalar(
        "SELECT COUNT(*) FROM insight_items WHERE published_at >= ?", (today_cutoff,)
    )
    week = await scalar(
        "SELECT COUNT(*) FROM insight_items WHERE published_at >= ?", (week_cutoff,)
    )
    total = await _count_items(db)

    cur = await db.execute(
        "SELECT category, COUNT(*) FROM insight_items GROUP BY category"
    )
    by_category = {str(r[0]): int(r[1]) for r in await cur.fetchall()}
    return InsightStatsResp(
        today=today, week=week, total=total, by_category=by_category
    )


@router.post("/insights/seed", response_model=SeedResp)
async def reseed_insights(user: dict[str, Any] = Depends(get_current_user)) -> SeedResp:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="仅管理员可重置演示数据")
    db = await get_db()
    await db.execute("DELETE FROM insight_items")
    await db.commit()
    inserted = await _seed_demo_items(db)
    logger.info("insights_reseeded", count=inserted)
    return SeedResp(ok=True, inserted=inserted)


# ---------------------------------------------------------------- 订阅

@router.get("/insights/subscriptions", response_model=SubscriptionListResp)
async def list_subscriptions(
    user: dict[str, Any] = Depends(get_current_user),
) -> SubscriptionListResp:
    db = await get_db()
    uid = user["id"]
    week_cutoff = (_now() - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")
    cur = await db.execute(
        "SELECT id, keyword, created_at FROM insight_subscriptions WHERE user_id = ? ORDER BY id DESC",
        (uid,),
    )
    subs = []
    for r in await cur.fetchall():
        sid, keyword, created_at = r
        hc = await db.execute(
            "SELECT COUNT(*) FROM insight_items WHERE published_at >= ? AND (title LIKE ? OR summary LIKE ?)",
            (week_cutoff, f"%{keyword}%", f"%{keyword}%"),
        )
        row = await hc.fetchone()
        subs.append(
            SubscriptionItem(
                id=int(sid),
                keyword=keyword,
                hits_week=int(row[0]) if row else 0,
                created_at=created_at,
            )
        )
    return SubscriptionListResp(total=len(subs), items=subs)


@router.post("/insights/subscriptions", response_model=SubscriptionItem, status_code=201)
async def create_subscription(
    body: SubscriptionCreateReq,
    user: dict[str, Any] = Depends(get_current_user),
) -> SubscriptionItem:
    keyword = body.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=422, detail="关键词不能为空")
    db = await get_db()
    uid = user["id"]
    cur = await db.execute(
        "SELECT COUNT(*) FROM insight_subscriptions WHERE user_id = ?", (uid,)
    )
    row = await cur.fetchone()
    if row and int(row[0]) >= MAX_SUBSCRIPTIONS_PER_USER:
        raise HTTPException(status_code=422, detail=f"每个账号最多订阅 {MAX_SUBSCRIPTIONS_PER_USER} 个关键词")
    cur = await db.execute(
        "SELECT id FROM insight_subscriptions WHERE user_id = ? AND keyword = ?",
        (uid, keyword),
    )
    if await cur.fetchone():
        raise HTTPException(status_code=409, detail="该关键词已在订阅列表中")
    cur = await db.execute(
        "INSERT INTO insight_subscriptions (user_id, keyword) VALUES (?, ?)",
        (uid, keyword),
    )
    await db.commit()
    new_id = int(getattr(cur, "lastrowid", 0) or 0)
    return SubscriptionItem(id=new_id, keyword=keyword, hits_week=0)


@router.delete("/insights/subscriptions/{sub_id}", status_code=204)
async def delete_subscription(
    sub_id: int, user: dict[str, Any] = Depends(get_current_user)
) -> None:
    db = await get_db()
    cur = await db.execute(
        "DELETE FROM insight_subscriptions WHERE id = ? AND user_id = ?",
        (sub_id, user["id"]),
    )
    await db.commit()
    if _rowcount(cur) == 0:
        raise HTTPException(status_code=404, detail="订阅不存在")


@router.get("/insights/subscriptions/hits", response_model=SubscriptionHitsResp)
async def subscription_hits(
    user: dict[str, Any] = Depends(get_current_user),
) -> SubscriptionHitsResp:
    db = await get_db()
    uid = user["id"]
    now = _now()
    day_cutoff = (now - timedelta(hours=24)).isoformat(timespec="seconds")
    week_cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")
    cur = await db.execute(
        "SELECT id, keyword FROM insight_subscriptions WHERE user_id = ? ORDER BY id DESC",
        (uid,),
    )
    rows = await cur.fetchall()
    items: list[SubscriptionItem] = []
    total_24h = 0
    for sid, keyword in rows:
        hc = await db.execute(
            "SELECT COUNT(*) FROM insight_items WHERE published_at >= ? AND (title LIKE ? OR summary LIKE ?)",
            (week_cutoff, f"%{keyword}%", f"%{keyword}%"),
        )
        row = await hc.fetchone()
        week_hits = int(row[0]) if row else 0
        dc = await db.execute(
            "SELECT COUNT(*) FROM insight_items WHERE published_at >= ? AND (title LIKE ? OR summary LIKE ?)",
            (day_cutoff, f"%{keyword}%", f"%{keyword}%"),
        )
        row = await dc.fetchone()
        day_hits = int(row[0]) if row else 0
        total_24h += day_hits
        items.append(SubscriptionItem(id=int(sid), keyword=keyword, hits_week=week_hits))
    return SubscriptionHitsResp(total_24h=total_24h, items=items)


# ---------------------------------------------------------------- 采集源（管理员）

@router.get("/insights/sources", response_model=SourceListResp)
async def list_sources(user: dict[str, Any] = Depends(get_current_user)) -> SourceListResp:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="仅管理员可查看采集源")
    db = await get_db()
    cur = await db.execute(
        "SELECT id, name, kind, url, category, enabled, created_at FROM insight_sources ORDER BY id"
    )
    items = [
        SourceItem(
            id=int(r[0]), name=r[1], kind=r[2], url=r[3],
            category=r[4], enabled=bool(r[5]), created_at=r[6],
        )
        for r in await cur.fetchall()
    ]
    return SourceListResp(total=len(items), items=items)


@router.post("/insights/sources", response_model=SourceItem, status_code=201)
async def create_source(
    body: SourceCreateReq, user: dict[str, Any] = Depends(get_current_user)
) -> SourceItem:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="仅管理员可添加采集源")
    if body.kind not in SOURCE_KINDS:
        raise HTTPException(status_code=422, detail=f"kind 仅支持 {'/'.join(sorted(SOURCE_KINDS))}")
    if body.category not in CATEGORY_LABELS:
        body.category = "research"
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO insight_sources (name, kind, url, category, enabled) VALUES (?, ?, ?, ?, ?)",
        (body.name.strip(), body.kind, body.url.strip(), body.category, 1 if body.enabled else 0),
    )
    await db.commit()
    new_id = int(getattr(cur, "lastrowid", 0) or 0)
    return SourceItem(
        id=new_id, name=body.name.strip(), kind=body.kind, url=body.url.strip(),
        category=body.category, enabled=body.enabled,
    )


@router.delete("/insights/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: int, user: dict[str, Any] = Depends(get_current_user)
) -> None:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="仅管理员可删除采集源")
    db = await get_db()
    cur = await db.execute("DELETE FROM insight_sources WHERE id = ?", (source_id,))
    await db.commit()
    if _rowcount(cur) == 0:
        raise HTTPException(status_code=404, detail="采集源不存在")


@router.post("/insights/collect", response_model=CollectResp)
async def trigger_collect(user: dict[str, Any] = Depends(get_current_user)) -> CollectResp:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="仅管理员可手动触发采集")
    from cancer_claw.services.insights.collector import collect_now

    stats = await collect_now()
    return CollectResp(**stats)
