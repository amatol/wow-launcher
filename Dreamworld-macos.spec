# Сборка нативного лаунчера для Apple Silicon; Wine добавляется после PyInstaller.
import os
import sys
root = os.path.abspath('.')
sys.path.insert(0, root)
from config import Config
a = Analysis(['main.py'], pathex=[root], binaries=[],
             datas=[('assets', 'assets')], hiddenimports=[], hookspath=[],
             runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Dreamworld',
          console=False, target_arch='arm64', codesign_identity=None)
collection = COLLECT(exe, a.binaries, a.datas, name='Dreamworld')
app = BUNDLE(collection, name='Dreamworld.app', icon='build/dreamworld.icns',
             bundle_identifier='blog.amatol.dreamworld', version=Config.LAUNCHER_VERSION,
             info_plist={'LSMinimumSystemVersion': '14.0',
                         'NSHighResolutionCapable': True})
