#!/usr/bin/env python3
"""Build minimal Apple and Google Wallet resume passes without dependencies."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "wallet" / "out"


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def need(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing {name}; set it in .env")
    return value


def resume_url() -> str:
    value = need("RESUME_URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit("RESUME_URL must be an absolute HTTPS URL")
    return value


def localized(value: str) -> dict:
    return {"defaultValue": {"language": "en-US", "value": value}}


def png(path: Path, size: int, color=(24, 43, 77)) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\0" + bytes(color) * size for _ in range(size))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def build_apple() -> Path:
    url = resume_url()
    label = os.getenv("PASS_LABEL", "Resume")
    cert = ROOT / need("APPLE_PASS_CERT")
    key = ROOT / need("APPLE_PASS_KEY")
    wwdr = ROOT / need("APPLE_WWDR_CERT")
    for path in (cert, key, wwdr):
        if not path.is_file():
            raise SystemExit(f"Missing credential file: {path}")

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="resume-pass-") as directory:
        source = Path(directory)
        pass_data = {
            "formatVersion": 1,
            "passTypeIdentifier": need("APPLE_PASS_TYPE_ID"),
            "serialNumber": "resume",
            "teamIdentifier": need("APPLE_TEAM_ID"),
            "organizationName": label,
            "description": f"{label} card",
            "logoText": label,
            "foregroundColor": "rgb(255, 255, 255)",
            "backgroundColor": "rgb(24, 43, 77)",
            "generic": {
                "primaryFields": [{"key": "title", "label": "", "value": label}],
                "backFields": [{"key": "website", "label": "Website", "value": url}],
            },
            "barcodes": [{
                "format": "PKBarcodeFormatQR",
                "message": url,
                "messageEncoding": "iso-8859-1",
                "altText": url,
            }],
        }
        (source / "pass.json").write_text(json.dumps(pass_data, separators=(",", ":")))
        for name, size in (("icon.png", 29), ("icon@2x.png", 58), ("icon@3x.png", 87)):
            png(source / name, size)

        manifest = {
            item.name: hashlib.sha1(item.read_bytes()).hexdigest()
            for item in source.iterdir()
        }
        manifest_path = source / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, separators=(",", ":")))
        command = [
            "openssl", "smime", "-binary", "-sign", "-outform", "DER",
            "-signer", str(cert), "-inkey", str(key), "-certfile", str(wwdr),
            "-in", str(manifest_path), "-out", str(source / "signature"),
        ]
        if os.getenv("APPLE_KEY_PASSWORD"):
            command.extend(["-passin", "env:APPLE_KEY_PASSWORD"])
        subprocess.run(command, check=True)

        output = OUT / "resume.pkpass"
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in source.iterdir():
                archive.write(item, item.name)
    return output


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def compact(data: dict) -> bytes:
    return json.dumps(data, separators=(",", ":"), sort_keys=True).encode()


def build_google() -> Path:
    url = resume_url()
    label = os.getenv("PASS_LABEL", "Resume")
    issuer_id = need("GOOGLE_ISSUER_ID")
    account_path = ROOT / need("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not account_path.is_file():
        raise SystemExit(f"Missing credential file: {account_path}")
    account = json.loads(account_path.read_text())
    class_id = f"{issuer_id}.resume"
    object_id = f"{issuer_id}.resume_card"
    claims = {
        "iss": account["client_email"],
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "origins": [urlparse(url).netloc],
        "payload": {
            "genericClasses": [{"id": class_id}],
            "genericObjects": [{
                "id": object_id,
                "classId": class_id,
                "state": "ACTIVE",
                "cardTitle": localized(label),
                "header": localized("Resume"),
                "hexBackgroundColor": "#182b4d",
                "barcode": {"type": "QR_CODE", "value": url, "alternateText": url},
                "appLinkData": {
                    "displayText": localized("Open resume"),
                    "webAppLinkInfo": {
                        "appTarget": {"targetUri": {"uri": url, "description": "Open resume"}}
                    },
                },
                "linksModuleData": {"uris": [{"uri": url, "description": "Open resume", "id": "resume"}]},
            }],
        },
    }
    header = {"alg": "RS256", "typ": "JWT"}
    if account.get("private_key_id"):
        header["kid"] = account["private_key_id"]
    unsigned = f"{b64url(compact(header))}.{b64url(compact(claims))}".encode()

    key_path = None
    try:
        with tempfile.NamedTemporaryFile("w", prefix="google-wallet-", delete=False) as key_file:
            key_file.write(account["private_key"])
            key_path = key_file.name
        signature = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=unsigned,
            check=True,
            capture_output=True,
        ).stdout
    finally:
        if key_path:
            Path(key_path).unlink(missing_ok=True)

    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "google-wallet.url"
    output.write_text(f"https://pay.google.com/gp/v/save/{unsigned.decode()}.{b64url(signature)}\n")
    return output


def main() -> None:
    load_env()
    target = sys.argv[1] if len(sys.argv) == 2 else ""
    builders = {"apple": build_apple, "google": build_google}
    if target not in builders:
        raise SystemExit("Usage: wallet/build.py apple|google")
    print(builders[target]())


if __name__ == "__main__":
    main()
