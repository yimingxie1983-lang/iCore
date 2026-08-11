# 反驳轮指令

# Author: OneKeyJune
# Email: onekeyjune@gmail.com

你正在参加一场 **多专家议会的第二轮（反驳轮）**。

## 上下文

**议题**：$question

**事实卷宗**（客观、可核验）：
$snapshot_section

## 你上轮的表态

$my_stance_text

## 其他专家的表态（匿名）

$other_stances_json

## 指令

1. 仔细阅读其他专家的表态——他们的论据是否有说服力？是否有新的 evidence_ref 是你遗漏的？
2. **不允许看到对方 persona 身份**——只看内容。
3. 用 **markdown** 输出你的反驳/修正意见（**完整写不要压缩**）。如果你被说服了要修改立场，坦率声明。
4. 引用事实直接在正文里用 `[PMID:xxx]` / `[case:xxx]` 标注；这是议会主席提取冲突矩阵的依据。
5. 如果愿意，可以在**最末尾**追加一个 JSON 块给信号（不强制）：

```json
{"evidence_refs": ["PMID:xxx", "case:xxx"], "changed_stance": true}
```

## 约束

- 你看不到对方 persona 身份（只看 role_anon_*）——不要写"我同意 X 医生"
- 引用 snapshot 之外的 ref 不会让你失败，但会触发软警告
- 如果你认为上轮立场完全正确无需修改，markdown 里**明确写一句**"立场不变：理由 X"
- 不要重复上轮全文——只写**增量差异**
- 不要在中段插入示例 JSON 或 `<填写...>` 占位符——议会主席从你回复末尾取 JSON
