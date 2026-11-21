# PyInstaller spec for Babarify Media Player (M10). Build with tools/build_release.py, not directly.
# One folder, Babarify Media Player\: the windowed player. (Until 0.10 a second folder held the optional
# AI worker; the feature was removed in 0.11.)
# libVLC is not collected here: build_release.py copies the curated engine to engines/vlc.
# ruff: noqa
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ICON = str(SRC / "babarify_frame" / "resources" / "icons" / "babarify-frame.ico")
VERSION_FILE = str(ROOT / "build" / "version_info.txt")
COMMON_EXCLUDES = [
    "tkinter", "unittest", "pydoc", "pytest", "mypy", "ruff", "IPython", "matplotlib",
    "PyInstaller",
    # Present in the development environment only (pip-audit and its dependencies, M11);
    # optional imports would otherwise pull them into the release.
    "certifi", "charset_normalizer", "tomli", "requests", "pip_audit",
]  # fmt: skip

app = Analysis(
    [str(ROOT / "packaging" / "entry_app.py")],
    pathex=[str(SRC)],
    datas=[(str(SRC / "babarify_frame" / "resources"), "babarify_frame/resources")],
    hiddenimports=["vlc"],  # imported lazily
    # Never needed by a local player; excluded so nothing in the environment pulls them in.
    excludes=COMMON_EXCLUDES + ["faster_whisper", "ctranslate2", "onnxruntime", "av", "numpy",
                                "huggingface_hub", "hf_xet", "httpx", "httpcore", "PIL"],  # fmt: skip
)
# Qt parts a widget-based, English-only player never loads (M10 size review).
QT_UNUSED = ("opengl32sw.dll", "qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard", "\\translations\\",
             "qpdf.dll")  # fmt: skip
app.binaries = [b for b in app.binaries if not any(u in b[0].lower() for u in QT_UNUSED)]
app.datas = [d for d in app.datas if not any(u in d[0].lower() for u in QT_UNUSED)]

app_exe = EXE(
    PYZ(app.pure),
    app.scripts,
    [],
    exclude_binaries=True,
    name="Babarify Media Player",
    icon=ICON,
    version=VERSION_FILE,
    console=False,
    upx=False,
)
COLLECT(app_exe, app.binaries, app.datas, name="Babarify Media Player", upx=False)
