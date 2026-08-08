#!/usr/bin/env python3
"""Создать детерминированный манифест файлов WoW-клиента."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote


EXCLUDED_PARTS = {".launcher_tmp", ".git"}
EXCLUDED_NAMES = {".launcher_version", "Dreamworld.exe", "Repair.log"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(source: Path, version: str, base_url: str, previous: dict = None) -> dict:
    if not (version.isdigit() and len(version) == 8):
        raise ValueError("version должна иметь формат YYYYMMDD")
    files = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if relative.name in EXCLUDED_NAMES or relative.name.endswith((".bak", ".part")):
            continue
        posix_path = relative.as_posix()
        encoded_path = "/".join(quote(part) for part in relative.parts)
        files.append({
            "path": posix_path,
            "size": path.stat().st_size,
            "sha256": sha256(path),
            "http_url": f"{base_url.rstrip('/')}/files/{encoded_path}",
        })
    manifest = {"version": version, "files": files}
    if previous is not None:
        current_paths = {entry["path"] for entry in files}
        previous_paths = {entry["path"] for entry in previous.get("files", [])}
        manifest["removed_files"] = sorted(previous_paths - current_paths)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Папка эталонного WoW-клиента")
    parser.add_argument("output", type=Path, help="Путь manifest.json")
    parser.add_argument("--version", required=True)
    parser.add_argument("--base-url", default="https://wotlk.amatol.blog/launcher")
    parser.add_argument("--previous-manifest", type=Path)
    args = parser.parse_args()
    if not args.source.is_dir():
        parser.error(f"Папка не существует: {args.source}")
    previous = None
    if args.previous_manifest:
        previous = json.loads(args.previous_manifest.read_text(encoding="utf-8"))
    manifest = build_manifest(args.source.resolve(), args.version, args.base_url, previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
