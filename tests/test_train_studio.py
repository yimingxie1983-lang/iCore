from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import pytest

from cancer_claw.services.training.designer import compose_design
from cancer_claw.services.training.schema import FEASIBLE_OK, FEASIBLE_TOO_LARGE


def _solve_challenge(challenge):
    m = re.match(r"(\d+)\s*\+\s*(\d+) = \?", challenge["question"])
    assert m, challenge["question"]
    return str(int(m.group(1)) + int(m.group(2)))


async def _register(client, username="trainer"):
    resp = await client.get("/api/auth/captcha")
    assert resp.status_code == 200, resp.text
    challenge = resp.json()
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "StrongPass1!",
            "email": f"{username}@example.com",
            "display_name": username,
            "captcha": {"id": challenge["id"], "answer": _solve_challenge(challenge)},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_compose_tabular_uses_sklearn_cpu(tmp_path, monkeypatch):
    from cancer_claw.config import settings

    monkeypatch.setattr(settings.paths, "projects_dir", str(tmp_path))
    (tmp_path / "proj1" / "workspace").mkdir(parents=True)
    doc = compose_design(
        project_id="proj1",
        run_id="run1",
        brief="用表格做三分类，主指标 AUC",
    )
    assert doc.model_family == "sklearn"
    assert doc.device == "cpu"
    assert doc.feasibility == FEASIBLE_OK
    assert (tmp_path / "proj1" / "workspace" / "runs" / "run1" / "DESIGN.json").exists()
    assert (tmp_path / "proj1" / "workspace" / "runs" / "run1" / "train.py").exists()


def test_compose_too_large_rejected(tmp_path, monkeypatch):
    from cancer_claw.config import settings

    monkeypatch.setattr(settings.paths, "projects_dir", str(tmp_path))
    (tmp_path / "proj1" / "workspace").mkdir(parents=True)
    doc = compose_design(
        project_id="proj1",
        run_id="run2",
        brief="从零全量微调 70B LLaMA，多机集群",
    )
    assert doc.feasibility == FEASIBLE_TOO_LARGE
    assert doc.script_path == ""


def test_compose_image_cuda_uses_cnn(tmp_path, monkeypatch):
    from cancer_claw.config import settings
    from cancer_claw.services.training import designer as designer_mod
    from cancer_claw.services.training.runtime import GpuInfo, TrainingRuntime

    monkeypatch.setattr(settings.paths, "projects_dir", str(tmp_path))
    (tmp_path / "proj1" / "workspace").mkdir(parents=True)
    monkeypatch.setattr(
        designer_mod,
        "probe_runtime",
        lambda: TrainingRuntime(
            python=sys.executable,
            python_ready=True,
            cuda_available=True,
            gpu=GpuInfo(name="NVIDIA GeForce RTX 4060 Laptop GPU", memory_total_mb=8188),
            sklearn_ready=True,
        ),
    )
    doc = compose_design(
        project_id="proj1",
        run_id="run3",
        brief="做一个小图像分类 CNN",
    )
    assert doc.model_family == "small_cnn"
    assert doc.device == "cuda"
    assert doc.feasibility == FEASIBLE_OK


@pytest.mark.asyncio
async def test_train_runtime_and_state_machine(client, tmp_path, monkeypatch):
    from cancer_claw.config import settings

    monkeypatch.setattr(settings.training, "python", sys.executable)
    monkeypatch.setattr(settings.sandbox, "mode", "off")

    user = await _register(client, "train_user")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    resp = await client.get("/api/train/runtime", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "cuda_available" in body
    assert "python_ready" in body

    resp = await client.post("/api/projects", json={"name": "训练项目"}, headers=headers)
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]

    resp = await client.post(
        f"/api/projects/{pid}/train/runs",
        json={"brief": "表格三分类，标签 group，主指标 AUC"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["status"] == "awaiting_confirm"
    assert run["design"]["model_family"] == "sklearn"
    assert run["design"]["device"] == "cpu"
    run_id = run["id"]

    resp = await client.post(
        f"/api/projects/{pid}/train/runs/{run_id}/confirm",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"

    final = None
    for _ in range(40):
        await asyncio.sleep(0.25)
        resp = await client.get(f"/api/projects/{pid}/train/runs/{run_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        final = resp.json()
        if final["status"] in {"succeeded", "failed"}:
            break
    assert final is not None
    assert final["status"] in {"succeeded", "failed"}
    if final["status"] == "succeeded":
        assert final.get("metrics")


def test_read_log_skips_sandbox_header_and_parses_epoch(tmp_path):
    from cancer_claw.capabilities.toolkit.executor.bg_log import HEADER_RESERVED_BYTES
    from cancer_claw.services.training.jobs import parse_progress, read_log

    head = b"---\npid: 1\ncommand: python train.py\n---\n"
    padded = head + b" " * (HEADER_RESERVED_BYTES - len(head) - 1) + b"\n"
    assert len(padded) == HEADER_RESERVED_BYTES
    body = (
        b"[2026-09-07T17:54:11] [stdout] iCore train start\n"
        b"epoch=2/5 loss=0.12 acc=0.80\n"
        b"=== TRAINING DONE ===\n"
    )
    path = tmp_path / "bg-1.log"
    path.write_bytes(padded + body)
    text, nxt = read_log(str(path), offset=0, limit=8000)
    assert "iCore train start" in text
    assert "epoch=2/5" in text
    assert "pid: 1" not in text
    assert nxt > HEADER_RESERVED_BYTES
    progress = parse_progress(text, {"status": "running"})
    assert progress["epoch"] == 2
    assert progress["epochs"] == 5
    assert progress["percent"] == 100
    assert progress["done"] is True


@pytest.mark.asyncio
async def test_too_large_cannot_confirm(client, monkeypatch):
    from cancer_claw.config import settings

    monkeypatch.setattr(settings.training, "python", sys.executable)
    monkeypatch.setattr(settings.sandbox, "mode", "off")

    user = await _register(client, "train_big")
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    resp = await client.post("/api/projects", json={"name": "大模型"}, headers=headers)
    pid = resp.json()["id"]
    resp = await client.post(
        f"/api/projects/{pid}/train/runs",
        json={"brief": "70B 全量微调 llama from scratch"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["id"]
    assert resp.json()["design"]["feasibility"] == "too_large"
    resp = await client.post(
        f"/api/projects/{pid}/train/runs/{run_id}/confirm",
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cancel_only_kills_this_run(client, tmp_path, monkeypatch):
    from cancer_claw.config import settings
    from cancer_claw.capabilities.toolkit.workspace import get_project_workspace_root

    monkeypatch.setattr(settings.training, "python", sys.executable)
    monkeypatch.setattr(settings.sandbox, "mode", "off")

    user = await _register(client, "train_cancel")
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    resp = await client.post("/api/projects", json={"name": "取消训练"}, headers=headers)
    pid = resp.json()["id"]
    resp = await client.post(
        f"/api/projects/{pid}/train/runs",
        json={"brief": "表格分类小任务"},
        headers=headers,
    )
    run_id = resp.json()["id"]
    script = get_project_workspace_root(pid) / "runs" / run_id / "train.py"
    script.write_text(
        "import time\nprint('sleep', flush=True)\ntime.sleep(30)\nprint('done', flush=True)\n",
        encoding="utf-8",
    )
    resp = await client.post(
        f"/api/projects/{pid}/train/runs/{run_id}/confirm",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"
    resp = await client.post(
        f"/api/projects/{pid}/train/runs/{run_id}/cancel",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"
    Path(tmp_path).mkdir(exist_ok=True)


@pytest.mark.asyncio
async def test_train_run_tool_design_without_auto_confirm(client, monkeypatch):
    from cancer_claw.config import settings
    from cancer_claw.capabilities.toolkit.builtins.train_run import TrainRunTool
    from cancer_claw.capabilities.toolkit.registry import (
        CORE_TOOL_NAMES,
        ML_ENGINEER_PERSONA_TOOLS,
        get_registry,
        reset_registry,
    )

    monkeypatch.setattr(settings.training, "python", sys.executable)
    monkeypatch.setattr(settings.sandbox, "mode", "off")

    user = await _register(client, "train_tool")
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    me = user.get("user") or (await client.get("/api/auth/me", headers=headers)).json()
    resp = await client.post("/api/projects", json={"name": "对话训练"}, headers=headers)
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]

    reset_registry()
    registry = get_registry()
    assert "train_run" in CORE_TOOL_NAMES
    assert "train_run" in ML_ENGINEER_PERSONA_TOOLS
    assert registry.get_tool("train_run") is not None

    tool = TrainRunTool()
    runtime = await tool.execute(action="runtime", _current_user=me)
    assert runtime.success, runtime.error

    designed = await tool.execute(
        action="design",
        brief="表格三分类，主指标 AUC",
        project_id=pid,
        _current_user=me,
    )
    assert designed.success, designed.error
    assert designed.data.get("status") == "awaiting_confirm"
    assert "ask_user" in (designed.output or "") or "同意" in (designed.output or "")

    listed = await tool.execute(
        action="list",
        project_id=pid,
        _current_user=me,
    )
    assert listed.success, listed.error
    assert designed.data.get("id") in (listed.output or "")

