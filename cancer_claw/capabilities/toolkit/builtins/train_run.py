from __future__ import annotations

from typing import Any

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.services.training.ops import (
    TrainOpError,
    cancel_run,
    confirm_run,
    create_run,
    list_runs,
    pick_run,
    pick_run_for_confirm,
    public_run,
    read_run_log,
    runtime_info,
)

_ACTIONS = ("runtime", "design", "confirm", "cancel", "status", "log", "list")
_WRITE_ACTIONS = frozenset({"design", "confirm", "cancel"})


def _attached_paths(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            path = str(item.get("path") or "").strip()
            if path:
                out.append(path)
    return out


def _summarize(run: dict[str, Any]) -> str:
    design = run.get("design") or {}
    progress = run.get("progress") or {}
    lines = [
        f"run_id={run.get('id')}  status={run.get('status')}",
        f"可行性={design.get('feasibility') or '—'}  模型族={design.get('model_family') or '—'}"
        f"  设备={design.get('device') or '—'}  任务={design.get('task_type') or '—'}",
    ]
    if design.get("architecture_summary"):
        lines.append(f"结构：{design['architecture_summary']}")
    if design.get("feasibility_reason"):
        lines.append(f"说明：{design['feasibility_reason']}")
    if design.get("estimated_minutes"):
        lines.append(f"预估约 {design['estimated_minutes']} 分钟")
    if design.get("script_path"):
        lines.append(f"脚本：{design['script_path']}")
    last = progress.get("last_line") or ""
    if progress.get("epoch") and progress.get("epochs"):
        lines.append(f"进度：epoch {progress['epoch']}/{progress['epochs']}")
    elif progress.get("percent") not in (None, ""):
        lines.append(f"进度：{progress.get('percent')}%")
    if last:
        lines.append(f"最新日志：{last}")
    if run.get("error"):
        lines.append(f"错误：{run['error']}")
    metrics = run.get("metrics")
    if metrics:
        lines.append(f"指标：{metrics}")
    artifacts = run.get("artifacts") or []
    if artifacts:
        names = "、".join(str(a.get("name") or a.get("path")) for a in artifacts[:8])
        lines.append(f"产物：{names}")
    status = run.get("status")
    if status == "awaiting_confirm":
        if design.get("feasibility") == "too_large":
            lines.append("本机训不了。请改 brief 降级（更小骨干 / sklearn）后再 design。")
        else:
            lines.append(
                "方案已写好。用自然语言把可行性、模型族、设备、预估时长讲给用户，"
                "再用 ask_user 问是否开训。用户口头同意后再 train_run(action=confirm)，不要立刻 confirm。"
            )
    elif status == "running":
        lines.append(
            "训练已在沙箱后台跑。不要 as_persona 死等、不要自己刷几个小时日志；"
            "把当前进度用一两句话告诉用户，等用户再问或过一阵再用 status/log 看一眼。"
        )
    elif status == "succeeded":
        lines.append("训练完成。读 metrics / 用 present_file 交产物，不要再 confirm。")
    return "\n".join(lines)


async def _ensure_access(
    project_id: str,
    user: dict[str, Any] | None,
    *,
    write: bool,
) -> str | None:
    if not project_id:
        return "请先在对话工作台打开项目，或用 project_open 切到目标项目。"
    if not user:
        return "无登录用户上下文，无法监管训练。"
    from cancer_claw.services.identity.deps import compute_project_role

    project, role = await compute_project_role(user, project_id)
    if project is None or role is None:
        return f"项目 {project_id} 不存在，或你没有访问权限。"
    if not write:
        return None
    status = project.get("status") or "active"
    if status == "frozen":
        return "项目已冻结，仅可查看。"
    if role == "viewer":
        return "只读成员无法开训或取消训练。"
    if status == "paused":
        return "项目已暂停，无法发起训练。"
    return None


class TrainRunTool(BaseTool):
    name = "train_run"
    description = (
        "在当前项目里设计并监管本机模型训练。"
        "长训必须用本工具（任务监管 + training.python），不要 as_persona 死等，"
        "不要 run_background 后再刷几个小时日志，禁止往 iCore 应用 .venv 里 pip install torch。"
        "流程：runtime → design(brief, attached_files) → 把方案讲给用户 → "
        "用户同意后 confirm → status/log 查看进度 → 完成后读 metrics。"
        "不要在 design 之后立刻 confirm。"
    )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": list(_ACTIONS),
                            "description": (
                                "runtime=探测本机 CUDA/训练环境；"
                                "design=根据 brief 生成 DESIGN.json 与 train.py（待确认）；"
                                "confirm=用户明确同意后启动沙箱长训；"
                                "status=查看当前或指定任务；"
                                "log=拉取训练日志；"
                                "list=最近任务；"
                                "cancel=取消正在跑的任务。"
                            ),
                        },
                        "brief": {
                            "type": "string",
                            "description": "design 时必填：用户的一句话任务描述",
                        },
                        "attached_files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "workspace 相对路径，来自用户上传的数据文件",
                        },
                        "run_id": {
                            "type": "string",
                            "description": "任务 id；省略则取正在跑的，否则最近一条",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "log 的字节偏移，默认 0",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = str(kwargs.get("action") or "").strip().lower()
        if action not in _ACTIONS:
            return ToolResult(
                success=False,
                error=f"未知 action={action}，可选：{', '.join(_ACTIONS)}",
            )

        if action == "runtime":
            info = runtime_info()
            bits = [
                f"python_ready={info.get('python_ready')}",
                f"cuda_available={info.get('cuda_available')}",
                f"sklearn_ready={info.get('sklearn_ready')}",
            ]
            gpu = info.get("gpu") or {}
            if gpu.get("name"):
                bits.append(f"gpu={gpu.get('name')} {gpu.get('memory_total_mb') or 0}MB")
            if info.get("hint"):
                bits.append(str(info["hint"]))
            if info.get("setup_hint") and not info.get("python_ready"):
                bits.append(str(info["setup_hint"]))
            return ToolResult(success=True, output="；".join(bits), data=info)

        project_id = str(kwargs.get("project_id") or "").strip()
        agent = kwargs.get("_agent")
        if not project_id and agent is not None:
            project_id = str(getattr(agent, "_evolution_project_id", "") or "").strip()
        user: dict[str, Any] | None = kwargs.get("_current_user")
        err = await _ensure_access(
            project_id, user, write=action in _WRITE_ACTIONS
        )
        if err:
            return ToolResult(success=False, error=err)

        user_id = str((user or {}).get("id") or "")
        try:
            if action == "design":
                brief = str(kwargs.get("brief") or "").strip()
                if len(brief) < 2:
                    return ToolResult(
                        success=False,
                        error="design 需要 brief（至少两字的任务描述）。",
                    )
                run = await create_run(
                    project_id=project_id,
                    user_id=user_id,
                    brief=brief,
                    attached_files=_attached_paths(kwargs.get("attached_files")),
                )
                return ToolResult(success=True, output=_summarize(run), data=run)

            if action == "list":
                items = await list_runs(project_id, limit=20)
                if not items:
                    return ToolResult(
                        success=True,
                        output="当前项目还没有训练任务。",
                        data={"items": []},
                    )
                lines = [
                    f"- {item.get('id')}  {item.get('status')}  "
                    f"{(item.get('design') or {}).get('model_family') or ''}  "
                    f"{(item.get('brief') or '')[:48]}"
                    for item in items
                ]
                return ToolResult(
                    success=True,
                    output="最近训练任务：\n" + "\n".join(lines),
                    data={"items": items},
                )

            run_id = str(kwargs.get("run_id") or "").strip()
            if action == "confirm":
                if not run_id:
                    current = await pick_run_for_confirm(project_id, "")
                    run_id = str(current.get("id") or "")
                run = await confirm_run(project_id, run_id)
                return ToolResult(success=True, output=_summarize(run), data=run)

            if action == "cancel":
                if not run_id:
                    current = await pick_run(project_id, "")
                    run_id = str(current.get("id") or "")
                run = await cancel_run(project_id, run_id)
                return ToolResult(success=True, output=_summarize(run), data=run)

            run = await pick_run(project_id, run_id)
            if action == "status":
                return ToolResult(success=True, output=_summarize(run), data=run)

            offset = int(kwargs.get("offset") or 0)
            chunk = read_run_log(run, offset=max(0, offset), limit=6000)
            text = (chunk.get("text") or "").strip()
            tail = text[-3500:] if text else "（尚无日志）"
            return ToolResult(
                success=True,
                output=_summarize(run) + "\n--- 日志 ---\n" + tail,
                data={**public_run(run), "log": chunk},
            )
        except TrainOpError as e:
            return ToolResult(success=False, error=str(e), data={"status": e.status})
        except LookupError:
            rid = str(kwargs.get("run_id") or "")
            return ToolResult(
                success=False,
                error=f"找不到训练任务{(' ' + rid) if rid else ''}。",
            )
