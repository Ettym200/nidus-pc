"""Verifica atualizacoes no GitHub Releases."""
import json
import re
import urllib.error
import urllib.request
from typing import Optional

REPO = "Ettym200/nidus-pc"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
TIMEOUT = 8


def parse_version(tag: str) -> tuple[int, int, int]:
    nums = re.findall(r"\d+", tag or "")
    while len(nums) < 3:
        nums.append("0")
    return tuple(int(n) for n in nums[:3])


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def fetch_latest_release() -> Optional[dict]:
    req = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Nidus-Updater",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def get_download_url(release: dict) -> str:
    for asset in release.get("assets", []):
        if asset.get("name", "").lower() == "nidus.exe":
            return asset.get("browser_download_url") or release.get("html_url", "")
    return release.get("html_url", f"https://github.com/{REPO}/releases/latest")


def check_update(current_version: str, skipped_version: str = "") -> Optional[dict]:
    release = fetch_latest_release()
    if not release:
        return None

    latest = release.get("tag_name", "")
    if not latest or not is_newer(latest, current_version):
        return None
    if skipped_version and parse_version(skipped_version) >= parse_version(latest):
        return None

    return {
        "version": latest.lstrip("vV"),
        "tag": latest,
        "url": get_download_url(release),
        "page": release.get("html_url", ""),
        "notes": (release.get("body") or "").strip(),
    }
