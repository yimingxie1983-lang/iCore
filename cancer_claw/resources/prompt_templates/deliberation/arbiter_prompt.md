# Council 议题

${question}

${snapshot_section}

# 各角色独立表态（已去名字 / 去人格标签）

```json
${stances_json}
```

# 你的任务

按 critical_reviewer 人格的仲裁规则（证据等级 > 指南推荐 > 安全性优先 > 可逆性 > 样本规模）对上述表态做仲裁，产出 verdict。【严禁】说「建议综合评估」等废话；【严禁】引入卷宗外的事实。

**引用格式**：verdict 的 `text` 里引用文献一律用方括号标记 `[PMID:数字]`（如 `[PMID:38453234]`）、政策原文用 `[GOV:完整URL]`——前端据此渲染可核验角标。**禁止**写裸数字或缺冒号的 `PMID38453234`。

# 输出契约（务必遵守）

在你最终回复的结尾，用 ```json``` 代码块输出符合以下 schema 的 JSON：

```json
{"type": "consensus | arbitrated | escalate", "text": "<最终判定，markdown，每条结论带 Fact.ref 引用>", "conflict_matrix": [{"axis": "...", "positions": {"role_anon_0": "support|against|unknown"}}], "minority_notes": "<可选：被压下的少数派意见摘要>"}
```
