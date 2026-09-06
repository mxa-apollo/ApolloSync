"""PyInstaller one-folder build specification for Apollo Sync."""

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH)
assets_directory = project_root / "assets"
datas = [(str(assets_directory), "assets")] if assets_directory.is_dir() else []
icon_file = project_root / "assets" / "icon.ico"

# Some embedded Python distributions do not expose Tcl/Tk to PyInstaller's
# automatic hook. Collect the standard-library GUI runtime explicitly when it
# is available so the first-run wizard works in the packaged application.
python_root = Path(sys.base_prefix)
tcl_root = python_root / "tcl"
for directory, target in ((tcl_root / "tcl8.6", "tcl/tcl8.6"), (tcl_root / "tk8.6", "tcl/tk8.6")):
    if directory.is_dir():
        datas.append((str(directory), target))
tkinter_sources = python_root / "Lib" / "tkinter"
if tkinter_sources.is_dir():
    datas.append((str(tkinter_sources), "tkinter"))
binaries = []
for dll_name in ("tcl86t.dll", "tk86t.dll", "_tkinter.pyd"):
    dll_path = python_root / "DLLs" / dll_name
    if dll_path.is_file():
        binaries.append((str(dll_path), "."))

# pystray selects its Windows backend dynamically at runtime.
hiddenimports = collect_submodules("pystray")

a = Analysis(
    [str(project_root / "run.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="ApolloSync",
    exclude_binaries=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(icon_file) if icon_file.is_file() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="ApolloSync",
)
