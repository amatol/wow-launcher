#!/usr/bin/env python3
"""Установить закреплённые готовые x86_64 bottles вместе с runtime-зависимостями."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile

LOCK = Path(__file__).with_name("winecx-homebrew-lock.json")
CACHE = Path("build/winecx-bottles")


def fetch(package):
    rebuild = f".{package['rebuild']}" if package['rebuild'] else ""
    filename = f"{package['name']}--{package['version']}.{package['tag']}.bottle{rebuild}.tar.gz"
    target = CACHE / filename
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != package['sha256']:
        print(f"Скачивание готового пакета {package['name']} {package['version']}", flush=True)
        partial = target.with_suffix(".part")
        subprocess.run(["curl", "-fL", "--retry", "3", "--max-time", "180",
                        "-H", "Authorization: Bearer QQ==", package['url'], "-o", str(partial)],
                       check=True, timeout=600)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != package['sha256']:
            partial.unlink()
            raise RuntimeError("SHA-256 не совпадает: " + package['name'])
        partial.replace(target)
    with tarfile.open(target) as archive:
        formula = f"{package['name']}/{package['version']}/.brew/{package['name']}.rb"
        if not archive.getmember(formula).isfile():
            raise RuntimeError("В bottle отсутствует исходная формула: " + package['name'])
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text())
    packages = lock['packages']
    # Порядок lock-файла должен устанавливать зависимости раньше потребителей.
    installed = set()
    for p in packages:
        if p['tag'] not in ('sonoma', 'sequoia', 'all'):
            raise RuntimeError("Неподходящая архитектура bottle: " + p['name'])
        if not set(p['runtime_dependencies']).issubset(installed):
            raise RuntimeError("Нарушен порядок зависимостей: " + p['name'])
        installed.add(p['name'])
    if not set(lock['roots']).issubset(installed):
        raise RuntimeError("Неполный набор пакетов")
    if not args.download_only and (platform.system() != "Darwin" or platform.machine() != "arm64"):
        raise RuntimeError("Установка предназначена для macos-latest Apple Silicon")
    CACHE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        archives = list(pool.map(fetch, packages))
    if args.download_only:
        print(f"Все {len(archives)} bottles доступны, SHA-256 и исходные формулы проверены.")
        return
    env = os.environ.copy()
    env.update({"HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_INSTALL_UPGRADE": "1",
                "HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK": "1", "HOMEBREW_NO_INSTALL_CLEANUP": "1",
                "HOMEBREW_NO_ANALYTICS": "1"})
    brew = ["arch", "-x86_64", "/usr/local/bin/brew"]
    for package, archive in zip(packages, archives):
        print(f"Установка bottle {package['name']} {package['version']}", flush=True)
        subprocess.run([*brew, "install", "--force-bottle", "--ignore-dependencies", str(archive.resolve())],
                       env=env, check=True, timeout=180)
        receipt = Path('/usr/local/Cellar') / package['name'] / package['version'] / 'INSTALL_RECEIPT.json'
        if not json.loads(receipt.read_text()).get('poured_from_bottle'):
            raise RuntimeError("Пакет не установлен из bottle: " + package['name'])
    print("Все закреплённые x86_64-пакеты установлены из готовых bottles.", flush=True)


if __name__ == "__main__":
    main()
