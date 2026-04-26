import io
import json
import os
import shutil
import tempfile
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from typing import Optional

from aqt import mw
from aqt.operations import QueryOp

from ..resources import addon_dir

REPO_OWNER = "h0tp-ftw"
REPO_NAME = "ankimon"
GITHUB_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
DOWNLOAD_TIMEOUT = 30


def _api_get(endpoint: str) -> Optional[dict]:
    url = f"{GITHUB_API}/{endpoint}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _fetch_gitignore_patterns() -> list[str]:
    url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/.gitignore"
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as resp:
            lines = resp.read().decode().splitlines()
        patterns = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cleaned = line.replace("src/Ankimon/", "").strip("/")
            if cleaned:
                patterns.append(cleaned)
        return patterns
    except Exception:
        return []


def _should_preserve(rel_path: str, gitignore_patterns: list[str]) -> bool:
    for pattern in gitignore_patterns:
        if pattern.endswith("/"):
            if rel_path.startswith(pattern) or rel_path.startswith(pattern.rstrip("/")):
                return True
        elif pattern.endswith("/*"):
            prefix = pattern[:-2]
            if rel_path.startswith(prefix + "/") or rel_path == prefix:
                return True
        elif "*" in pattern:
            import fnmatch
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(os.path.basename(rel_path), pattern):
                return True
        else:
            if rel_path == pattern or rel_path.startswith(pattern + "/"):
                return True
    always_preserve = ["user_files/sprites/", "user_files/ankimon.db", "meta.json"]
    for p in always_preserve:
        if rel_path.startswith(p) or rel_path == p:
            return True
    return False


def fetch_tags() -> list[dict]:
    data = _api_get("tags")
    if not data:
        return []
    return [{"name": t["name"], "zipball_url": t["zipball_url"]} for t in data]


def fetch_releases() -> list[dict]:
    data = _api_get("releases")
    if not data:
        return []
    return [{"name": r["tag_name"], "body": r.get("body", ""), "zipball_url": r["zipball_url"]} for r in data]


def fetch_branches() -> list[dict]:
    data = _api_get("branches")
    if not data:
        return []
    return [{"name": b["name"]} for b in data]


def fetch_open_prs() -> list[dict]:
    data = _api_get("pulls?state=open&per_page=50")
    if not data:
        return []
    return [{"number": pr["number"], "title": pr["title"], "head_ref": pr["head"]["ref"], "head_sha": pr["head"]["sha"]} for pr in data]


def _download_zip(url: str, progress_cb=None) -> Optional[bytes]:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            data = bytearray()
            chunk_size = 64 * 1024
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                data.extend(chunk)
                if progress_cb and total > 0:
                    progress_cb(len(data), total)
            return bytes(data)
    except Exception:
        return None


def _download_branch_zip(branch: str, progress_cb=None) -> Optional[bytes]:
    url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{branch}.zip"
    return _download_zip(url, progress_cb)


def _download_pr_zip(head_sha: str, progress_cb=None) -> Optional[bytes]:
    url = f"{GITHUB_API}/zipball/{head_sha}"
    return _download_zip(url, progress_cb)


def apply_update(zip_data: bytes, status_cb=None) -> tuple[bool, str]:
    def log(msg):
        if status_cb:
            status_cb(msg)

    log("Fetching latest .gitignore from main...")
    gitignore_patterns = _fetch_gitignore_patterns()
    if not gitignore_patterns:
        gitignore_patterns = [
            "user_files/mypokemon.json", "user_files/mainpokemon.json",
            "user_files/badges.json", "user_files/items.json",
            "user_files/data.json", "user_files/team.json",
            "user_files/config.obf", "user_files/pokemon_history.json",
            "user_files/rate_this.json", "user_files/backups",
            "user_files/todays_shop.json", "user_files/meta.json",
            "user_files/download_complete.flag", "user_files/ankimon.db",
            "user_files/json/*", "user_files/sprites/",
            "meta.json", "*.pyc", "*.log",
        ]
        log("Could not fetch .gitignore, using fallback preserve list.")

    log("Extracting update archive...")
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_data))
    except zipfile.BadZipFile:
        return False, "Downloaded file is not a valid ZIP archive."

    names = zf.namelist()
    if not names:
        return False, "ZIP archive is empty."

    prefix = names[0]
    src_prefix = None
    for name in names:
        if name.endswith("src/Ankimon/"):
            src_prefix = name
            break
    if not src_prefix:
        for name in names:
            if "src/Ankimon/__init__.py" in name:
                src_prefix = name.rsplit("src/Ankimon/__init__.py", 1)[0] + "src/Ankimon/"
                break
    if not src_prefix:
        return False, "Could not find src/Ankimon/ in the archive."

    log("Identifying files to preserve...")
    preserved_files = {}
    for root, dirs, files in os.walk(addon_dir):
        for fname in files:
            full_path = Path(root) / fname
            rel = str(full_path.relative_to(addon_dir)).replace("\\", "/")
            if _should_preserve(rel, gitignore_patterns):
                try:
                    preserved_files[rel] = full_path.read_bytes()
                except Exception:
                    pass
    log(f"Preserving {len(preserved_files)} user files.")

    log("Removing old addon files...")
    for root, dirs, files in os.walk(addon_dir, topdown=False):
        for fname in files:
            full_path = Path(root) / fname
            rel = str(full_path.relative_to(addon_dir)).replace("\\", "/")
            if not _should_preserve(rel, gitignore_patterns):
                try:
                    full_path.unlink()
                except Exception:
                    pass
        for dname in dirs:
            dir_path = Path(root) / dname
            try:
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
            except Exception:
                pass

    log("Installing new files...")
    installed = 0
    for name in names:
        if not name.startswith(src_prefix) or name == src_prefix:
            continue
        rel_path = name[len(src_prefix):]
        if not rel_path or rel_path.endswith("/"):
            continue
        if _should_preserve(rel_path, gitignore_patterns):
            continue
        dest = addon_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_bytes(zf.read(name))
            installed += 1
        except Exception:
            pass

    log("Restoring preserved files...")
    for rel, data in preserved_files.items():
        dest = addon_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_bytes(data)
        except Exception:
            pass

    zf.close()
    log(f"Update complete. Installed {installed} files, preserved {len(preserved_files)} user files.")
    return True, f"Update applied successfully. Please restart Anki."
