# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Veri dosyalarını tanımla
added_files = [
    ('etiket_baslik.png', '.'),
    ('yerli_uretim.jpg', '.'),
    ('etiketEkle.json', '.'),
    ('dogtasCom.xlsx', '.'),
    ('Other.xlsx', '.'),
]

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'pandas',
        'openpyxl',
        'aiohttp',
        'bs4',
        'reportlab',
        'qrcode',
        'numpy',
        'asyncio',
        'json',
        'datetime',
        'pathlib',
        're',
        'logging',
        'et_xmlfile',
        'reportlab.pdfbase.ttfonts',
        'reportlab.pdfgen.canvas',
        'reportlab.lib.pagesizes',
        'reportlab.lib.utils',
        'reportlab.lib.colors',
        'reportlab.platypus',
        'reportlab.lib.styles',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='EtiketProgram',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Konsol penceresi açılmasın
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
