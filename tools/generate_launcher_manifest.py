#!/usr/bin/env python3
"""Создать манифест самообновления для собранного лаунчера."""

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--legacy-sequence",
        choices=range(100),
        type=int,
        metavar="NN",
        help="добавить прежний суффикс NN только для переходного манифеста",
    )
    parser.add_argument("--download-url", default="https://wotlk.amatol.blog/launcher/Dreamworld.exe")
    parser.add_argument("--changelog", default="")
    args = parser.parse_args()
    if not (args.version.isdigit() and len(args.version) == 8):
        parser.error("version должна иметь формат YYYYMMDD")
    manifest_version = args.version
    if args.legacy_sequence is not None:
        manifest_version += f"{args.legacy_sequence:02d}"
    content = args.executable.read_bytes()
    manifest = {
        "version": manifest_version,
        "download_url": args.download_url,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "changelog": args.changelog,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
