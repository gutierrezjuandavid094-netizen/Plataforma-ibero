# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "Main.py")], pathex=[str(root)], binaries=[],
    datas=[(str(root / "src" / "assets"), "src/assets")],
    hiddenimports=["keyring.backends.SecretService"], hookspath=[],
    runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name="CampusFlow",
    debug=False, bootloader_ignore_signals=False, strip=False,
    upx=True, console=False, icon=str(root / "src" / "assets" / "campus-flow.ico"),
)
