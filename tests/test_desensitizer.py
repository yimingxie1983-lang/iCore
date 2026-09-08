import pytest

from cancer_claw.config import settings
from cancer_claw.services.privacy.desensitizer import (
    desensitize_file,
    desensitize_messages,
    desensitize_text,
    is_textual_upload,
)


@pytest.fixture(autouse=True)
def _privacy_strict():
    old = {
        "enabled": settings.privacy.enabled,
        "mode": settings.privacy.mode,
        "on_upload": settings.privacy.desensitize_on_upload,
        "before_llm": settings.privacy.desensitize_before_llm,
        "on_chat": settings.privacy.desensitize_on_chat_input,
        "on_persist": getattr(settings.privacy, "desensitize_on_persist", True),
    }
    settings.privacy.enabled = True
    settings.privacy.mode = "strict"
    settings.privacy.desensitize_on_upload = True
    settings.privacy.desensitize_before_llm = True
    settings.privacy.desensitize_on_chat_input = True
    settings.privacy.desensitize_on_persist = True
    yield
    settings.privacy.enabled = old["enabled"]
    settings.privacy.mode = old["mode"]
    settings.privacy.desensitize_on_upload = old["on_upload"]
    settings.privacy.desensitize_before_llm = old["before_llm"]
    settings.privacy.desensitize_on_chat_input = old["on_chat"]
    settings.privacy.desensitize_on_persist = old["on_persist"]


def test_desensitize_id_card_and_phone():
    raw = "患者身份证110101199001011234，手机13812345678"
    result = desensitize_text(raw)
    assert "[脱敏:身份证]" in result.text
    assert "[脱敏:手机号]" in result.text
    assert "110101199001011234" not in result.text
    assert "13812345678" not in result.text
    assert result.changed
    assert result.hits.get("id_card") == 1
    assert result.hits.get("phone") == 1


def test_desensitize_labeled_name_and_mrn():
    raw = "姓名：张三，病历号：MR2024011588"
    result = desensitize_text(raw)
    assert "[脱敏:姓名]" in result.text
    assert "[脱敏:病历号]" in result.text
    assert "张三" not in result.text
    assert "MR2024011588" not in result.text


def test_desensitize_email():
    raw = "联系邮箱 patient@hospital.cn 请回复"
    result = desensitize_text(raw)
    assert "[脱敏:邮箱]" in result.text
    assert "patient@hospital.cn" not in result.text


def test_audit_only_does_not_replace():
    settings.privacy.mode = "audit_only"
    raw = "手机13812345678"
    result = desensitize_text(raw)
    assert result.text == raw
    assert result.hits.get("phone") == 1
    assert not result.changed


def test_disabled_returns_original():
    settings.privacy.enabled = False
    raw = "手机13812345678"
    result = desensitize_text(raw)
    assert result.text == raw
    assert not result.changed


def test_desensitize_messages_multimodal():
    messages = [
        {"role": "user", "content": "身份证110101199001011234"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "手机13812345678"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        },
    ]
    out = desensitize_messages(messages)
    assert "[脱敏:身份证]" in out[0]["content"]
    assert "[脱敏:手机号]" in out[1]["content"][0]["text"]
    assert out[1]["content"][1]["type"] == "image_url"


def test_is_textual_upload():
    assert is_textual_upload("report.csv")
    assert is_textual_upload("notes.MD")
    assert is_textual_upload("notes.docx")
    assert is_textual_upload("scan.dcm")
    assert not is_textual_upload("photo.png")


def test_desensitize_file_writes_back(tmp_path):
    f = tmp_path / "patient.txt"
    f.write_text("姓名：李四，手机13900001111", encoding="utf-8")
    result = desensitize_file(f)
    assert result.changed
    saved = f.read_text(encoding="utf-8")
    assert "[脱敏:姓名]" in saved
    assert "[脱敏:手机号]" in saved
    assert "李四" not in saved


def test_scan_file_does_not_modify(tmp_path):
    from cancer_claw.services.privacy.desensitizer import scan_file, summarize_hits_zh

    f = tmp_path / "patient.txt"
    raw = "姓名：赵六，手机13900002222，身份证110101199001011234"
    f.write_text(raw, encoding="utf-8")
    result = scan_file(f)
    assert not result.changed
    assert f.read_text(encoding="utf-8") == raw
    assert result.hits.get("phone") == 1
    assert result.hits.get("id_card") == 1
    assert result.hits.get("name") == 1
    assert "姓名" in summarize_hits_zh(result.hits)


def test_unlabeled_patient_phrase_not_treated_as_name():
    raw = "基于以上病历做诊断，并考虑到患者经济条件情况用医保"
    result = desensitize_text(raw)
    assert "患者经济" in result.text
    assert "[脱敏:姓名]" not in result.text


def test_labeled_landline_only():
    raw = "联系电话：010-65551234，另有编号 76543210"
    result = desensitize_text(raw)
    assert "[脱敏:电话]" in result.text
    assert "010-65551234" not in result.text
    assert "76543210" in result.text


def test_unlabeled_digit_run_is_not_bank_card():
    raw = "session 1787216073718123 and hash 1234567890123456"
    result = desensitize_text(raw)
    assert "[脱敏:银行卡]" not in result.text
    assert "1787216073718123" in result.text


def test_visa_test_card_is_masked():
    raw = "卡 4111111111111111"
    result = desensitize_text(raw)
    assert "[脱敏:银行卡]" in result.text
    assert "4111111111111111" not in result.text


def test_backfill_conversation_and_workspace(tmp_path):
    import sqlite3

    from cancer_claw.services.privacy.backfill import backfill_database, backfill_workspace

    db = tmp_path / "t.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE conversation_history ("
        "id INTEGER PRIMARY KEY, content TEXT, tool_calls_json TEXT, name TEXT)"
    )
    con.execute(
        "CREATE TABLE chat_sessions (session_id TEXT PRIMARY KEY, title TEXT, preview TEXT)"
    )
    con.execute(
        "INSERT INTO conversation_history(content, tool_calls_json, name) VALUES (?,?,?)",
        ("姓名：王五，手机13800138000", None, None),
    )
    con.execute(
        "INSERT INTO chat_sessions(session_id, title, preview) VALUES (?,?,?)",
        ("s1", "姓名：王五就诊", ""),
    )
    con.commit()
    stats = backfill_database(con, dry_run=False)
    row = con.execute("SELECT content FROM conversation_history").fetchone()[0]
    title = con.execute("SELECT title FROM chat_sessions").fetchone()[0]
    con.close()
    assert stats["conversation_rows_changed"] == 1
    assert "[脱敏:姓名]" in row
    assert "[脱敏:手机号]" in row
    assert "13800138000" not in row
    assert "[脱敏:姓名]" in title

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "note.md").write_text("病历号：MR999888", encoding="utf-8")
    file_stats = backfill_workspace(ws, dry_run=False)
    saved = (ws / "note.md").read_text(encoding="utf-8")
    assert file_stats["files_changed"] == 1
    assert "[脱敏:病历号]" in saved
    assert "MR999888" not in saved
