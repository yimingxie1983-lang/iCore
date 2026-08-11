---
name: irae-grading-management
description: 识别免疫检查点抑制剂(ICI)相关不良反应(irAE)，按 CTCAE v5.0 分级并给出对应处理框架（激素阶梯、停药/复用决策、跨学科会诊触发条件）。整合 CSCO 免疫检查点抑制剂相关毒性管理指南与 NCCN/ASCO/SITC 共识。Use when a patient on PD-1/PD-L1/CTLA-4 therapy develops suspected immune-related adverse events and needs grading or management guidance.
tool_type: python
primary_tool: guideline_search
---

# 免疫相关不良反应（irAE）识别与分级管理

免疫检查点抑制剂把"刹车"松开，代价是免疫系统可能误伤正常器官。
irAE 的处理逻辑和化疗毒性完全不同：核心不是减量，而是**按器官、按级别**决定
要不要上糖皮质激素、要不要永久停药、要不要拉专科会诊。这个 Skill 把零散的
"皮疹了怎么办、转氨酶升了怎么办"收敛成一套可执行的分级处置框架。

> 本 Skill 只做**证据梳理与分级建议**，不替代主管医师下医嘱。所有阈值以
> CSCO/NCCN 当年版指南为准，用 `guideline_search` 拉最新版核对，不要凭记忆。

## 一、先定性：是不是 irAE

ICI 毒性的鉴别诊断常被忽略——发热不一定是 irAE，也可能是感染或肿瘤热。
落级别之前先排除"长得像 irAE 的非 irAE"：

| 疑似表现 | 必须先排除 |
|----------|-----------|
| 转氨酶升高 | 病毒性肝炎、药物性肝损（其他合并用药）、胆道梗阻、肝转移进展 |
| 腹泻 | 感染性肠炎（艰难梭菌/CMV）、肿瘤相关、其他药物 |
| 呼吸困难 | 肺部感染、肿瘤进展、肺栓塞、心源性 |
| 乏力 + 低钠 | 肾上腺功能不全 vs 垂体炎 vs 甲减——内分泌 irAE 常被当成"化疗后虚弱"漏掉 |

> 时间线是关键线索：irAE 多在用药后 **数周至数月** 出现，皮肤毒性最早、
> 内分泌与肝毒居中、肺炎与肾炎偏晚；CTLA-4 联合方案毒性更早更重。

## 二、CTCAE 分级 → 处置阶梯（通用骨架）

绝大多数器官系统共用同一套阶梯逻辑，差异在阈值与器官特异监测：

| 级别 | 通用处置原则 | ICI 用药 |
|------|-------------|----------|
| G1 | 对症支持，密切观察 | 多数可继续，加强监测 |
| G2 | 泼尼松 0.5–1 mg/kg/d；症状持续按 G3 升级 | 暂停，缓解至 ≤G1 再评估复用 |
| G3 | 甲泼尼龙 1–2 mg/kg/d，住院；48–72h 无改善加用免疫抑制剂（英夫利昔单抗/麦考酚酯等，按器官选） | 暂停，多数需永久停用（高危器官） |
| G4 | 甲泼尼龙 1–2 mg/kg/d 起，ICU 级别支持 | 永久停用 |

**激素减量铁律**：起效后维持，再用 **≥4–6 周** 缓慢减量，骤停易反跳。
长期激素 + 免疫抑制需预防机会性感染（PJP 预防、监测血糖/骨密度）。

## 三、高危器官的特异性要点（必须单独记）

| 器官 | 红旗 | 与通用阶梯的差异 |
|------|------|-----------------|
| 心肌炎 | 肌钙蛋白↑ + 新发心律失常/心衰 | **死亡率极高**，G1 即住院、大剂量激素，可越级到冲击；任何级别原则永久停用 |
| 肺炎 | 影像磨玻璃/实变 + 氧合下降 | G2 即暂停，G3/G4 永久停；激素无效早上英夫利昔/麦考酚酯 |
| 肝炎 | 转氨酶/胆红素↑ | 英夫利昔单抗**禁用**（肝毒性），二线选麦考酚酯 |
| 结肠炎 | 腹泻 + 便血/腹痛 | G2 持续即用英夫利昔单抗；穿孔风险高需外科警戒 |
| 内分泌（甲状腺/垂体/肾上腺） | 激素轴紊乱 | **激素替代为主、不一定停 ICI**；肾上腺危象需立即氢化可的松，是急症 |
| 1 型糖尿病 | 高血糖 + 酮症 | 胰岛素替代，激素无效（β 细胞已毁），属不可逆 |

## 四、推荐调用工序

落具体分级与剂量阈值前，先用工具把"当年版指南原文"拉出来核对，避免记忆漂移：

```
# 1) 拉 CSCO 免疫检查点抑制剂相关毒性管理指南当年版
guideline_search(action="search_guideline", keyword="CSCO 免疫检查点抑制剂 毒性管理 2026")

# 2) 需要分级阈值的循证溯源时查文献
pubmed_search(query="immune-related adverse events management grade guideline", max_results=10)

# 3) 正文里引用的指南条目/PMID 用反向锚核验，未命中标出而非替换
citation_resolve(ids=["PMID:33198853"])
```

涉及器官 irAE 的临床决策（停药 vs 继续、激素 vs 加免疫抑制剂）若多视角分歧，
主 agent 可 `convene_council` 召集肿瘤内科 + 相应专科（心内/呼吸/消化/内分泌）表态仲裁。

## 五、给主 agent 的输出纪律

- 先报"分级 + 依据的指标"，再报处置；缺关键指标（肌钙蛋白、转氨酶具体值、氧合）
  一律 `ask_user` 追问，**绝不假设正常**
- 心肌炎、肺炎、神经系统（重症肌无力/脑炎）、肾上腺危象按**急症**优先级提示
- 永久停用 vs 暂停后复用是高权重决策，明确写出依据器官与级别
- 所有阈值标注指南来源与版本年份

## References

- CSCO《免疫检查点抑制剂相关的毒性管理指南》（人民卫生出版社，按当年最新版）
- NCCN Guidelines: Management of Immunotherapy-Related Toxicities（当年版）
- Brahmer JR, et al. ASCO Clinical Practice Guideline on irAE management. [PMID:29442540]
- Schneider BJ, et al. ASCO Guideline Update. [PMID:34255976]

## Related Skills

- clinical-oncology-management/antineoplastic-ddi-check - 抗肿瘤药物相互作用核查
- clinical-oncology-management/organ-function-dose-adjust - 脏器功能剂量调整
- china-clinical-guidelines/csco-guideline-fetch - CSCO 指南抓取
- china-clinical-guidelines/drug-label-lookup - 药品说明书查询
