"""Run first-use checks in a copied source tree with no user connection state.

This is application-state isolation, not a new Windows or macOS installation.
Live neighbour discovery is read-only. Credentials and SSH are never used.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import hashlib

WORKER = r'''
import json, subprocess
from pathlib import Path
from winmaclink import onboarding

root = Path.cwd().resolve()
assert Path(onboarding.__file__).resolve().is_relative_to(root)
p, path, errors = onboarding.find_profile()
assert p is None and path is None and not errors, 'Saved connection leaked into test'
assert not (Path.home()/'.ssh').exists(), 'Existing SSH home is visible'

commands = []
def read_only_runner(command, **kwargs):
    executable = Path(command[0]).name.lower()
    if executable not in ('arp', 'arp.exe', 'powershell.exe'):
        raise AssertionError('Unexpected command in blind discovery')
    commands.append(executable)
    return subprocess.run(command, **kwargs)

live = onboarding.discover(None, runner=read_only_runner)
assert not any(c.get('registered') or c.get('identity_verified') for c in live)

def empty_cache_runner(command, **kwargs):
    if command[0] == 'powershell.exe':
        return subprocess.CompletedProcess(command, 0, '["172.22.37.1"]', '')
    if command[0] == 'arp':
        return subprocess.CompletedProcess(command, 0, 'Interface: 172.22.37.1 --- 0xa\n', '')
    raise AssertionError('Unexpected command for empty cache')
empty = onboarding.discover(None, runner=empty_cache_runner)
assert empty == []
synthetic = onboarding.parse_neighbours('Interface: 172.22.37.1 --- 0xa\n172.22.37.2 02-11-22-33-44-55 dynamic\nInterface: 10.55.1.5 --- 0xb\n10.55.1.1 02-66-77-88-99-aa dynamic')
filtered = onboarding.direct_candidates(synthetic, ['172.22.37.1'], None)
assert len(filtered) == 1 and filtered[0]['host'] == '172.22.37.2'
assert not filtered[0]['identity_verified']

result = {
    'saved_profile_visible': False,
    'existing_ssh_home_visible': False,
    'ssh_commands_executed': 0,
    'live_wired_candidate_count': len(live),
    'live_candidates_authenticated': 0,
    'empty_neighbour_cache_candidate_count': len(empty),
    'nondefault_subnet_discovery_passed': True,
    'wifi_exclusion_passed': True,
    'user_account_auto_discovered': False,
    'automatic_first_connection_completed': False,
    'system_settings_changed': False,
    'limitations': ['Existing operating systems and physical network are retained.', 'A cached IP is a device candidate, not an authenticated Mac.', 'Empty cache cannot currently discover a fresh peer.']
}
Path('blind-report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gui', action='store_true', help='Also open isolated first-use GUI')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    # Parent audit only: these fingerprints are never sent to the blind worker.
    originals = [project/'.local'/'profile.json']
    if os.environ.get('LOCALAPPDATA'):
        originals.append(Path(os.environ['LOCALAPPDATA'])/'WinMacLink'/'connection.json')
    def snapshot():
        return [hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None for path in originals]
    before = snapshot()
    isolated = project/'.local'/'blind-first-run'/uuid.uuid4().hex[:10]
    source = isolated/'source'
    source.mkdir(parents=True)
    shutil.copytree(project/'winmaclink', source/'winmaclink', ignore=shutil.ignore_patterns('__pycache__'))
    (source/'blind_worker.py').write_text(WORKER, encoding='utf-8')
    home = isolated/'empty-user'; home.mkdir()
    local = isolated/'empty-appdata'; local.mkdir()
    env = os.environ.copy()
    env['LOCALAPPDATA'] = str(local)
    env['USERPROFILE'] = str(home)
    # This tool currently targets Windows; do not change the global user environment.
    env['PYTHONPATH'] = str(source)
    env['PYTHONIOENCODING'] = 'utf-8'
    env.pop('SSH_AUTH_SOCK', None)
    checked = subprocess.run([sys.executable, 'blind_worker.py'], cwd=source, env=env,
                             capture_output=True, text=True, encoding='utf-8', timeout=40)
    if checked.returncode:
        print(checked.stderr)
        return checked.returncode
    print(checked.stdout)
    unchanged = before == snapshot()
    if not unchanged:
        raise RuntimeError('Original connection settings changed during blind test')
    print('Original connection settings unchanged:', unchanged)
    if args.gui:
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        command = [str(pythonw if pythonw.exists() else Path(sys.executable)), '-m', 'winmaclink', 'gui']
        proc = subprocess.Popen(command, cwd=source, env=env)
        print('Isolated first-use GUI PID:', proc.pid)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
