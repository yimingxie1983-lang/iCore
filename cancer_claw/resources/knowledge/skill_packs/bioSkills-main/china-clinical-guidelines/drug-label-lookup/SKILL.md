---
name: china-drug-label-lookup
description: 使用 guideline_search + http_fetch 工具查询中国药品说明书和适应症信息，辅助指南用药推荐的落地核验。Use when looking up Chinese drug labels, indications, or dosing information to verify guideline recommendations.
tool_type: python
primary_tool: guideline_search
---

# 中国药品说明书查询

药品说明书是临床用药的法规性文件，CSCO/CMA 指南的用药推荐
最终需要对照 NMPA（国家药监局）批准的说明书适应症来落地执行。

## 工具调用

### 检索药品相关指南

```
# 查某药物在指南中的推荐地位
guideline_search(
    action="search_guideline",
    keyword="奥希替尼 非小细胞肺癌 一线"
)
```

### 查询 NMPA 药品信息

通过 http_fetch 访问 NMPA 数据库：

```
http_fetch(
    action="get",
    url="https://www.nmpa.gov.cn/datasearch/home-index.html",
    headers={"Accept-Language": "zh-CN"}
)
```

### 第三方药品 API

部分第三方平台提供结构化药品数据 API（如 drugsnav.com、yaozh.com）：

```
http_fetch(
    action="get",
    url="https://api.example.com/drug/search?name=奥希替尼",
    timeout=15
)
```

## 核验清单

用指南推荐方案做临床决策时，建议核验以下项目：

| 核验项 | 说明 |
|--------|------|
| NMPA 获批适应症 | 指南推荐的用法是否在获批适应症范围内 |
| 医保目录收录 | 是否纳入国家医保目录（影响患者可及性） |
| 用法用量 | 说明书推荐剂量 vs 指南推荐剂量 |
| 禁忌症 | 患者是否存在说明书列出的禁忌 |
| 药物相互作用 | 联合用药时的相互作用风险 |

## 常用药品数据源

| 平台 | URL | 内容 |
|------|-----|------|
| NMPA 数据查询 | nmpa.gov.cn/datasearch | 官方批文、说明书 |
| 药智网 | yaozh.com | 说明书、医保目录 |
| 用药助手（DXY） | drugs.dxy.cn | 药品信息聚合 |
| 医保药品目录 | nhsa.gov.cn | 国家医保目录查询 |

## Related Skills

- csco-guideline-fetch - CSCO 指南推荐方案
- nccn-china-lookup - NCCN 中国版推荐
- pharmacogenomics - 药物基因组学（PGx）
