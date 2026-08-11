---
name: china-cma-guideline-parse
description: 使用 guideline_search 工具检索和解析中华医学会 (CMA) 发布的临床诊疗指南 PDF，提取章节结构和推荐等级表格。Use when parsing Chinese Medical Association clinical guideline PDFs for structured extraction.
tool_type: python
primary_tool: guideline_search
---

# 中华医学会指南解析

中华医学会 (CMA) 是中国最权威的医学学术组织，发布的临床诊疗指南
是各科室临床实践的"金标准"。指南主要以期刊论文和 PDF 形式发布。

## 工具调用

### 检索中华医学会指南

```
# 通过万方或梅斯检索 CMA 指南
guideline_search(
    action="search_guideline",
    keyword="中华医学会 肝癌 诊疗指南"
)

# 也可以直接搜中华医学会各专科分会名称
guideline_search(
    action="search_wanfang",
    keyword="中华医学会肿瘤学分会 专家共识"
)
```

### 解析 CMA 指南 PDF

下载到本地后用 parse_pdf 提取结构化内容：

```
guideline_search(
    action="parse_pdf",
    pdf_path="workspace/raw/cma_liver_guideline_2026.pdf"
)
```

返回内容：
- **章节列表**：按"第 X 章 / 一、二、三"等模式自动拆分
- **推荐表格**：自动识别含"推荐/证据/方案"关键词的表格
- **页码索引**：每个章节和表格标注所在页码

### 典型工作流

1. `guideline_search(action="search_guideline", keyword="...")` 检索指南
2. `http_fetch(action="download_file", url="...", save_path="...")` 下载 PDF
3. `guideline_search(action="parse_pdf", pdf_path="...")` 解析 PDF
4. 基于解析结果撰写临床报告或对比分析

## 中华医学会主要专科分会（肿瘤相关）

- 肿瘤学分会
- 放射肿瘤治疗学分会
- 病理学分会
- 核医学分会
- 外科学分会（各亚专科）
- 消化病学分会

## Related Skills

- csco-guideline-fetch - CSCO 指南抓取
- medsci-guideline-query - 梅斯医学检索
- wanfang-guideline-search - 万方指南检索
