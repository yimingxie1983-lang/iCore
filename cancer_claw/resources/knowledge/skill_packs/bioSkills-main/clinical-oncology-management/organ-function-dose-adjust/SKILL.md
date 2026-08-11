---
name: organ-function-dose-adjust
description: 根据患者肝肾功能、骨髓储备与体表面积，对常用化疗/靶向药给出剂量调整建议，含卡铂 Calvert AUC 公式、肌酐清除率估算、骨髓抑制减量/延迟规则。Use when adjusting anticancer drug doses for hepatic or renal impairment, calculating carboplatin AUC dosing, or deciding chemotherapy delay/reduction after myelosuppression.
tool_type: python
primary_tool: craft_clinical_scores
---

# 脏器功能与抗肿瘤药物剂量调整

同一个方案，肝肾功能不同的两个人不能用同一剂量。剂量调整出错的后果是双向的：
减多了无效、减少了中毒。这个 Skill 把"按脏器功能调量"的几条核心算法和减量规则
固化下来，避免临场拍脑袋。

> 本 Skill 给的是**计算与调整框架**，最终剂量须对照各药说明书与当年指南，由主管
> 医师确认。缺关键化验值（肌酐、胆红素、中性粒、血小板）一律先 `ask_user` 追问，
> **绝不假设正常值**。

## 一、先把基础参数算准

### 肾功能：肌酐清除率（Cockcroft-Gault）

```
CrCl (mL/min) = (140 − 年龄) × 体重(kg) × (0.85 若女性) / (72 × 血清肌酐 mg/dL)
```

> 单位陷阱：国内肌酐常报 μmol/L，换算 mg/dL 需 ÷88.4。肥胖/水肿患者用实际体重会
> 高估，建议用校正体重；危重/AKI 时 Cockcroft-Gault 不可靠，需实测或慎用肾毒药。

### 卡铂剂量：Calvert 公式（AUC 法，非 mg/m²）

```
卡铂总剂量(mg) = 目标AUC × (GFR + 25)
```

> 关键坑：现代实验室肌酐多用 IDMS 标化，会系统性低估，导致 GFR 偏高、卡铂超量。
> 多数机构对 Calvert 的 GFR **设上限（常封顶 125 mL/min）**。目标 AUC 按方案定
> （单药常 5–6，联合常 4–5）。算完务必复核：GFR 是否被封顶、AUC 是否取对。

## 二、肝功能损害的剂量调整（按代谢途径分类）

肝代谢药才受肝功能影响，肾清除为主的药（如卡铂、培美曲塞）看肾不看肝。

| 药物类别 | 代表药 | 肝损时原则 |
|----------|--------|-----------|
| 蒽环类 | 多柔比星/表柔比星 | 按胆红素分档减量（胆红素↑显著减量乃至停用） |
| 紫杉类 | 紫杉醇/多西他赛 | 转氨酶 + 胆红素双指标分档减量 |
| 长春碱类 | 长春瑞滨 | 胆红素升高显著减量 |
| 伊立替康 | — | 胆红素升高减量；UGT1A1*28 纯合者起始减量 |
| 肾清除为主 | 卡铂/培美曲塞 | 肝损一般不调，按肾调 |

> 具体分档阈值各药说明书不一致，用 `china-clinical-guidelines/drug-label-lookup`
> 拉对应药物说明书的"肝功能不全用法"段落核对，不要套用别药的档位。

## 三、骨髓抑制后的减量/延迟规则（通用骨架）

下一周期开始前看血象，按 CTCAE 最低值（nadir）和当前值双重判断：

| 情形 | 常见处置 |
|------|----------|
| 下一周期 ANC < 1.5×10⁹/L 或 PLT < 100×10⁹/L | 延迟给药，每周复查至恢复 |
| 上周期出现 G4 中性粒减少 / 发热性中性粒减少(FN) | 下周期减量一档 ± 预防性 G-CSF |
| 上周期 G4 血小板减少或出血 | 下周期减量一档 |
| 反复延迟 > 2 周仍不恢复 | 重新评估方案强度/换方案 |

> FN 是急症（ANC < 0.5 + 发热）：先经验性广谱抗生素，再谈下周期减量。G-CSF
> 一级预防用于 FN 风险 ≥20% 的方案，不是所有人都打。

## 四、推荐调用工序

```
# 1) 算评分/清除率，缺字段工具会触发 ask_user 追问
craft_clinical_scores(score="cockcroft_gault", fields={"age":..., "weight":..., "scr_umol":..., "sex":...})

# 2) 拉具体药物说明书的脏器功能调整段落
guideline_search(action="search_guideline", keyword="多西他赛 说明书 肝功能不全 用法")

# 3) 循证溯源
pubmed_search(query="carboplatin Calvert AUC dosing GFR capping", max_results=8)
```

## 五、给主 agent 的输出纪律

- 先复述用到的化验值与单位，再给计算过程，最后给建议剂量区间 + 依据
- 卡铂务必显示 GFR 是否封顶、AUC 取值；单位换算（μmol/L↔mg/dL）写出来
- 减量是"减一档"还是"延迟"要分清，并给出下次复查时点
- 任何缺失关键化验值 → `ask_user`，不得默认正常

## References

- Calvert AH, et al. Carboplatin dosage: prospective evaluation of a simple formula based on renal function. [PMID:2459426]
- Cockcroft DW, Gault MH. Prediction of creatinine clearance from serum creatinine. [PMID:1244564]
- NCCN Guidelines: Hematopoietic Growth Factors（FN 风险与 G-CSF 适应，当年版）
- 各药 NMPA 批准说明书（肝肾功能不全用法段落）

## Related Skills

- clinical-oncology-management/antineoplastic-ddi-check - 抗肿瘤药物相互作用核查
- clinical-oncology-management/irae-grading-management - irAE 识别与分级管理
- china-clinical-guidelines/drug-label-lookup - 药品说明书查询
- china-clinical-guidelines/csco-guideline-fetch - CSCO 指南抓取
