# clinical-oncology-management

## Overview

肿瘤临床管理类 Skill，覆盖 bioSkills 原本缺失的"床旁决策"环节：不良反应分级、
剂量调整、用药安全、MDT 卷宗整理与癌痛管理。与组学分析类 Skill 互补——前者
回答"数据怎么分析"，本类回答"病人怎么管"。

**Tool type:** python | **Primary tools:** craft_clinical_scores, guideline_search, convene_council, pubmed_search, citation_resolve

所有 Skill 只做证据梳理、分级与计算框架，不替代主管医师下医嘱；缺关键化验/分级
字段一律 `ask_user` 追问，绝不假设正常值；阈值与等效系数均以当年指南/说明书为准。

## Skills

| Skill | Description |
|-------|-------------|
| irae-grading-management | 免疫相关不良反应识别 + CTCAE 分级 + 激素/停药处置阶梯 |
| organ-function-dose-adjust | 肝肾功能/骨髓储备剂量调整，含卡铂 Calvert AUC 与肌酐清除率 |
| antineoplastic-ddi-check | 抗肿瘤药物相互作用核查（CYP450 / QT / PPI / 抗凝中草药） |
| mdt-case-dossier | MDT 病例卷宗结构化，产出 convene_council 可用的 explicit_facts |
| cancer-pain-opioid-titration | 癌痛 NRS 评估 + 阿片滴定 + OME 等效换算 + 副作用防治 |

## Example Prompts

- "患者用帕博利珠单抗后转氨酶升到 5 倍上限，帮我分级并给处置框架"
- "这个肝硬化患者要上卡铂，AUC 5，帮我用 Calvert 算剂量并复核 GFR 封顶"
- "把这份病历整理成 MDT 会诊用的客观卷宗，然后召集议会讨论治疗策略"
- "晚期患者 NRS 7 分，目前口服吗啡，想换羟考酮控释，帮我做等效换算"

## Requirements

无需额外 pip 依赖；本类 Skill 依赖框架内置工具（craft_clinical_scores /
guideline_search / convene_council / pubmed_search / citation_resolve）。

## Related Skills

- **china-clinical-guidelines** - 中国临床指南检索（CSCO/NCCN中国版/万方/梅斯/说明书）
- **pharmacogenomics** - 药物基因组学，与剂量调整/DDI 互补
