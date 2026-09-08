from pathlib import Path

import pytest

from cancer_claw.capabilities.toolkit.workspace import build_workspace_for_local_root
from cancer_claw.client.cli import parse_argv
from cancer_claw.client.project import local_project_id, normalize_local_root


def test_parse_chat_default():
    args = parse_argv([])
    assert args.command == "chat"
    assert args.prompt is None
    assert args.resume is None


def test_parse_chat_with_prompt():
    args = parse_argv(["查一下这个目录"])
    assert args.command == "chat"
    assert args.prompt == "查一下这个目录"


def test_parse_exec():
    args = parse_argv(["exec", "总结 README"])
    assert args.command == "exec"
    assert args.prompt == "总结 README"
    assert args.resume is None


def test_parse_exec_after_cd_flag():
    args = parse_argv(["-C", "D:/tmp/work", "exec", "hello"])
    assert args.command == "exec"
    assert args.prompt == "hello"
    assert args.workdir.replace("\\", "/").endswith("tmp/work") or "work" in args.workdir


def test_parse_resume_last():
    args = parse_argv(["resume"])
    assert args.command == "chat"
    assert args.resume == "LAST"
    assert args.prompt is None


def test_parse_resume_id():
    args = parse_argv(["resume", "abc123"])
    assert args.command == "chat"
    assert args.resume == "abc123"


def test_local_project_id_is_stable_and_casefold():
    a = Path("D:/Demo/Project")
    b = Path("d:/demo/project")
    # On Windows these resolve to the same path; on others they may differ.
    # The hasher casefolds the resolved string, so equal resolve() => equal id.
    ra = str(normalize_local_root(a)).replace("\\", "/").casefold()
    rb = str(normalize_local_root(b)).replace("\\", "/").casefold()
    if ra == rb:
        assert local_project_id(a) == local_project_id(b)
    assert len(local_project_id(Path.cwd())) == 12


def test_build_workspace_for_local_root_anchors_at_cwd():
    import tempfile

    with tempfile.TemporaryDirectory(dir=".") as raw:
        tmp_path = Path(raw).resolve()
        ws = build_workspace_for_local_root(tmp_path, "abc123def456")
        assert ws.project_id == "abc123def456"
        assert ws.default_relative_root == tmp_path
        assert ws.project_root == tmp_path
        assert ws.resolved_project_id() == "abc123def456"


@pytest.mark.asyncio
async def test_ensure_local_project_creates_row():
    import tempfile

    from cancer_claw.config import settings
    from cancer_claw.db import close_db, get_db, init_db
    from cancer_claw.client.project import ensure_local_project, local_project_id

    old_db = settings.database.path
    old_projects = settings.paths.projects_dir
    with tempfile.TemporaryDirectory(dir=".") as raw:
        base = Path(raw).resolve()
        settings.database.path = str(base / "client.db")
        settings.paths.projects_dir = str(base / "projects")
        work = base / "repo"
        work.mkdir()
        try:
            await close_db()
            await init_db()
            pid, root = await ensure_local_project(work)
            assert pid == local_project_id(work)
            assert root == work.resolve()
            db = await get_db()
            cur = await db.execute(
                "SELECT name, workspace_path, source FROM projects WHERE id = ?", (pid,)
            )
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == "repo"
            assert Path(row[1]).resolve() == work.resolve()
            assert row[2] == "cli_local"
            pid2, _ = await ensure_local_project(work)
            assert pid2 == pid
        finally:
            await close_db()
            settings.database.path = old_db
            settings.paths.projects_dir = old_projects
