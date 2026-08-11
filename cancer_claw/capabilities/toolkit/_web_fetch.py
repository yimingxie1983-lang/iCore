

from __future__ import annotations

import asyncio
import gzip
import html as _html
import http.client
import re
import ssl
import zlib
from urllib.parse import urljoin, urlparse

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_RE_META_CHARSET = re.compile(
    rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.IGNORECASE
)
_RE_SCRIPT_STYLE = re.compile(
    r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_MULTISPACE = re.compile(r"[ \t\r\f\v]+")
_RE_MULTINEWLINE = re.compile(r"\n{3,}")

_TLS_FINGERPRINT_HINTS = (
    "UNEXPECTED_EOF",
    "EOF occurred",
    "record layer failure",
    "handshake",
)

class WebFetchError(Exception):
    pass

def html_to_text(html: str) -> str:

    if not html:
        return ""
    text = _RE_SCRIPT_STYLE.sub(" ", html)
    text = _RE_TAG.sub("\n", text)
    text = _html.unescape(text)
    text = _RE_MULTISPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _RE_MULTINEWLINE.sub("\n\n", text).strip()

def _decompress(raw: bytes, encoding: str) -> bytes:

    enc = (encoding or "").lower()
    if "gzip" in enc:
        try:
            return gzip.decompress(raw)
        except OSError:
            return raw
    if "deflate" in enc:

        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                return zlib.decompress(raw, wbits)
            except zlib.error:
                continue
    return raw

def _decode_text(raw: bytes, content_type: str) -> str:


    charset = ""
    m = re.search(r"charset=([a-zA-Z0-9_\-]+)", content_type or "", re.IGNORECASE)
    if m:
        charset = m.group(1)

    if not charset:
        mm = _RE_META_CHARSET.search(raw[:2048])
        if mm:
            charset = mm.group(1).decode("ascii", "ignore")

    if charset.lower() in ("gb2312", "gbk"):
        charset = "gb18030"
    for enc in (charset, "utf-8", "gb18030"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue

    return raw.decode("utf-8", "ignore")

def _fetch_once(url: str, headers: dict, timeout: float) -> tuple[int, bytes, str | None, str]:

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise WebFetchError(f"不支持的协议: {parsed.scheme}")

    host = parsed.hostname or ""
    port = parsed.port
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    if parsed.scheme == "https":

        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(host, port or 443, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(host, port or 80, timeout=timeout)

    try:
        conn.request("GET", path, headers={**headers, "Host": parsed.netloc})
        resp = conn.getresponse()
        raw = resp.read()
        raw = _decompress(raw, resp.getheader("Content-Encoding", ""))
        return (
            resp.status,
            raw,
            resp.getheader("Location"),
            resp.getheader("Content-Type", ""),
        )
    finally:
        conn.close()

def fetch_text_blocking(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 20.0,
    max_redirects: int = 5,
) -> tuple[int, str, str]:

    base_headers = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
    }
    if headers:
        base_headers.update(headers)

    current = url
    last_status = 0
    last_ctype = ""
    for _ in range(max_redirects + 1):
        try:
            status, raw, location, ctype = _fetch_once(current, base_headers, timeout)
        except (OSError, ssl.SSLError, http.client.HTTPException) as e:
            raise WebFetchError(str(e)) from e

        last_status, last_ctype = status, ctype
        if status in (301, 302, 303, 307, 308) and location:
            current = urljoin(current, location)
            continue
        return status, _decode_text(raw, ctype), current


    return last_status, "", current

async def fetch_text(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 20.0,
    max_redirects: int = 5,
) -> tuple[int, str, str]:

    return await asyncio.to_thread(
        fetch_text_blocking,
        url,
        headers=headers,
        timeout=timeout,
        max_redirects=max_redirects,
    )

def looks_like_tls_fingerprint_block(err: object) -> bool:

    text = str(err)
    return any(hint in text for hint in _TLS_FINGERPRINT_HINTS)
