---
name: model-design-from-brief
description: 根据自然语言任务描述与数据路径设计可在本机执行的训练方案，写出 DESIGN.json 与 train.py。用于对话里「帮我按这个描述训一个模型」。遵守本机 8GB 显存边界，禁止默认安装 CPU 版 torch。
tool_type: python
primary_tool: sklearn
---

# 根据描述设计训练方案

把用户的一句话需求收成 `workspace/runs/<run_id>/DESIGN.json`，再写可复现的 `train.py`。  
由 **模型训练工程师**（`ml_engineer`）在对话里用 `train_run` 设计、确认并监管。向用户解释方案时用自然语言，不要让用户去点任何训练专用按钮或进度条。

## 必做步骤

1. 先探运行时（不要猜）：
   - 用 `train_run(action=runtime)`，解释器是配置里的 `training.python`（默认 `D:\icore-ml\venv`），**禁止**往 iCore 应用 `.venv` 里 `pip install torch`。
   - 没有 CUDA 就在方案里写 `cpu` / `cpu_fallback`，不要装 CPU 版 torch 充数。
2. 看数据：表格（csv）还是图像；标签列是哪一列；样本量。把用户上传路径放进 `attached_files`。
3. `train_run(action=design, brief=..., attached_files=[...])` 写出 `DESIGN.json`，字段必须齐全：

```json
{
  "task_type": "classification",
  "model_family": "sklearn",
  "architecture_summary": "StandardScaler + RandomForest",
  "data": {"path": "", "n_samples": 0, "n_features": 0, "format": "csv", "label_column": "label", "attached": []},
  "metrics": ["accuracy", "auc"],
  "device": "cpu",
  "feasibility": "ok",
  "feasibility_reason": "",
  "batch_size": 32,
  "epochs": 5,
  "estimated_minutes": 3,
  "script_path": "workspace/runs/<id>/train.py",
  "python_exe": "",
  "hyperparams": {"random_state": 42}
}
```

`feasibility` 只能是 `ok` | `cpu_fallback` | `too_large`。

4. 把方案用白话说给用户（模型族、设备、可行性、预估时长），`ask_user` 问是否开训。

## 选型闸门（必须遵守）

| 任务 | 默认 | 本机边界 |
| --- | --- | --- |
| 表格分类 / 回归 / 组学标志物 | sklearn（CPU） | 可以训 |
| 小图像分类 | 2–3 层 CNN；有 CUDA 用 `cuda` | 8GB 显存够 |
| 7B+ 全量微调、EnFormer、chromBPNet、多机 | `too_large` | 直接拒绝并给降级 |

降级方向：更小骨干、QLoRA、或退回 sklearn。不要为了显得能干而写出训不完的方案。

## 训练怎么跑

- 设计阶段产出 JSON + 脚本即可。对话里解释这份 JSON，不要另写一套对不上的散文方案。
- **开训必须等用户在对话里明确同意**（「开训 / 确认 / 开始 / 可以」）后 `train_run(action=confirm)`。不要在 design 后立刻 confirm。
- 监管进程执行 `{training.python} -u train.py`，不要用 `as_persona`，不要自己 `run_background` 再死循环刷日志。
- 用户问进度 → `train_run(action=status)` 或 `log`，用一两句话汇报 epoch / 指标 / 错误。用户说停 → `cancel`。
- 脚本每个 epoch `print(..., flush=True)`，结束必须打印 `=== TRAINING DONE ===`。
- 产物：`models/best_model.*`、`results/metrics.json`、可选曲线图。
- 没有独立的「模型训练」页面，也没有专用进度条或按钮。
