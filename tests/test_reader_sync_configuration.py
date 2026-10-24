"""Configuration safety: preserve credentials and unrelated server settings."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

spec = importlib.util.spec_from_file_location('reader_sync_configuration',
    Path(__file__).resolve().parents[1] / 'deploy/aliyun/configure-reader-sync.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)
TOKEN = 'synthetic_token_for_configuration_test_0123456789'


@pytest.mark.parametrize('present', ['reader', 'shuran', 'both'])
def test_existing_credentials_reused(present):
    reader = {'SHURAN_CLIENT_ID': 'shuran-hk', 'SHURAN_CLIENT_SECRET': TOKEN} if present != 'shuran' else {}
    shuran = {'READER_CLIENT_ID': 'shuran-hk', 'READER_CLIENT_SECRET': TOKEN} if present != 'reader' else {}
    assert config.credentials(reader, shuran) == ('shuran-hk', TOKEN)


def test_missing_credentials_generated_and_conflicts_rejected():
    first, second = config.credentials({}, {}), config.credentials({}, {})
    assert first[0] == second[0] == 'shuran-hk'
    assert len(first[1]) >= 32 and first[1] != second[1]
    with pytest.raises(ValueError) as error:
        config.credentials({'SHURAN_CLIENT_ID': 'old', 'SHURAN_CLIENT_SECRET': TOKEN},
                           {'READER_CLIENT_ID': 'new', 'READER_CLIENT_SECRET': TOKEN + '_different'})
    assert TOKEN not in str(error.value)


@pytest.mark.parametrize('values', [
    {'READER_CLIENT_ID': 'partial'},
    {'READER_CLIENT_SECRET': TOKEN},
    {'READER_CLIENT_ID': 'valid', 'READER_CLIENT_SECRET': 'short'},
    {'READER_CLIENT_ID': 'bad\nclient', 'READER_CLIENT_SECRET': TOKEN},
])
def test_partial_or_unsafe_credentials_not_replaced(values):
    with pytest.raises(ValueError):
        config.credentials({}, values)


def test_only_selected_environment_keys_change(tmp_path):
    original = '# private config\nDATABASE_URL=postgresql://kept\nSECRET_KEY="keep$exact"\nSHURAN_INSTANCE_LABEL=书然\nREADER_CLIENT_ID=old\nexport READER_CLIENT_ID=duplicate\n'
    result = config.env_text(original, {'READER_CLIENT_ID': 'shuran-hk', 'READER_CLIENT_SECRET': TOKEN})
    assert '# private config\nDATABASE_URL=postgresql://kept\nSECRET_KEY="keep$exact"\nSHURAN_INSTANCE_LABEL=书然\n' in result
    assert result.count('READER_CLIENT_ID=') == 1
    path = tmp_path / '.env'
    path.write_text(result, encoding='utf-8')
    assert dotenv_values(path, interpolate=False)['READER_CLIENT_SECRET'] == TOKEN


def prepare(monkeypatch, tmp_path):
    shuran, reader = tmp_path / 'shuran.env', tmp_path / 'reader.env'
    shuran.write_text('SECRET_KEY=keep-existing-stable-key\nPOSTGRES_PASSWORD=keep-password\n', encoding='utf-8')
    reader.write_text('DATABASE_URL=keep-reader-database\n', encoding='utf-8')
    monkeypatch.setattr(config, 'SHURAN_ENV', shuran)
    monkeypatch.setattr(config, 'READER_ENV', reader)
    monkeypatch.setattr(config, 'BACKUP_ROOT', tmp_path / 'backups')
    monkeypatch.setattr(config.os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setitem(sys.modules, 'pwd', SimpleNamespace(getpwnam=lambda _: SimpleNamespace(pw_uid=0, pw_gid=0)))
    return shuran, reader


def test_failed_preflight_makes_no_changes(monkeypatch, tmp_path):
    shuran, reader = prepare(monkeypatch, tmp_path)
    original = (shuran.read_bytes(), reader.read_bytes())
    def failed(*args, **kwargs):
        raise RuntimeError('preflight failed')
    monkeypatch.setattr(config, 'run', failed)
    with pytest.raises(RuntimeError, match='preflight failed'):
        config.main()
    assert (shuran.read_bytes(), reader.read_bytes()) == original
    assert not config.BACKUP_ROOT.exists()


def test_second_file_failure_restores_both_configs(monkeypatch, tmp_path):
    shuran, reader = prepare(monkeypatch, tmp_path)
    original = (shuran.read_bytes(), reader.read_bytes())
    calls = []
    monkeypatch.setattr(config, 'run', lambda command, *args, **kwargs: calls.append(command))
    writes = []
    def write(path, text, uid, gid):
        writes.append(path)
        if len(writes) == 2:
            raise OSError('simulated disk error')
        path.write_text(text, encoding='utf-8')
    monkeypatch.setattr(config, 'write_private', write)
    with pytest.raises(RuntimeError, match='已恢复原文件'):
        config.main()
    assert (shuran.read_bytes(), reader.read_bytes()) == original
    assert not any('restart' in call or '--force-recreate' in call for call in calls)
    backup = next(config.BACKUP_ROOT.iterdir())
    assert (backup / 'shuran.env').read_bytes() == original[0]
    assert (backup / 'reader.env').read_bytes() == original[1]
