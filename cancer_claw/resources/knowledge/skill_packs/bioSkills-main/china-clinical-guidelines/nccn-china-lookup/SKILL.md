---
name: china-nccn-china-lookup
description: 使用 guideline_search 工具查询 NCCN 中国版肿瘤诊疗指南，支持浏览指南列表和 NCCN vs CSCO 推荐差异对比。Use when looking up NCCN China guidelines or comparing international vs Chinese oncology treatment recommendations.
tool_type: python
primary_tool: guideline_search
---

# NCCN 中国版指南查询

NCCN（美国国家综合癌症网络）指南是全球最广泛使用的肿瘤诊疗标准。
NCCN 中文官网（nccnchina.org.cn）提供 40+ 癌种的中文翻译版本。

## 工具调用

### 浏览 NCCN 中国版指南

```
guideline_search(
    action="search_nccn_china",
    keyword="肺癌"
)
```

> 从 nccnchina.org.cn 获取指南列表，按癌种关键词过滤。
> 留空 keyword 可获取全部可用指南目录。

### NCCN vs CSCO 对比

```
guideline_search(
    action="compare_nccn_csco",
    keyword="乳腺癌"
)
```

> 返回两套指南在推荐等级体系、药物可及性、靶向/免疫治疗等维度的差异概要。
> 支持癌种：肺癌、乳腺癌、结直肠癌、胃癌等高频癌种有细化对比。

## NCCN 证据与共识分类

| 证据类别 | 含义 |
|----------|------|
| Category 1 | 高级别循证证据 + NCCN 专家一致同意 |
| Category 2A | 较低级别证据 + 专家一致同意（默认等级） |
| Category 2B | 较低级别证据 + 专家基本同意 |
| Category 3 | 任何级别证据 + 专家存在重大分歧 |

## 中国覆盖的主要 NCCN 指南

| 系统 | 癌种 |
|------|------|
| 胸部 | 非小细胞肺癌、小细胞肺癌、恶性胸膜间皮瘤 |
| 乳腺 | 乳腺癌 |
| 消化 | 结直肠癌、胃癌、食管癌、肝胆癌、胰腺癌 |
| 泌尿 | 肾癌、前列腺癌、膀胱癌 |
| 妇科 | 宫颈癌、卵巢癌、子宫内膜癌 |
| 血液 | 弥漫大B细胞淋巴瘤、慢性粒细胞白血病、多发性骨髓瘤 |
| 头颈 | 头颈部鳞癌、甲状腺癌 |
| 皮肤 | 黑色素瘤 |

## Related Skills

- csco-guideline-fetch - CSCO 指南抓取与解析
- medsci-guideline-query - 梅斯医学指南检索
- wanfang-guideline-search - 万方指南检索
