"""PyInstaller one-folder build specification for Apollo Sync."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH)
assets_directory = project_root / "assets"
datas = [(str(assets_directory), "assets")] if assets_directory.is_dir() else []
icon_file = project_root / "assets" / "icon.ico"

# pystray selects its Windows backend dynamically at runtime.
hiddenimports = collect_submodules("pystray")

a = Analysis(
    [str(project_root / "run.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
