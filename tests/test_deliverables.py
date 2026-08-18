from pathlib import Path

from cancer_claw.services.deliverables import deliverable_group, list_workspace_deliverables


def test_lists_stage_outputs_skips_scripts_and_logs(tmp_path: Path):
    ws = tmp_path / "workspace"
    (ws / "docs" / "charters").mkdir(parents=True)
    (ws / "scripts").mkdir()
    (ws / "logs").mkdir()
    (ws / "habitat" / "voxfeat").mkdir(parents=True)
    (ws / "docs" / "阶段1_报告.md").write_text("one", encoding="utf-8")
    (ws / "docs" / "charters" / "task.md").write_text("charter", encoding="utf-8")
    (ws / "habitat" / "L1_QC报告.md").write_text("qc", encoding="utf-8")
    (ws / "habitat" / "fig_tsne.png").write_bytes(b"png")
    (ws / "habitat" / "habitat_full.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (ws / "schema.json").write_text("{}", encoding="utf-8")
    (ws / "plan.docx").write_bytes(b"docx")
    (ws / "notes.txt").write_text("txt", encoding="utf-8")
    (ws / "brief.pdf").write_bytes(b"%PDF")
    (ws / "habitat" / "voxfeat" / "a.npz").write_bytes(b"npz")
    (ws / "scripts" / "full_scan.py").write_text("print(1)", encoding="utf-8")
    (ws / "logs" / "bg.log").write_text("log", encoding="utf-8")
    (ws / "full_scan.py").write_text("print(2)", encoding="utf-8")
    (ws / "nii_probe.txt").write_text("probe", encoding="utf-8")
    (ws / "deliver_summary.md").write_text("sum", encoding="utf-8")

    items = list_workspace_deliverables(tmp_path)
    paths = {it["path"] for it in items}
    assert "workspace/docs/阶段1_报告.md" in paths
    assert "workspace/docs/charters/task.md" not in paths
    assert "workspace/habitat/L1_QC报告.md" in paths
    assert "workspace/habitat/fig_tsne.png" in paths
    assert "workspace/schema.json" in paths
    assert "workspace/plan.docx" in paths
    assert "workspace/deliver_summary.md" in paths
    assert "workspace/habitat/habitat_full.csv" in paths
    assert "workspace/notes.txt" in paths
    assert "workspace/brief.pdf" in paths
    assert "workspace/scripts/full_scan.py" not in paths
    assert "workspace/logs/bg.log" not in paths
    assert "workspace/full_scan.py" not in paths
    assert "workspace/nii_probe.txt" not in paths
    assert "workspace/habitat/voxfeat/a.npz" not in paths
    groups = {it["path"]: it["group"] for it in items}
    assert groups["workspace/docs/阶段1_报告.md"] == "阶段文档"
    assert groups["workspace/habitat/L1_QC报告.md"] == "Habitat"
    assert deliverable_group("workspace/manuscript/paper.md") == "文稿"
