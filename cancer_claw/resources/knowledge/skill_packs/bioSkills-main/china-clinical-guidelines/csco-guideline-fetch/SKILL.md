---
name: china-csco-guideline-fetch
description: 使用 guideline_search 工具抓取和解析 CSCO（中国临床肿瘤学会）诊疗指南。支持从梅斯医学、万方等平台检索指南，解析 PDF 并提取推荐等级表格。Use when retrieving CSCO cancer treatment guidelines for clinical decision support.
tool_type: python
primary_tool: guideline_search
---

# CSCO 指南抓取与解析

CSCO 指南是中国肿瘤临床诊疗最权威的参考标准之一，每年在 CSCO 年会上发布更新。
2026 版计划出版 32 部指南（含 3 部首发：质子重离子放射治疗、阴道癌、癌症疼痛）。

## 工具调用

本 Skill 依赖内置工具 `guideline_search`，无需手写爬虫代码。

### 检索 CSCO 指南

```
guideline_search(
    action="search_guideline",
    keyword="CSCO 非小细胞肺癌 2026",
    max_results=20
)
```

> 多源聚合：同时查梅斯医学 + 万方医学，自动去重合并。

### 指定平台检索

```
# 仅查梅斯医学
guideline_search(action="search_medsci", keyword="CSCO 乳腺癌")

# 仅查万方医学
guideline_search(action="search_wanfang", keyword="CSCO 结直肠癌 诊疗指南")
```

### 解析指南 PDF

下载指南 PDF 后，用 `parse_pdf` 提取章节结构和推荐等级表格：

```
guideline_search(
    action="parse_pdf",
    pdf_path="workspace/raw/csco_nsclc_2026.pdf"
)
```

返回内容包括：
- 按章节拆分的文本（标题 + 内容 + 页码）
- 推荐等级表格（自动识别含"推荐/方案/证据/级别"的表格）

### NCCN vs CSCO 对比

```
guideline_search(
    action="compare_nccn_csco",
    keyword="肺癌"
)
```

返回两套指南在推荐等级体系、药物可及性、靶向/免疫治疗等维度的框架级差异。

## CSCO 推荐等级体系

| 推荐等级 | 证据等级 | 含义 |
|----------|---------|------|
| I 级推荐 | 1A | 高级别证据 + 专家一致推荐，可直接应用 |
| II 级推荐 | 1B / 2A | 稍低级别证据，专家基本一致推荐 |
| III 级推荐 | 2B / 3 | 专家意见不完全一致，可作为参考 |

## 常见用法场景

- 查最新 CSCO 指南版本和更新要点
- 提取特定癌种的一线/二线治疗推荐方案
- 对比 NCCN 国际版 vs CSCO 中国版的推荐差异
- 解析指南 PDF 获取结构化推荐表格

## Related Skills

- nccn-china-lookup - NCCN 中国版指南查询
- medsci-guideline-query - 梅斯医学指南通用检索
- wanfang-guideline-search - 万方医学指南检索
- cma-guideline-parse - 中华医学会指南 PDF 解析
- drug-label-lookup - 药品说明书查询
