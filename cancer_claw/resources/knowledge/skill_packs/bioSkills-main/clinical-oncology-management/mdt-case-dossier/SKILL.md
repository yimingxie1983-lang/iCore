---
name: mdt-case-dossier
description: 把零散的病史、影像、病理、化验整理成 MDT 会诊可直接使用的结构化病例卷宗，输出只含客观事实、缺口清单与待澄清问题，可直接喂给 convene_council 的 explicit_facts。Use when preparing a structured case summary for a multidisciplinary tumor board, or assembling the objective fact base before convening a clinical council.
tool_type: python
primary_tool: convene_council
---

# MDT 病例卷宗结构化整理

MDT 会诊最常见的翻车点不是讨论本身，而是**事实卷宗被主观结论污染**：一句
"这个病人应该先手术"写进病史摘要，后面所有科室都会被带跑。本 Skill 把病例
整理成一份**只有客观事实、不含倾向性结论**的卷宗，恰好是 `convene_council`
要求的 `explicit_facts` 输入格式——议会的客观性从源头就守住。

> 这个 Skill 是 iCore 议会机制（`convene_council`）的"上游配料台"。议会要求
> 调用方必须提供 snapshot，且所有 role 只能基于卷宗推理；卷宗写歪了，N 个角色一起歪。

## 一、卷宗的铁律：事实与结论分离

| 写法 | 判定 |
|------|------|
| "肿块 4.2 cm，位于肝右叶 S7，紧邻门静脉右支" | ✅ 客观事实 |
| "BCLC-B 期，Child-Pugh A5，ECOG 0" | ✅ 客观（分级是规则计算结果，附计算依据） |
| "考虑应优先手术切除" | ❌ 结论/倾向，**禁止**进卷宗，应留给议会去吵 |
| "患者一般情况尚可" | ❌ 模糊主观，改成 ECOG 评分 + 具体指标 |

> 规则：凡是"判断/推荐/倾向"性语言一律剔除；凡是"数值/影像所见/病理诊断/分级"
> 保留并标单位与来源。

## 二、卷宗标准结构（八段）

1. **基本信息**：年龄、性别、体能状态（ECOG/KPS，带评分）
2. **主诉与现病史时间线**：发病-就诊-检查-治疗的客观时间序列
3. **既往史/合并症/用药**：含 OTC、中草药、过敏史（影响后续 DDI 与耐受评估）
4. **影像**：部位、大小、数目、与关键结构关系、分期相关征象（带检查日期与设备）
5. **病理/分子**：组织学类型、分级、关键标志物（IHC/基因，带检测方法与日期）
6. **关键化验**：肝肾功能、血象、肿瘤标志物（带单位与参考区间）
7. **分期与评分**：TNM、临床分期、Child-Pugh/MELD/BCLC 等（附计算用到的字段）
8. **明确缺口（open gaps）**：缺哪些关键事实——这是卷宗最有价值的部分

## 三、整理工作流

```
# 1) 用临床评分工具把分级算准（缺字段会触发 ask_user，绝不假设正常值）
craft_clinical_scores(score="child_pugh", fields={...})
craft_clinical_scores(score="ecog", fields={...})

# 2) 影像/病理描述若引用文献阈值，反向锚核验
citation_resolve(ids=["PMID:..."])

# 3) 卷宗就绪后，主 agent 用它作为议会事实层发起 MDT
convene_council(
    topic="该患者的治疗策略选择",
    snapshot_mode="explicit",
    explicit_facts="<上面八段整理好的客观卷宗>",
    roles=["med_oncologist", "surgical_oncologist", "radiation_oncologist", "interventional_radiologist", "radiologist"]
)
```

## 四、缺口清单怎么写（决定议会质量）

把"缺失但关键"的事实显式列出，让议会知道哪些是真空、哪些角色需要补：

| 缺口 | 影响哪个决策 | 谁来补 |
|------|-------------|--------|
| 未做 PD-L1 / 驱动基因检测 | 系统治疗选药 | 病理/分子 |
| 无近期心功能(LVEF) | 蒽环/HER2 用药安全 | 心内/影像 |
| 门静脉受累程度未明确 | 可切除性判定 | 影像/外科 |

> 不要替缺口"脑补正常值"。议会里这些缺口会被写进各角色的 open_questions，由主
> agent 决定补还是带着不确定性决策。

## 五、给主 agent 的输出纪律

- 卷宗正文**零结论**：任何治疗倾向都不写进 explicit_facts
- 每个分级附计算字段，便于议会角色复核而非盲信
- 缺口清单必须单列，不得用"未见异常"掩盖"未检查"
- 单位、日期、检测方法齐全；不齐 → `ask_user`

## References

- 各瘤种 NCCN/CSCO 指南中 MDT 与分期章节（当年版）
- AJCC Cancer Staging Manual（对应瘤种 TNM 体系，当前版次）

## Related Skills

- clinical-oncology-management/organ-function-dose-adjust - 脏器功能剂量调整
- clinical-oncology-management/cancer-pain-opioid-titration - 癌痛阿片滴定
- china-clinical-guidelines/csco-guideline-fetch - CSCO 指南抓取
- china-clinical-guidelines/nccn-china-lookup - NCCN 中国版指南查询
