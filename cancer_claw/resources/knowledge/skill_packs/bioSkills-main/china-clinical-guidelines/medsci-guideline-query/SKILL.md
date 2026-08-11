---
name: china-medsci-guideline-query
description: 使用 guideline_search 工具从梅斯医学 (MedSci) 检索中国临床指南，涵盖 30+ 科室分类和 CSCO/中华医学会等权威来源。Use when searching Chinese clinical guidelines from MedSci platform.
tool_type: python
primary_tool: guideline_search
---

# 梅斯医学指南检索

梅斯医学 (medsci.cn) 是国内最大的临床指南聚合平台之一，
收录 CSCO / 中华医学会 / NCCN 中国版等多来源指南，覆盖 30+ 科室。

## 工具调用

### 梅斯指南检索

```
guideline_search(
    action="search_medsci",
    keyword="CSCO 非小细胞肺癌",
    max_results=20
)
```

### 按科室分类检索

```
# 肿瘤科指南
guideline_search(action="search_medsci", keyword="肿瘤 诊疗指南")

# 内科指南
guideline_search(action="search_medsci", keyword="糖尿病 管理指南")

# 感染科指南
guideline_search(action="search_medsci", keyword="抗菌药物 临床应用")
```

### 多源聚合（推荐）

```
# 同时查梅斯+万方，去重合并
guideline_search(
    action="search_guideline",
    keyword="免疫检查点抑制剂 不良反应 管理"
)
```

## 梅斯医学指南科室覆盖

肿瘤科、心血管、呼吸科、消化科、神经科、内分泌、肾脏科、
血液科、风湿免疫、感染科、急诊科、儿科、妇产科、骨科、
泌尿外科、皮肤科、精神心理、眼科、耳鼻喉、口腔科等 30+ 科室。

## Related Skills

- csco-guideline-fetch - CSCO 指南抓取
- wanfang-guideline-search - 万方指南检索
- nccn-china-lookup - NCCN 中国版查询
