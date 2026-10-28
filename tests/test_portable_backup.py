"""Backups restore both account data and files, and fail closed on corrupt archives."""
import importlib.util
from pathlib import Path
import sys
import pytest


@pytest.fixture
def backup_tool(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('portable_backup',Path(__file__).resolve().parents[1]/'scripts/portable-backup.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    roots={name:tmp_path/name for name in module.ROOTS}
    for path in roots.values():path.mkdir()
    (roots['credentials']/'compose.env').write_text('AI07_DB_PASSWORD=source-db\nAI07_LS_TOKEN=original-token\nAI07_WEB_PORT=3000\n')
    (roots['artifacts']/'sample.txt').write_text('original sample')
    monkeypatch.setattr(module,'ROOTS',roots);monkeypatch.setattr(module,'DEST',tmp_path/'backups')
    monkeypatch.setenv('AI07_DATABASE_URL','postgresql+psycopg://ai07:target-db@platform-db/ai07')
    calls=[]
    def database(command,*args):
        calls.append(command)
        if command=='pg_dump':Path(args[-1]).write_bytes(b'test database accounts')
        else:assert Path(args[-1]).read_bytes()==b'test database accounts'
    monkeypatch.setattr(module,'database',database)
    return module,roots,calls


def run(module,monkeypatch,action):
    monkeypatch.setattr(sys,'argv',['portable-backup.py',action,'--name','roundtrip.tar']);module.main()


def test_restore_preserves_target_connection_and_source_files(backup_tool,monkeypatch):
    module,roots,calls=backup_tool
    run(module,monkeypatch,'backup')
    (roots['artifacts']/'sample.txt').write_text('changed')
    (roots['artifacts']/'extra.txt').write_text('remove on explicit restore')
    (roots['credentials']/'compose.env').write_text('AI07_DB_PASSWORD=target-db\nAI07_WEB_PORT=13000\n')
    run(module,monkeypatch,'restore')
    assert (roots['artifacts']/'sample.txt').read_text()=='original sample'
    assert not (roots['artifacts']/'extra.txt').exists()
    settings=(roots['credentials']/'compose.env').read_text()
    assert 'AI07_DB_PASSWORD=target-db' in settings and 'AI07_WEB_PORT=13000' in settings
    assert 'AI07_LS_TOKEN=original-token' in settings
    assert calls==['pg_dump','pg_restore']


def test_corrupt_archive_does_not_change_database_or_files(backup_tool,monkeypatch):
    module,roots,calls=backup_tool
    run(module,monkeypatch,'backup')
    with (module.DEST/'roundtrip.tar').open('ab') as stream:stream.write(b'corrupt')
    with pytest.raises(ValueError,match='checksum'):run(module,monkeypatch,'restore')
    assert calls==['pg_dump']
    assert (roots['artifacts']/'sample.txt').read_text()=='original sample'
