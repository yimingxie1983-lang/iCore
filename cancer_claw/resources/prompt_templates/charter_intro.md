下面这份**任务契约（CHARTER）**是你和用户对一个**多阶段长任务**的共同承诺。
它是跨阶段、跨会话、跨 compact 的真相源 —— 比当前 PLAN.md 稳定（PLAN 每阶段重写），
比项目记忆紧急（项目记忆是事后沉淀）。**整个长任务结束前它都会留在这里。**

## 你和契约的关系（每轮都重读，不要忘）

1. **阶段进度表是账本**：哪个阶段在做、哪些已经 ✓、哪些还 ⏳，以它为准；不要靠对话历史回忆。
2. **阶段完成的唯一标记动作**是先 `task_charter(action="advance_stage", result_summary=...)`，紧接着 `attempt_completion(result=...)`。
   - **不能默默继续做下一阶段**。一次流必须以 `attempt_completion` 结束，让框架触发"进化链 → digests 落盘"，否则本阶段对未来的你完全不可见。
   - 调完 `advance_stage` 没调 `attempt_completion` = 阶段没真正完成（用户在前端看不到完成报告）。
3. **关键事件随手记**：完成一个有意义的工具回合后，调一次 `task_charter(action="log_event", text=...)`。
   框架会自动防抖（同字段 60s 内多次写只生效最后一次）+ 滑动窗口截断到最近 10 条，不会污染 prefix cache。
4. **决策与阻塞**用 `update_decision` / `update_blocker` 维护，让长任务的"为什么这么选 / 卡在哪"被持久化。
5. **整个任务全部完成**（所有阶段都 ✓）时调 `task_charter(action="finalize", final_summary=...)`，
   框架会归档到 `workspace/docs/charters/` 并删掉 `workspace/CHARTER.md`，避免下次误识别为进行中。

## 注意

- 这份 CHARTER 不是 PLAN 的替代品 —— 每阶段开始前仍然可以走 `enter_plan_mode` 写本阶段的 PLAN.md。
- 这份 CHARTER 的内容会在**每一轮 chat 开始时**重新从 `workspace/CHARTER.md` 读取注入；
  也就是说：你的 `task_charter` 工具调用对它的修改，**下一轮**才会反映在这里 —— 同一轮内以工具返回的 output 为准。

---
