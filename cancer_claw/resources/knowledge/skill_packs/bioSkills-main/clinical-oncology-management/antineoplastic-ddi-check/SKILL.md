---
name: antineoplastic-ddi-check
description: 系统化核查抗肿瘤治疗的药物相互作用，重点覆盖 CYP450 酶诱导/抑制、QT 间期叠加延长、质子泵抑制剂影响 TKI 吸收、抗凝/中草药相互作用，输出风险分级与处置建议。Use when reviewing a cancer patient's full medication list for drug-drug interactions, especially with targeted agents, before starting or combining therapies.
tool_type: python
primary_tool: guideline_search
---

# 抗肿瘤药物相互作用核查

肿瘤患者往往同时吃靶向药、止吐药、抗凝药、降压药、还有自己加的中草药保健品。
相互作用导致的"血药浓度过高中毒"或"过低无效"在临床很常见但容易被漏。这个 Skill
提供一套**按机制分轨**的核查清单，把一长串用药单过一遍而不靠记忆碰运气。

> 本 Skill 做的是**风险识别与分级**，不替代临床药师/主管医师的最终判断。建议
> 联动专业数据库（Lexicomp / Micromedex / 用药助手）做权威核对。

## 一、四条核查主轨

### 轨道 1：CYP450 酶（最高频、最隐蔽）

许多 TKI 是 CYP3A4 底物，遇强诱导/强抑制剂血药浓度可数倍波动：

| 机制 | 典型合用药 | 后果 | 处置 |
|------|-----------|------|------|
| 强抑制剂（↑底物浓度） | 唑类抗真菌、克拉霉素、葡萄柚汁 | TKI 中毒（如奥希替尼 QT、伊马替尼水肿） | 避免合用或底物减量 |
| 强诱导剂（↓底物浓度） | 利福平、卡马西平、苯妥英、圣约翰草 | TKI 失效 | 避免合用或换药 |

> 圣约翰草（贯叶连翘）是被反复忽视的强诱导剂，患者常当"草药/抗抑郁保健品"自服，
> 必须主动问。

### 轨道 2：QT 间期叠加延长

多个延长 QT 的药叠加 → 尖端扭转风险。常见叠加源：部分 TKI/ICI 相关、止吐药
（昂丹司琼/胃复安）、氟喹诺酮、唑类、甲氧氯普胺、电解质紊乱（低钾/低镁）。

> 处置：合用前查基线 ECG、纠正电解质、避免多药叠加；高危组合监测 QTc。

### 轨道 3：吸收依赖胃 pH 的口服药

某些 TKI（如部分需酸性环境溶解者）与 PPI/H2 受体拮抗剂合用吸收骤降、疗效打折。

> 处置：错时服用、改用抗酸剂并间隔给药、或评估换不依赖 pH 的药；不同 TKI 规则
> 不一致，按各药说明书查。

### 轨道 4：抗凝/抗血小板 + 中草药

华法林与多种抗肿瘤药/抗生素/中草药（丹参、当归、银杏）相互作用，INR 易失控；
DOAC 也受 CYP3A4/P-gp 影响。出血/血栓双向风险。

> 处置：合用期加密监测 INR/出血征象，必要时换药或调抗凝强度。

## 二、核查工作流

```
# 1) 把患者完整用药单逐药归类（抗肿瘤药/支持治疗/合并症用药/自服中草药保健品）
# 2) 对每个 TKI 查代谢途径与禁忌合用
guideline_search(action="search_guideline", keyword="奥希替尼 说明书 药物相互作用 CYP3A4")

# 3) 循证补充
pubmed_search(query="tyrosine kinase inhibitor drug interaction CYP3A4 QT prolongation", max_results=10)

# 4) 引用核验
citation_resolve(ids=["DOI:10.1200/JCO.xxxx"])
```

## 三、输出结构（建议给主 agent 用）

| 组合 | 机制轨道 | 风险等级 | 处置建议 | 依据 |
|------|---------|---------|---------|------|
| 药A + 药B | CYP3A4 强抑制 | 高 | 避免/减量/监测 | 说明书/PMID |

风险分级：高（禁忌或需换药）/ 中（可合用但需监测/错时）/ 低（关注即可）。

## 四、给主 agent 的输出纪律

- 必须先拿到**完整**用药单（含 OTC、保健品、中草药），缺则 `ask_user` 追问
- 主动问圣约翰草、葡萄柚汁、PPI、抗真菌药这几个高频"隐藏雷"
- 风险组合按等级排序，高风险置顶；每条给机制 + 可执行处置
- 标注信息来源（说明书版本/PMID），不臆断剂量

## References

- 各药 NMPA 批准说明书"药物相互作用"段落
- FDA Drug Development and Drug Interactions: Table of Substrates, Inhibitors and Inducers
- NCCN/CSCO 各瘤种指南中支持治疗与用药安全章节（当年版）

## Related Skills

- clinical-oncology-management/organ-function-dose-adjust - 脏器功能剂量调整
- clinical-oncology-management/irae-grading-management - irAE 识别与分级管理
- china-clinical-guidelines/drug-label-lookup - 药品说明书查询
- china-clinical-guidelines/csco-guideline-fetch - CSCO 指南抓取
