

from __future__ import annotations

_LEGACY_ENCODINGS: tuple[str, ...] = ("gb18030", "gbk", "cp936")

def _try_utf8_tolerant_tail(raw: bytes) -> str | None:

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass


    for cut in (1, 2, 3):
        if cut >= len(raw):
            break
        try:
            return raw[:-cut].decode("utf-8")
        except UnicodeDecodeError:
            continue
    return None

def decode_text_bytes(raw: bytes) -> tuple[str, str]:

    if not raw:
        return "", "utf-8"


    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            pass


    text = _try_utf8_tolerant_tail(raw)
    if text is not None:
        return text, "utf-8"


    for enc in _LEGACY_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue


    return raw.decode("latin-1", errors="replace"), "latin-1"

def encoding_for_text_open(raw_sample: bytes) -> str:

    _, enc = decode_text_bytes(raw_sample)

    if raw_sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if enc == "utf-8-sig":
        return "utf-8"
    return enc
