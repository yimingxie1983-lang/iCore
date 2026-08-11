---
name: china-trial-search
description: 使用 http_fetch 工具检索中国肿瘤临床试验信息，支持从药物临床试验登记与信息公示平台 (chinadrugtrials.org.cn) 和 ClinicalTrials.gov 查询中国区试验。Use when searching oncology clinical trials recruiting in China.
tool_type: python
primary_tool: http_fetch
---

# 中国肿瘤临床试验检索

临床试验是指南更新的循证基础，查询正在进行的中国区肿瘤临床试验
有助于了解最新治疗进展和患者入组机会。

## 工具调用

### 中国药物临床试验登记平台

```
http_fetch(
    action="get",
    url="http://www.chinadrugtrials.org.cn/eap/clinicaltrials.searchlist",
    headers={"Accept-Language": "zh-CN"}
)
```

> 中国药物临床试验登记与信息公示平台 (NMPA 管理)，
> 收录所有在中国开展的药物临床试验。

### ClinicalTrials.gov 中国区试验

```
# 通过 ClinicalTrials.gov API 查询中国区的肿瘤试验
http_fetch(
    action="get",
    url="https://clinicaltrials.gov/api/v2/studies?query.cond=NSCLC&query.locn=China&filter.overallStatus=RECRUITING&pageSize=20"
)
```

### 癌种+药物联合检索

```
http_fetch(
    action="get",
    url="https://clinicaltrials.gov/api/v2/studies?query.cond=non-small+cell+lung+cancer&query.intr=osimertinib&query.locn=China&pageSize=10"
)
```

## 主要试验数据源

| 平台 | URL | 说明 |
|------|-----|------|
| 药物临床试验登记平台 | chinadrugtrials.org.cn | NMPA 官方，中国境内试验 |
| ClinicalTrials.gov | clinicaltrials.gov | 国际注册库，含中国区中心 |
| 中国临床试验注册中心 | chictr.org.cn | WHO 一级注册中心 |
| 肿瘤患者入组平台 | 各医院官网 | 单中心入组信息 |

## ClinicalTrials.gov API v2 常用参数

| 参数 | 说明 | 示例 |
|------|------|------|
| query.cond | 疾病/条件 | `NSCLC`, `breast cancer` |
| query.intr | 干预/药物 | `osimertinib`, `pembrolizumab` |
| query.locn | 地点 | `China`, `Beijing` |
| filter.overallStatus | 试验状态 | `RECRUITING`, `ACTIVE_NOT_RECRUITING` |
| pageSize | 返回数量 | `10`, `20` |
| sort | 排序 | `LastUpdatePostDate:desc` |

## 典型工作流

1. 用 `guideline_search` 查到指南推荐方案
2. 用 `http_fetch` 查该药物/方案在中国的临床试验
3. 用 `pubmed_search` 检索已发表的试验结果
4. 综合指南推荐 + 试验进展撰写临床建议

## Related Skills

- csco-guideline-fetch - CSCO 指南推荐
- nccn-china-lookup - NCCN 指南推荐
- pubmed_search - PubMed 文献检索
