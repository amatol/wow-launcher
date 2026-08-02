#!/usr/bin/env python3
"""Package addon directories and atomically-ready metadata for publication."""
import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def package_addon(source: Path, output_dir: Path, version: str, base_url: str, description: str = "") -> dict:
    name = source.name
    if not source.is_dir() or not SAFE_NAME.fullmatch(name):
        raise ValueError(f"invalid addon directory: {source}")
    if not any(source.glob("*.toc")):
        raise ValueError(f"addon has no top-level .toc file: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{name}-{version}.zip"
    target = output_dir / filename
    fd, temporary = tempfile.mkstemp(prefix=filename + ".", suffix=".tmp", dir=output_dir)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(path, Path(name) / path.relative_to(source))
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    payload = target.read_bytes()
    return {
        "name": name,
        "version": version,
        "description": description,
        "download_url": f"{base_url.rstrip('/')}/{filename}",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="directory containing one folder per addon")
    parser.add_argument("output_dir", type=Path, help="directory for generated ZIP files")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--base-url", default="https://wotlk.amatol.blog/launcher/addons")
    args = parser.parse_args()
    entries = [package_addon(path, args.output_dir, args.version, args.base_url) for path in sorted(args.source.iterdir()) if path.is_dir()]
    if not entries:
        raise SystemExit("refusing to generate an empty addons manifest")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({"addons": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
