"""医院场景 PHI/PII 脱敏：在上传、对话入站、LLM 出站前统一处理。"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from cancer_claw.config import settings

logger = structlog.get_logger()

_LABELED_RULES = {"mrn", "name", "landline"}
_OFFICE_EXT = {".docx", ".xlsx"}
_DICOM_EXT = {".dcm", ".dicom"}
_MAX_TEXT_BYTES = 8_000_000

_MASK = {
    "id_card": "[脱敏:身份证]",
    "phone": "[脱敏:手机号]",
    "landline": "[脱敏:电话]",
    "mrn": "[脱敏:病历号]",
    "name": "[脱敏:姓名]",
    "address": "[脱敏:地址]",
    "email": "[脱敏:邮箱]",
    "bank_card": "[脱敏:银行卡]",
    "passport": "[脱敏:护照]",
}

_RULE_PATTERNS: dict[str, re.Pattern[str]] = {
    "id_card": re.compile(
        r"(?<!\d)"
        r"(?:[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"
        r"|[1-9]\d{7}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3})"
        r"(?!\d)"
    ),
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "landline": re.compile(
        r"(?:(?:座机号?|固话|联系电话|电话)\s*[:：]\s*)"
        r"((?:0\d{2,3}[-\s]?)?\d{7,8})(?!\d)"
    ),
    "mrn": re.compile(
        r"(?:(?:病历号|住院号|门诊号|患者编号|病案号|就诊卡号|医保卡号|卡号)"
        r"[:：\s]*)([A-Za-z0-9]{4,20})",
        re.IGNORECASE,
    ),
    "name": re.compile(
        r"(?:(?:患者姓名|病人姓名|姓名|患者|病人)\s*[:：]\s*)"
        r"([\u4e00-\u9fff]{2,4})(?![\u4e00-\u9fff])"
    ),
    "address": re.compile(
        r"(?:[\u4e00-\u9fff]{2,8}(?:省|市|自治区|特别行政区))"
        r"[\u4e00-\u9fff\d\-#]{2,36}"
        r"(?:号楼?|栋|单元|室|村|街|路|巷|大道)"
    ),
    "email": re.compile(
        r"(?<![\w.@+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.@+-])"
    ),
    "bank_card": re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)"),
    "passport": re.compile(
        r"(?<![A-Za-z0-9])(?:[EeGg]\d{8}|[PpSs]\d{7}|[Dd]\d{8})(?![A-Za-z0-9])"
    ),
}


@dataclass
class DesensitizeResult:
    text: str
    hits: dict[str, int] = field(default_factory=dict)
    changed: bool = False

    @property
    def total_hits(self) -> int:
        return sum(self.hits.values())


def _privacy_cfg():
    return settings.privacy


def _enabled_rules(*, force: bool = False) -> list[str]:
    cfg = _privacy_cfg()
    if not force and (not cfg.enabled or cfg.mode == "off"):
        return []
    allowed = set(cfg.rules) if cfg.rules else set(_RULE_PATTERNS)
    return [r for r in _RULE_PATTERNS if r in allowed]


def _luhn_ok(num: str) -> bool:
    digits = [int(c) for c in num if c.isdigit()]
    if not (16 <= len(digits) <= 19):
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _looks_like_bank_card(raw: str) -> bool:
    digits = "".join(c for c in raw if c.isdigit())
    if not _luhn_ok(digits):
        return False
    return digits.startswith(("4", "5", "62", "35", "37", "34", "60"))


def _apply_rule(text: str, rule: str, *, audit_only: bool) -> tuple[str, int]:
    pattern = _RULE_PATTERNS[rule]
    mask = _MASK[rule]
    count = 0

    if rule == "bank_card":
        def repl(m: re.Match[str]) -> str:
            nonlocal count
            if not _looks_like_bank_card(m.group(0)):
                return m.group(0)
            count += 1
            return m.group(0) if audit_only else mask

        return pattern.sub(repl, text), count

    if rule in _LABELED_RULES:
        def repl(m: re.Match[str]) -> str:
            nonlocal count
            count += 1
            prefix = m.group(0)[: m.start(1) - m.start()]
            return prefix + (m.group(1) if audit_only else mask)

        return pattern.sub(repl, text), count

    if audit_only:
        count = len(pattern.findall(text))
        return text, count

    def repl(_: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return mask

    return pattern.sub(repl, text), count


def desensitize_text(
    text: str, *, context: str = "", force: bool = False
) -> DesensitizeResult:
    """对纯文本执行脱敏；audit_only 模式仅统计命中，不替换。force 时始终替换。"""
    cfg = _privacy_cfg()
    if not text:
        return DesensitizeResult(text=text)
    if not force and (not cfg.enabled or cfg.mode == "off"):
        return DesensitizeResult(text=text)

    audit_only = (not force) and cfg.mode == "audit_only"
    out = text
    hits: dict[str, int] = {}
    for rule in _enabled_rules(force=force):
        out, n = _apply_rule(out, rule, audit_only=audit_only)
        if n:
            hits[rule] = n

    changed = (not audit_only) and out != text
    if hits and not (context or "").startswith("backfill"):
        logger.info(
            "privacy_desensitize",
            context=context or "text",
            mode="strict" if force else cfg.mode,
            hits=hits,
            changed=changed,
        )
    return DesensitizeResult(text=out, hits=hits, changed=changed)


def scan_text(text: str, *, context: str = "scan") -> DesensitizeResult:
    """仅检测敏感信息命中，不改写文本。"""
    cfg = _privacy_cfg()
    if not text or not cfg.enabled or cfg.mode == "off":
        return DesensitizeResult(text=text or "")
    hits: dict[str, int] = {}
    for rule in _enabled_rules(force=False):
        _, n = _apply_rule(text, rule, audit_only=True)
        if n:
            hits[rule] = n
    if hits and not (context or "").startswith("backfill"):
        logger.info(
            "privacy_scan",
            context=context or "scan",
            hits=hits,
            total=sum(hits.values()),
        )
    return DesensitizeResult(text=text, hits=hits, changed=False)


def _desensitize_content_part(part: Any, *, context: str) -> Any:
    if isinstance(part, str):
        return desensitize_text(part, context=context).text
    if isinstance(part, dict):
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            return {**part, "text": desensitize_text(part["text"], context=context).text}
    return part


def desensitize_messages(
    messages: list[dict], *, context: str = "llm"
) -> list[dict]:
    """脱敏 LLM 消息列表（支持 str 与多模态 content）。"""
    cfg = _privacy_cfg()
    if not cfg.enabled or cfg.mode == "off" or not cfg.desensitize_before_llm:
        return messages

    out: list[dict] = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        content = msg.get("content")
        if isinstance(content, str):
            new_content = desensitize_text(content, context=context).text
            out.append({**msg, "content": new_content})
        elif isinstance(content, list):
            new_parts = [
                _desensitize_content_part(p, context=context) for p in content
            ]
            out.append({**msg, "content": new_parts})
        else:
            out.append(msg)
    return out


def is_textual_upload(filename: str) -> bool:
    ext = Path(filename or "").suffix.lower()
    if ext in _OFFICE_EXT or ext in _DICOM_EXT:
        return True
    extra = {".jsonl", ".ipynb"}
    return ext in set(_privacy_cfg().textual_upload_extensions) | extra


def _merge_hits(dst: dict[str, int], src: dict[str, int]) -> None:
    for k, v in src.items():
        dst[k] = dst.get(k, 0) + v


def _desensitize_office(
    path: Path, *, context: str, force: bool = False
) -> DesensitizeResult:
    hits: dict[str, int] = {}
    changed = False
    buf = io.BytesIO()
    with zipfile.ZipFile(path, "r") as zin:
        with zipfile.ZipFile(buf, "w") as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                name = info.filename.lower()
                if name.endswith(".xml") or name.endswith(".rels"):
                    try:
                        text = data.decode("utf-8")
                    except UnicodeDecodeError:
                        zout.writestr(info, data)
                        continue
                    result = desensitize_text(text, context=context, force=force)
                    if result.changed:
                        changed = True
                        _merge_hits(hits, result.hits)
                        data = result.text.encode("utf-8")
                    elif result.hits:
                        _merge_hits(hits, result.hits)
                zout.writestr(info, data)
    if changed:
        path.write_bytes(buf.getvalue())
    return DesensitizeResult(text="", hits=hits, changed=changed)


def _scan_office(path: Path, *, context: str) -> DesensitizeResult:
    hits: dict[str, int] = {}
    with zipfile.ZipFile(path, "r") as zin:
        for info in zin.infolist():
            name = info.filename.lower()
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            data = zin.read(info.filename)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            result = scan_text(text, context=context)
            if result.hits:
                _merge_hits(hits, result.hits)
    return DesensitizeResult(text="", hits=hits, changed=False)


def _desensitize_dicom(path: Path, *, context: str) -> DesensitizeResult:
    try:
        import pydicom
    except ImportError:
        logger.warning("privacy_dicom_skip_no_pydicom", path=str(path.name), context=context)
        return DesensitizeResult(text="")

    patient_tags = (
        "PatientName",
        "PatientID",
        "PatientBirthDate",
        "PatientBirthTime",
        "PatientSex",
        "PatientAddress",
        "PatientTelephoneNumbers",
        "OtherPatientNames",
        "OtherPatientIDs",
        "EthnicGroup",
        "PatientComments",
    )
    try:
        header = pydicom.dcmread(str(path), stop_before_pixels=True)
    except Exception as e:
        logger.warning("privacy_dicom_read_failed", error=str(e), context=context)
        return DesensitizeResult(text="")

    pending = []
    for tag in patient_tags:
        if tag not in header:
            continue
        elem = header.data_element(tag)
        if elem is None:
            continue
        if elem.value not in ("", None, "ANONYMOUS"):
            pending.append(tag)
    if not pending:
        return DesensitizeResult(text="", hits={}, changed=False)

    try:
        ds = pydicom.dcmread(str(path))
    except Exception as e:
        logger.warning("privacy_dicom_read_failed", error=str(e), context=context)
        return DesensitizeResult(text="")

    n = 0
    for tag in pending:
        elem = ds.data_element(tag)
        if elem is None:
            continue
        empty = "ANONYMOUS" if getattr(elem, "VR", "") == "PN" else ""
        elem.value = empty
        n += 1
    if not n:
        return DesensitizeResult(text="", hits={}, changed=False)
    try:
        ds.save_as(str(path))
    except Exception as e:
        logger.warning("privacy_dicom_write_failed", error=str(e), context=context)
        return DesensitizeResult(text="")
    hits = {"dicom_patient_tag": n}
    if not context.startswith("backfill"):
        logger.info("privacy_desensitize", context=context, mode="dicom", hits=hits, changed=True)
    return DesensitizeResult(text="", hits=hits, changed=True)


def desensitize_file(
    path: Path, *, context: str = "upload", force: bool = False
) -> DesensitizeResult:
    """脱敏文本 / Office XML / DICOM 患者标签后写回。"""
    cfg = _privacy_cfg()
    suffix = path.suffix.lower()
    if not force and (not cfg.enabled or cfg.mode == "off" or not cfg.desensitize_on_upload):
        if suffix in _OFFICE_EXT or suffix in _DICOM_EXT:
            return DesensitizeResult(text="")
        raw = path.read_text(encoding="utf-8", errors="replace")
        return DesensitizeResult(text=raw)

    if suffix in _DICOM_EXT:
        return _desensitize_dicom(path, context=context)
    if suffix in _OFFICE_EXT:
        return _desensitize_office(path, context=context, force=force)

    extra = set(_privacy_cfg().textual_upload_extensions) | {".jsonl", ".ipynb", ".py", ".rst", ".tex", ".sql", ".r"}
    if suffix not in extra:
        return DesensitizeResult(text="")

    try:
        size = path.stat().st_size
    except OSError:
        return DesensitizeResult(text="")
    if size == 0 or size > _MAX_TEXT_BYTES:
        return DesensitizeResult(text="")
    raw = path.read_text(encoding="utf-8", errors="replace")
    result = desensitize_text(raw, context=context, force=force)
    if result.changed:
        path.write_text(result.text, encoding="utf-8")
    return result


def scan_file(path: Path, *, context: str = "scan") -> DesensitizeResult:
    """检测文件中的敏感信息，不改写落盘内容。"""
    cfg = _privacy_cfg()
    if not cfg.enabled or cfg.mode == "off":
        return DesensitizeResult(text="")
    suffix = path.suffix.lower()
    if suffix in _DICOM_EXT:
        # DICOM：只统计可识别的患者标签数，不写盘
        try:
            import pydicom
        except ImportError:
            return DesensitizeResult(text="")
        try:
            header = pydicom.dcmread(str(path), stop_before_pixels=True)
        except Exception:
            return DesensitizeResult(text="")
        tags = (
            "PatientName",
            "PatientID",
            "PatientBirthDate",
            "PatientBirthTime",
            "PatientSex",
            "PatientAddress",
            "PatientTelephoneNumbers",
            "OtherPatientNames",
            "OtherPatientIDs",
            "EthnicGroup",
            "PatientComments",
        )
        n = 0
        for tag in tags:
            if tag not in header:
                continue
            elem = header.data_element(tag)
            if elem is None:
                continue
            if elem.value not in ("", None, "ANONYMOUS"):
                n += 1
        hits = {"dicom_patient_tag": n} if n else {}
        return DesensitizeResult(text="", hits=hits, changed=False)
    if suffix in _OFFICE_EXT:
        return _scan_office(path, context=context)

    extra = set(cfg.textual_upload_extensions) | {".jsonl", ".ipynb", ".py", ".rst", ".tex", ".sql", ".r"}
    if suffix not in extra:
        return DesensitizeResult(text="")
    try:
        size = path.stat().st_size
    except OSError:
        return DesensitizeResult(text="")
    if size == 0 or size > _MAX_TEXT_BYTES:
        return DesensitizeResult(text="")
    raw = path.read_text(encoding="utf-8", errors="replace")
    return scan_text(raw, context=context)


HIT_LABELS_ZH: dict[str, str] = {
    "id_card": "身份证",
    "phone": "手机号",
    "landline": "电话",
    "mrn": "病历号",
    "name": "姓名",
    "address": "地址",
    "email": "邮箱",
    "bank_card": "银行卡",
    "passport": "护照",
    "dicom_patient_tag": "DICOM患者标签",
}


def summarize_hits_zh(hits: dict[str, int]) -> str:
    if not hits:
        return ""
    parts = [
        f"{HIT_LABELS_ZH.get(k, k)} {v} 处"
        for k, v in sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))
        if v > 0
    ]
    return "、".join(parts)
