r"""Release check (M10; M4 of the offline player): install, clean run, upgrade, rollback, uninstall.

Uses the installers in release/<version>/ (and a second, newer test build for the upgrade). It
installs into a throw-away folder for the current user, runs the installed program with a
stripped environment (Windows-only PATH, no Python/Babarify variables, empty profile folders),
and checks every module the running program has loaded comes from the install folder or Windows.

With --real-data <folder>, a COPY of that settings-and-library folder (normally
%APPDATA%\Babarify\Frame) is the profile's data, so the upgrade is tested on real data. The folder
itself is only read.

The throw-away install shares the app's Windows uninstall entry with a real install, and the
final uninstall removes it: reinstall the real copy afterwards (with its own tasks). Close
Babarify first: the installer closes running copies.

Usage:  python tools/release_check.py <old-setup.exe> <new-setup.exe> [out.json] [--real-data DIR]
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]

MEDIA = ROOT / "tests" / "fixtures" / "media" / "generated" / "h264_1080p30_aac.mp4"
APP_ID = "{6C6E6628-FE5B-4E93-ADA0-C13ADF7F99A2}_is1"
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
WINDOWS = os.environ.get("SYSTEMROOT", r"C:\Windows")


def clean_env(profile: Path) -> dict[str, str]:
    """What a fresh user account would have: Windows paths only, empty app-data folders."""
    # Python keeps Windows variable names in upper case.
    keep = {
        "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "NUMBER_OF_PROCESSORS", "OS",
        "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "USERNAME", "USERDOMAIN", "TEMP", "TMP",
    }  # fmt: skip
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["PATH"] = f"{WINDOWS}\\system32;{WINDOWS};{WINDOWS}\\System32\\Wbem"
    for name in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        folder = profile / name
        folder.mkdir(parents=True, exist_ok=True)
        env[name] = str(folder)
    return env


def app_of(setup: Path, target: Path) -> Path:
    """The program an installer puts in ``target``: versions before 0.10 were called Babarify Frame."""
    name = "Babarify Frame.exe" if setup.name.startswith("BabarifyFrame-") else "Babarify Media Player.exe"
    return target / name


def install(setup: Path, target: Path, log: Path, tasks: str = "") -> int:
    args = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
            f"/DIR={target}", f"/LOG={log}"]  # fmt: skip
    if tasks:
        args.append(f"/TASKS={tasks}")
    return subprocess.run(args, timeout=600).returncode


def file_version(exe: Path) -> str:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"(Get-Item '{exe}').VersionInfo.ProductVersion"],
        capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    return out.stdout.strip()


def reg_value(path: str, name: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return None


def run_app(app: Path, env: dict[str, str], media: Path, seconds: int = 20) -> dict[str, object]:
    process = psutil.Popen([str(app), str(media), "--smoke-test", str(seconds * 1000)], env=env)
    foreign: set[str] = set()
    loaded = 0
    started = time.time()
    while process.poll() is None and time.time() - started < seconds + 30:
        try:
            for item in process.memory_maps():
                path = item.path
                loaded += 1
                inside = path.lower().startswith(str(app.parent).lower())
                if not inside and not path.lower().startswith(WINDOWS.lower()):
                    foreign.add(path)
        except psutil.Error:
            pass
        time.sleep(1.0)
    code = process.wait(timeout=60)
    log = Path(env["LOCALAPPDATA"]) / "Babarify" / "Frame" / "logs" / "app.log"
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    return {
        "exit": code,
        "foreign_modules": sorted(foreign),
        "dev_paths_loaded": sorted(
            p for p in foreign if "babarify vision" in p.lower() or ".venv" in p.lower()
        ),
        "log_started": "started" in text,
        "log_played": "smoke test: state=playing" in text or "smoke test: state=paused" in text,
        "engine_ready": [line.split("INFO ")[-1] for line in text.splitlines() if "engine ready in" in line],
        "log_tail": text.strip().splitlines()[-4:],
        "crash_log": (log.parent / "crash.log").read_text(encoding="utf-8")[-400:]
        if (log.parent / "crash.log").is_file()
        else "",
    }


def library_facts(folder: Path) -> dict[str, object]:
    """What the library holds, read without changing it."""
    db = folder / "library.db"
    if not db.is_file():
        return {}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        facts: dict[str, object] = {"schema": conn.execute("PRAGMA user_version").fetchone()[0]}
        for table in ("media", "folders", "playlists", "playlist_items", "history", "favourites"):
            try:
                facts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                facts[table] = None
        return facts
    finally:
        conn.close()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def main() -> int:
    args = sys.argv[1:]
    real_data: Path | None = None
    if "--real-data" in args:
        i = args.index("--real-data")
        real_data = Path(args[i + 1])
        del args[i : i + 2]
    old_setup, new_setup = Path(args[0]), Path(args[1])
    out = Path(args[2]) if len(args) > 2 else ROOT / "release" / "release_check.json"
    work = Path(tempfile.mkdtemp(prefix="babarify-release-check-"))
    target = work / "Babarify Media Player"
    profile = work / "profile"
    env = clean_env(profile)
    results: dict[str, object] = {}
    data = profile / "APPDATA" / "Babarify" / "Frame"
    if real_data is not None:
        shutil.copytree(real_data, data, ignore=shutil.ignore_patterns("backup-*"))
        results["real_data_before"] = library_facts(data)
        settings_before = json.loads((data / "settings.json").read_text(encoding="utf-8"))
    mp4_before = reg_value(r"Software\Classes\.mp4", "")

    # 1. Fresh install of the older version, with "Open with".
    results["install_old"] = install(old_setup, target, work / "install-old.log", "openwith")
    app = app_of(old_setup, target)
    results["installed_version_old"] = file_version(app)
    results["openwith_registered"] = (
        reg_value(r"Software\Classes\.mp4\OpenWithProgids", "BabarifyFrame.Media") is not None
    )
    results["default_app_unchanged"] = reg_value(r"Software\Classes\.mp4", "") == mp4_before
    results["install_size_mb"] = round(sum(p.stat().st_size for p in target.rglob("*") if p.is_file()) / 1e6)

    # 2. Clean-environment playback; user data is created in the clean profile.
    results["run_old"] = run_app(app, env, MEDIA)
    settings = profile / "APPDATA" / "Babarify" / "Frame" / "settings.json"
    marker = profile / "APPDATA" / "Babarify" / "Frame" / "release-check-marker.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("user data", encoding="utf-8")

    # 4. Upgrade, then roll back to the older version.
    results["upgrade"] = install(new_setup, target, work / "install-new.log")
    app = app_of(new_setup, target)
    results["installed_version_new"] = file_version(app)
    results["run_new"] = run_app(app, env, MEDIA)
    results["data_kept_after_upgrade"] = marker.is_file() and settings.is_file()
    if real_data is not None:
        after = library_facts(data)
        results["real_data_after_upgrade"] = after
        before = results["real_data_before"]
        assert isinstance(before, dict)
        # The check itself plays one file, so history may grow by that one entry.
        results["real_data_counts_kept"] = all(
            after.get(k) == v or (k == "history" and isinstance(v, int) and after.get(k) in (v, v + 1))
            for k, v in before.items()
            if k != "schema"
        )
        results["copy_before_migration"] = sorted(p.name for p in data.glob("library.before-*"))
        settings_after = json.loads(settings.read_text(encoding="utf-8"))
        results["settings_changed_by_upgrade"] = sorted(
            k for k in settings_before if k in settings_after and settings_after[k] != settings_before[k]
        )
        results["settings_lost_by_upgrade"] = sorted(k for k in settings_before if k not in settings_after)
    library_after_upgrade = digest(data / "library.db")
    results["rollback"] = install(old_setup, target, work / "install-rollback.log")
    app = app_of(old_setup, target)
    results["installed_version_after_rollback"] = file_version(app)
    results["run_rollback"] = run_app(app, env, MEDIA)
    results["data_kept_after_rollback"] = marker.is_file() and settings.is_file()
    # An older version never changes a newer library (it starts with an empty one in memory and says why).
    results["library_untouched_by_rollback"] = digest(data / "library.db") == library_after_upgrade

    # 5. Silent uninstall: program and registry entries gone, user data kept.
    uninstaller = next(target.glob("unins*.exe"))
    results["uninstall"] = subprocess.run(
        [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES"], timeout=600
    ).returncode
    time.sleep(3)  # the uninstaller finishes from a temporary copy
    results["program_removed"] = not app.exists() and not (target / "_internal").exists()
    results["uninstall_entry_removed"] = reg_value(UNINSTALL_KEY, "DisplayName") is None
    results["openwith_removed"] = (
        reg_value(r"Software\Classes\.mp4\OpenWithProgids", "BabarifyFrame.Media") is None
    )
    results["default_app_still_unchanged"] = reg_value(r"Software\Classes\.mp4", "") == mp4_before
    results["user_data_kept_on_silent_uninstall"] = marker.is_file()
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
