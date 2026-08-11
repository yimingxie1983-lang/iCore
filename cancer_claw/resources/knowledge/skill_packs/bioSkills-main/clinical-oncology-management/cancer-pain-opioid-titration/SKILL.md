---
name: cancer-pain-opioid-titration
description: 按 NRS 评分做癌痛三阶梯评估，给出阿片类药物起始滴定、爆发痛解救剂量、阿片等效剂量(OME)换算与轮替减量框架，含便秘/呼吸抑制等不良反应防治要点。Use when assessing cancer pain severity, initiating or titrating opioids, converting between opioids, or rotating opioid therapy.
tool_type: python
primary_tool: craft_clinical_scores
---

# 癌痛阿片类药物滴定与等效剂量换算

癌痛管理出错主要在两处：滴定太保守让患者一直疼，或换药时等效剂量算错导致过量。
这个 Skill 把"评估→起始→滴定→换药→防副作用"串成一条可执行链，等效换算用
OME（口服吗啡当量）统一标尺。

> 本 Skill 提供**评估与换算框架**，处方权在主管医师。等效换算表存在个体差异与
> 不完全交叉耐受，换药后必须减量并重新滴定，不能照搬等效值直接给。

## 一、评估：NRS 三阶梯定性

| NRS（0–10） | 程度 | 阶梯起点 |
|-------------|------|----------|
| 1–3 | 轻度 | 非阿片 ± 辅助药（第一阶梯） |
| 4–6 | 中度 | 弱阿片或低剂量强阿片（第二/三阶梯） |
| 7–10 | 重度 | 强阿片为主（第三阶梯），尽快滴定 |

> 现代趋势：中重度癌痛可跳过弱阿片直接低剂量强阿片。评估同时要查神经病理性
> 成分（灼痛/电击样）→ 加抗惊厥/抗抑郁辅助药，单靠阿片效果差。

## 二、起始与滴定

- **未用过阿片者**：从低剂量短效强阿片起始，按需评估、逐步加量
- **滴定原则**：每日总量按疼痛控制情况上调（常以前 24h 用量为基础按比例增加），
  待稳定后转长效控释 + 短效解救备用
- **爆发痛解救剂量**：通常取**全天阿片总量的 10%–20%** 作为单次解救量，按需可重复

## 三、阿片等效剂量（OME）换算——换药/轮替核心

换药时先把当前方案折算成口服吗啡当量（OME），再换算到目标药，**再减量**：

| 药物/途径 | 大致换算关系（以口服吗啡为基准，仅供框架参考） |
|-----------|------------------------------------------------|
| 口服吗啡 | 1×（基准） |
| 静脉/皮下吗啡 | 约口服的 1/3 剂量等效（即更"强") |
| 口服羟考酮 | 比口服吗啡更强（需按当年等效表系数换算） |
| 芬太尼透皮贴 | 单位为 µg/h，有专用换算表，不与上面同标尺直接比 |

> ⚠️ 上表只标"方向与量级"，**具体系数必须查当年指南/说明书等效表核对**，不同来源
> 系数有差异。换药铁律：算出等效量后**下调 25%–50%**（不完全交叉耐受），再按疼痛
> 重新滴定。芬太尼贴剂换算单独处理，别硬塞进吗啡当量心算。

## 四、不良反应防治（开阿片就要同步安排）

| 不良反应 | 处置 |
|----------|------|
| 便秘 | **从用药第一天起预防性通便**（不耐受，需常规给缓泻剂） |
| 恶心呕吐 | 多为一过性，止吐对症，注意与化疗止吐方案叠加 |
| 呼吸抑制 | 过量征象，监测呼吸/镇静评分；纳洛酮拮抗（癌痛长期用者慎用、小量滴定避免戒断+剧痛反跳） |
| 嗜睡/谵妄 | 评估是否过量或脏器功能下降致蓄积，必要时减量/轮替 |

## 五、推荐调用工序

```
# 1) NRS 与体能评分（缺字段触发 ask_user）
craft_clinical_scores(score="ecog", fields={...})

# 2) 拉癌痛指南与阿片等效换算当年版表
guideline_search(action="search_guideline", keyword="癌症疼痛 诊疗 阿片 等效剂量 2026")

# 3) 循证溯源
pubmed_search(query="opioid rotation equianalgesic dose cancer pain", max_results=8)
```

## 六、给主 agent 的输出纪律

- 先报 NRS 与疼痛性质（伤害感受性/神经病理性），再给阶梯与方案
- 换药必须显示：当前 OME → 目标药等效 → 减量后剂量，三步写全
- 开阿片同时主动给便秘预防与监测计划
- 等效系数标注来源版本；缺关键信息 → `ask_user`，不臆断

## References

- WHO Guidelines for the pharmacological and radiotherapeutic management of cancer pain（当年版）
- CSCO/CMA《癌症疼痛诊疗规范》与癌痛相关指南（当年版）
- NCCN Guidelines: Adult Cancer Pain（当年版，含 OME 换算与轮替）

## Related Skills

- clinical-oncology-management/organ-function-dose-adjust - 脏器功能剂量调整
- clinical-oncology-management/antineoplastic-ddi-check - 抗肿瘤药物相互作用核查
- china-clinical-guidelines/drug-label-lookup - 药品说明书查询
- china-clinical-guidelines/csco-guideline-fetch - CSCO 指南抓取
