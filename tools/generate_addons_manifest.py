#!/usr/bin/env python3
"""Generate a verified manifest for addon directories published as-is."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def describe_addon(source: Path, version: str, base_url: str, description: str = "") -> dict:
    name = source.name
    if not source.is_dir() or source.is_symlink() or not SAFE_NAME.fullmatch(name):
        raise ValueError(f"invalid addon directory: {source}")
    if not any(source.glob("*.toc")):
        raise ValueError(f"addon has no top-level .toc file: {source}")
    files = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"addon contains a symbolic link: {path}")
        if path.is_file():
            relative = path.relative_to(source).as_posix()
            digest = hashlib.sha256()
            with path.open("rb") as payload:
                for chunk in iter(lambda: payload.read(1024 * 1024), b""):
                    digest.update(chunk)
            encoded = "/".join(quote(part, safe="") for part in (name, *Path(relative).parts))
            files.append({
                "path": relative,
                "download_url": f"{base_url.rstrip('/')}/{encoded}",
                "sha256": digest.hexdigest(),
                "size": path.stat().st_size,
            })
    if not files:
        raise ValueError(f"addon has no files: {source}")
    return {"name": name, "version": version, "description": description, "files": files}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="?", default=Path("/opt/azerothcore/addons"), help="directory containing one folder per addon")
    parser.add_argument("manifest", type=Path, nargs="?", default=Path("/srv/dreamworld-launcher/addons_manifest.json"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--base-url", default="https://wotlk.amatol.blog/launcher/addons")
    args = parser.parse_args()
    entries = [describe_addon(path, args.version, args.base_url) for path in sorted(args.source.iterdir()) if path.is_dir()]
    if not entries:
        raise SystemExit("refusing to generate an empty addons manifest")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.manifest.with_suffix(args.manifest.suffix + ".tmp")
    temporary.write_text(json.dumps({"addons": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.manifest)


if __name__ == "__main__":
    main()
