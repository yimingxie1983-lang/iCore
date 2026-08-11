# Council 议题

${question}

${snapshot_section}
${stance_hint_block}# 你的任务

基于你的人格视角与上面【冻结的事实卷宗】，对议题给出独立表态。【不要附议、不要等待其它角色】——你看不到他们在想什么。

# 输出方式

直接用 markdown 写出你的完整表态——这是你向议会主席汇报视角的主要载体，
有多少话说多少话，不要压缩成口号。建议结构：

  1. 一句话立场（"从外科角度，我支持/反对/有条件支持 X"）
  2. 分点依据（解剖学评估 / 生理评估 / 证据等级 / 风险点）
  3. 给其他科的话（"如新辅助降期可切，我接手"）
  4. 你目前不敢拍板的问题（缺什么事实 / 哪条证据薄）

引用事实时直接在正文里用 `[PMID:38453234]` / `[NCCN HCC v2.2025]` / `[case:patient_age]`
这样的形式标注。

# 末尾结构化信号（推荐但非强制）

上层会用你 markdown 的引用做冲突矩阵，但如果你愿意在**最后一段**追加下面这个
JSON 代码块，可以让信号更精准。**只追加一次，而且必须在你回复的最末尾**：

```json
{"evidence_refs": ["PMID:38453234", "case:patient_age"], "open_questions": ["缺 PD-L1 数据"]}
```

注意：
- **不要**在正文中段插入示例 JSON 块或者格式占位符（如 `<填写表态>`）——
  上层会从你回复的末尾取 JSON，如果中段有 JSON 会造成混淆。
- 如果你只想写 markdown 不写 JSON，**完全 OK**——上层会从 markdown 抽引用。
- JSON 写不规范或者忘记写**不会让你的表态作废**，但加了能让信号更稳。

# 硬约束（违反会被内核拒）

- 你看不到其它角色的表态（互不可见），不要写「我同意 X 医生」这种话
- 你的工具集由人格 suggested_tools 决定；当 suggested_tools 为空时（典型 MDT 场景），
  事实只在卷宗里——缺事实请写进 open_questions 或 markdown 里点名，**不要凭模型记忆补**
- 不能在 sub-agent 子上下文里再调用 dispatch_squad / convene_council / as_persona /
  switch_persona（内核 _depth>0 一律拒）
- 引用 snapshot 之外的 ref 不会让你失败，但会触发一条软警告事件给前端看见
