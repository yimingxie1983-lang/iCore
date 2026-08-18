import pytest

from cancer_claw.capabilities.toolkit.builtins.present_file import (
    PresentFileTool,
    coerce_present_paths,
)
from cancer_claw.capabilities.toolkit.workspace import (
    ToolWorkspaceContext,
    tool_workspace_scope,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (["JS001_Phase1_Protocol_V1.0.docx"], ["JS001_Phase1_Protocol_V1.0.docx"]),
        (
            '["JS001_Phase1_Protocol_V1.0.docx"]',
            ["JS001_Phase1_Protocol_V1.0.docx"],
        ),
        (
            '["workspace/JS001_Phase1_Protocol_V1.0.docx"]',
            ["workspace/JS001_Phase1_Protocol_V1.0.docx"],
        ),
        (
            '["docs/00_总交付摘要.md", "docs/阶段4_最优路线详细研究方案.md"]',
            ["docs/00_总交付摘要.md", "docs/阶段4_最优路线详细研究方案.md"],
        ),
        ("a.md, b.md", ["a.md", "b.md"]),
        ("hello.md", ["hello.md"]),
        ('"hello.md"', ["hello.md"]),
        ([], []),
        (None, []),
    ],
)
def test_coerce_present_paths(raw, expected):
    assert coerce_present_paths(raw) == expected


@pytest.mark.asyncio
async def test_present_file_accepts_json_array_string(tmp_path):
    project_root = tmp_path / "proj"
    workspace = project_root / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "hello.md").write_text("# hi\n", encoding="utf-8")
    ctx = ToolWorkspaceContext(
        project_root=project_root.resolve(),
        default_relative_root=workspace.resolve(),
        project_id="demo",
    )
    tool = PresentFileTool()
    with tool_workspace_scope(ctx):
        result = await tool.execute(paths='["hello.md"]', title="交付")
    assert result.success, result.error
    files = (result.data or {}).get("presentation", {}).get("files") or []
    assert len(files) == 1
    assert files[0]["name"] == "hello.md"
    assert files[0]["path"].replace("\\", "/").endswith("workspace/hello.md")
