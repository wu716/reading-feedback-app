#!/usr/bin/env python3
"""Run with the reader virtualenv as root on the shared Hong Kong server."""
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler, build_opener

from dotenv import dotenv_values

COMPOSE_DIR = Path('/opt/shuran-app/deploy/aliyun')
SHURAN_ENV = COMPOSE_DIR / '.env'
READER_ENV = Path('/opt/learning-reader/.env')
READER_URL = 'https://43.161.238.165'
BACKUP_ROOT = Path('/opt/shuran-release-backups')


def credentials(reader, shuran):
    """Reuse a complete existing pair; never silently rotate or resolve conflicts."""
    pairs = []
    for label, values, prefix in [('知间', reader, 'SHURAN'), ('书然', shuran, 'READER')]:
        client = values.get(prefix + '_CLIENT_ID') or ''
        secret = values.get(prefix + '_CLIENT_SECRET') or ''
        if not client and not secret:
            continue
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', client) or not re.fullmatch(r'[A-Za-z0-9_+/=-]{32,256}', secret):
            raise ValueError(label + '现有凭证不完整或格式需人工核对；未改动配置，请勿把密钥贴到聊天。')
        pairs.append((client, secret))
    if len(pairs) == 2 and (not hmac.compare_digest(pairs[0][0], pairs[1][0]) or not hmac.compare_digest(pairs[0][1], pairs[1][1])):
        raise ValueError('两端已有服务凭证不一致，未改动配置；需先核对哪一组正在使用。')
    return pairs[0] if pairs else ('shuran-hk', secrets.token_urlsafe(48))


def env_text(original, changes):
    """Replace only selected keys, preserving all other configuration lines."""
    result, seen = [], set()
    for line in original.splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
        key = match[1] if match else None
        if key in changes:
            if key not in seen:
                result.append(key + "='" + changes[key] + "'")
                seen.add(key)
        else:
            result.append(line)
    result.extend(key + "='" + value + "'" for key, value in changes.items() if key not in seen)
    return '\n'.join(result) + '\n'


def write_private(path, content, uid, gid):
    fd, temporary = tempfile.mkstemp(prefix='.reader-sync-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
            os.fchmod(output.fileno(), 0o600)
            os.fchown(output.fileno(), uid, gid)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(command, label, timeout=60):
    result = subprocess.run(command, cwd=COMPOSE_DIR, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Never echo subprocess output: configuration commands may contain credentials.
        raise RuntimeError(label + '失败（输出已隐藏以保护凭证）。请提供这条状态提示，勿发送 .env 内容。')
    return result.stdout


def wait_api(url, expected):
    opener = build_opener(ProxyHandler({}))
    for _ in range(30):
        try:
            with opener.open(url, timeout=3) as response:
                value = json.load(response)
            if all(value.get(key) == item for key, item in expected.items()):
                return
        except (OSError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError('服务就绪检查超时：' + url + '；请检查服务日志，保留配置备份。')


def main():
    if not hasattr(os, 'geteuid') or os.geteuid() != 0:
        raise RuntimeError('本脚本仅供 Ubuntu 服务器使用；请先 sudo -i，再运行。')
    for path in (SHURAN_ENV, READER_ENV):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError('未找到常规配置文件：' + str(path) + '；未改动配置。')
    reader = dotenv_values(READER_ENV, interpolate=False)
    shuran = dotenv_values(SHURAN_ENV, interpolate=False)
    if shuran.get('READER_API_URL') and shuran['READER_API_URL'].rstrip('/') != READER_URL:
        raise RuntimeError('书然已指定其他知间来源地址，未自动覆盖；请先核对来源。')
    client, secret = credentials(reader, shuran)
    print('1/4 检查服务、书然稳定密钥与容器内 HTTPS 连接（不显示凭证）。', flush=True)
    run(['systemctl', 'is-active', '--quiet', 'learning-reader'], '知间服务检查')
    run(['docker', 'compose', 'exec', '-T', 'app', 'python', '-c', '''
from app.config import settings
assert not settings.is_insecure_secret, 'Existing SECRET_KEY must be secured separately'
'''], '书然现有 SECRET_KEY 检查（不能为默认值或长度不足，脚本不会自动更换它）')
    run(['docker', 'compose', 'exec', '-T', 'app', 'python', '-c', '''
import requests
r = requests.get('https://43.161.238.165/api', timeout=(5, 10), allow_redirects=False)
assert r.status_code == 200 and r.json().get('name') == 'Learning Reader'
'''], '书然容器到知间的 HTTPS 连接检查')
    BACKUP_ROOT.mkdir(mode=0o700, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='reader-sync-', dir=BACKUP_ROOT))
    originals = [(SHURAN_ENV, SHURAN_ENV.read_text(encoding='utf-8'), SHURAN_ENV.stat()),
                 (READER_ENV, READER_ENV.read_text(encoding='utf-8'), READER_ENV.stat())]
    for path, _, _ in originals:
        saved = backup / ('shuran.env' if path == SHURAN_ENV else 'reader.env')
        shutil.copyfile(path, saved)
        saved.chmod(0o600)
    import pwd
    account = pwd.getpwnam('reader')
    changes = [
        {'READER_API_URL': READER_URL, 'READER_CLIENT_ID': client, 'READER_CLIENT_SECRET': secret},
        {'SHURAN_CLIENT_ID': client, 'SHURAN_CLIENT_SECRET': secret},
    ]
    print('2/4 备份路径：' + str(backup) + '；写入一致服务凭证，保留其他配置。', flush=True)
    try:
        for (path, original, attrs), values in zip(originals, changes):
            owner = (account.pw_uid, account.pw_gid) if path == READER_ENV else (attrs.st_uid, attrs.st_gid)
            write_private(path, env_text(original, values), *owner)
    except Exception:
        for path, original, attrs in originals:
            write_private(path, original, attrs.st_uid, attrs.st_gid)
            path.chmod(stat.S_IMODE(attrs.st_mode))
        raise RuntimeError('配置写入失败，已恢复原文件；备份保留于 ' + str(backup)) from None
    print('3/4 重启知间并重新创建书然应用容器，使新环境变量生效。', flush=True)
    run(['systemctl', 'restart', 'learning-reader'], '知间重启')
    run(['docker', 'compose', 'up', '-d', '--no-deps', '--force-recreate', 'app'], '书然应用重建', timeout=120)
    wait_api('http://127.0.0.1:8010/api', {'name': 'Learning Reader'})
    wait_api('http://127.0.0.1:8000/health', {'status': 'healthy'})
    print('4/4 验证容器内配置和两端机器认证；不创建账号关联或阅读记录。', flush=True)
    run(['docker', 'compose', 'exec', '-T', 'app', 'python', '-c', '''
import os
import requests
from app.reader_client import configured
assert configured()
url = os.environ['READER_API_URL'] + '/api/integrations/shuran/v1/link-requests/00000000-0000-0000-0000-000000000000/status'
r = requests.post(url, json={'receiver_account_id':'connection-check', 'receiver_nonce':'0'*32},
    headers={'X-Shuran-Client':os.environ['READER_CLIENT_ID'],
             'Authorization':'Bearer '+os.environ['READER_CLIENT_SECRET']},
    timeout=(5, 15), allow_redirects=False)
assert r.status_code == 404 and r.json().get('detail') == 'Unknown pairing request'
'''], '联动配置与机器认证验证')
    print('联动通道已启用。回书然刷新“知间阅读联动”，生成关联码，再在两边确认账号。', flush=True)
    print('配置备份保留于 ' + str(backup) + '；业务数据库、书籍、附件和原 SECRET_KEY 均未改写。')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print('停止：' + str(exc), file=sys.stderr)
        sys.exit(1)
