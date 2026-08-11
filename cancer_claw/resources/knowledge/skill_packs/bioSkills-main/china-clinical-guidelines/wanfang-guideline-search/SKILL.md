---
name: china-wanfang-guideline-search
description: 使用 guideline_search 工具从万方医学数据库检索中国临床指南和专家共识，支持按疾病、科室等维度查询。Use when searching Chinese clinical guidelines from Wanfang Medical database.
tool_type: python
primary_tool: guideline_search
---

# 万方医学指南检索

万方医学网拥有中国最大的临床指南数据库之一（10,000+ 篇），
涵盖中华医学会、CSCO 等权威机构发布的各类诊疗指南和专家共识。

## 工具调用

### 万方指南检索

```
guideline_search(
    action="search_wanfang",
    keyword="非小细胞肺癌 诊疗指南",
    max_results=20,
    page=1
)
```

### 批量癌种检索（配合多轮调用）

```
# 逐个查询不同癌种
guideline_search(action="search_wanfang", keyword="乳腺癌 诊疗指南")
guideline_search(action="search_wanfang", keyword="结直肠癌 CSCO")
guideline_search(action="search_wanfang", keyword="胃癌 专家共识")
```

### 多源聚合（推荐）

```
# 自动同时查万方+梅斯，去重合并
guideline_search(
    action="search_guideline",
    keyword="肝细胞癌 诊疗指南 2026"
)
```

## 万方指南分类体系

| 科室 | 常见指南主题 |
|------|-------------|
| 肿瘤科 | 各癌种 CSCO/NCCN 指南、放化疗规范 |
| 内科 | 高血压、糖尿病、冠心病管理指南 |
| 外科 | 手术指征、围术期管理 |
| 感染科 | 抗菌药物使用、传染病防治 |
| 急诊科 | 急救流程、创伤处理 |

## 检索技巧

- 用"诊疗指南"而非"治疗指南"，前者覆盖面更广
- 加年份可定位最新版本，如"CSCO 肺癌 2026"
- "专家共识"可检索到正式指南之外的临床建议

## Related Skills

- csco-guideline-fetch - CSCO 指南抓取
- medsci-guideline-query - 梅斯医学指南检索
- cma-guideline-parse - 中华医学会指南解析
