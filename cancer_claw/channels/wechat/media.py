"""微信 CDN AES-ECB 加解密与上传下载。"""

from __future__ import annotations

import hashlib
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cancer_claw.channels.wechat.api import WeixinOfficialApi

try:
    from Crypto.Cipher import AES  # type: ignore
except Exception:  # pragma: no cover
    AES = None  # type: ignore


UploadMediaType = {
    "IMAGE": 1,
    "VIDEO": 2,
    "FILE": 3,
    "VOICE": 4,
}


def aes_ecb_padded_size(plaintext_size: int) -> int:
    return ((plaintext_size + 1 + 15) // 16) * 16


def _pkcs7_pad(data: bytes) -> bytes:
    pad = 16 - (len(data) % 16)
    return data + bytes([pad] * pad)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    pad = data[-1]
    if pad < 1 or pad > 16:
        return data
    return data[:-pad]


def encrypt_aes_ecb(plaintext: bytes, key: bytes) -> bytes:
    if AES is None:
        raise RuntimeError("需要 pycryptodome：pip install pycryptodome")
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(_pkcs7_pad(plaintext))


def decrypt_aes_ecb(ciphertext: bytes, key: bytes) -> bytes:
    if AES is None:
        raise RuntimeError("需要 pycryptodome：pip install pycryptodome")
    cipher = AES.new(key, AES.MODE_ECB)
    return _pkcs7_unpad(cipher.decrypt(ciphertext))


def encode_weixin_media_aes_key(aes_key_hex: str) -> str:
    import base64

    return base64.b64encode(aes_key_hex.encode("ascii")).decode("ascii")


def parse_aes_key_base64(aes_key_b64: str) -> bytes:
    import base64

    decoded = base64.b64decode(aes_key_b64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32 and all(chr(b) in "0123456789abcdefABCDEF" for b in decoded):
        return bytes.fromhex(decoded.decode("ascii"))
    raise ValueError("invalid aes_key payload")


def build_cdn_download_url(encrypted_query_param: str, cdn_base_url: str) -> str:
    return (
        f"{cdn_base_url.rstrip('/')}/download?"
        f"encrypted_query_param={urllib.parse.quote(encrypted_query_param)}"
    )


def build_cdn_upload_url(*, cdn_base_url: str, upload_param: str, filekey: str) -> str:
    return (
        f"{cdn_base_url.rstrip('/')}/upload?"
        f"encrypted_query_param={urllib.parse.quote(upload_param)}"
        f"&filekey={urllib.parse.quote(filekey)}"
    )


@dataclass
class UploadedFileInfo:
    filekey: str
    download_encrypted_query_param: str
    aeskey: str  # 32-char hex
    file_size: int
    file_size_ciphertext: int
    file_md5: str


def upload_file_to_cdn(
    api: WeixinOfficialApi,
    *,
    file_path: Path,
    to_user_id: str,
    media_type: int = UploadMediaType["FILE"],
) -> UploadedFileInfo:
    plaintext = Path(file_path).read_bytes()
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext).hexdigest()
    filesize = aes_ecb_padded_size(rawsize)
    filekey = secrets.token_hex(16)
    aeskey = secrets.token_bytes(16)
    aeskey_hex = aeskey.hex()

    upload_resp = api.get_upload_url(
        {
            "filekey": filekey,
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aeskey_hex,
        }
    )
    upload_full_url = str(upload_resp.get("upload_full_url") or "").strip()
    upload_param = str(upload_resp.get("upload_param") or "").strip()
    if upload_full_url:
        cdn_url = upload_full_url
    elif upload_param:
        cdn_url = build_cdn_upload_url(
            cdn_base_url=api.cdn_base_url,
            upload_param=upload_param,
            filekey=filekey,
        )
    else:
        raise RuntimeError("CDN upload URL missing")

    ciphertext = encrypt_aes_ecb(plaintext, aeskey)
    req = urllib.request.Request(
        cdn_url,
        data=ciphertext,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        download_param = resp.headers.get("x-encrypted-param") or ""
        if resp.status != 200 or not download_param:
            raise RuntimeError(f"CDN upload failed status={resp.status}")

    return UploadedFileInfo(
        filekey=filekey,
        download_encrypted_query_param=download_param,
        aeskey=aeskey_hex,
        file_size=rawsize,
        file_size_ciphertext=filesize,
        file_md5=rawfilemd5,
    )


def download_and_decrypt(
    *,
    encrypted_query_param: str,
    aes_key_b64: str,
    cdn_base_url: str,
    full_url: str | None = None,
) -> bytes:
    url = full_url or build_cdn_download_url(encrypted_query_param, cdn_base_url)
    if not url:
        raise RuntimeError("media download url missing")
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            encrypted = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"CDN download failed: {e.code}") from e
    key = parse_aes_key_base64(aes_key_b64)
    return decrypt_aes_ecb(encrypted, key)


def infer_media_type(path: Path) -> int:
    ext = path.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return UploadMediaType["IMAGE"]
    if ext in {".mp4", ".mov", ".avi"}:
        return UploadMediaType["VIDEO"]
    if ext in {".silk", ".wav", ".mp3", ".amr"}:
        return UploadMediaType["VOICE"]
    return UploadMediaType["FILE"]


def build_media_item(path: Path, uploaded: UploadedFileInfo) -> dict[str, Any]:
    media_type = infer_media_type(path)
    aes_wire = encode_weixin_media_aes_key(uploaded.aeskey)
    media = {
        "encrypt_query_param": uploaded.download_encrypted_query_param,
        "aes_key": aes_wire,
        "encrypt_type": 1,
    }
    if media_type == UploadMediaType["IMAGE"]:
        return {
            "type": 2,
            "image_item": {
                "media": media,
                "mid_size": uploaded.file_size_ciphertext,
            },
        }
    if media_type == UploadMediaType["VIDEO"]:
        return {
            "type": 5,
            "video_item": {
                "media": media,
                "video_size": uploaded.file_size_ciphertext,
                "video_md5": uploaded.file_md5,
            },
        }
    return {
        "type": 4,
        "file_item": {
            "media": media,
            "file_name": path.name,
            "md5": uploaded.file_md5,
            "len": str(uploaded.file_size),
        },
    }
