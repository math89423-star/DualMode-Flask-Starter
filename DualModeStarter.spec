# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None
app_dir = os.path.join(os.getcwd(), 'app')

fsa_datas, fsa_binaries, fsa_hiddenimports = collect_all('flask_sqlalchemy')
fc_datas, fc_binaries, fc_hiddenimports = collect_all('flask_cors')

a = Analysis(
    [os.path.join(app_dir, 'main.py')],
    pathex=[app_dir],
    datas=fsa_datas + fc_datas,
    binaries=fsa_binaries + fc_binaries,
    hiddenimports=[
        'backend',
        'backend.paths',
        'backend.config',
        'backend.extensions',
        'backend.memory_backend',
        'backend.memory_queue',
        'backend.worker_engine',
        'backend.model.models',
        'backend.routes.example',
        'backend.services.example_service',
        'backend.utils.logging_config',
        'flask',
        'flask.json',
        'flask_sqlalchemy',
        'flask_cors',
        'sqlalchemy',
        'sqlalchemy.sql.default_comparator',
        'sqlalchemy.dialects.sqlite',
        'dotenv',
        'waitress',
        'sqlite3',
        'jinja2',
        'markupsafe',
        'werkzeug',
        'click',
        'itsdangerous',
        'blinker',
    ] + fsa_hiddenimports + fc_hiddenimports,
    excludes=[
        'mysql',
        'mysql.connector',
        'mysqlx',
        'redis',
        'rq',
        'gevent',
        'greenlet',
        'gunicorn',
        'tkinter',
        'unittest',
        'test',
    ],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DualModeStarter',
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='DualModeStarter',
)
