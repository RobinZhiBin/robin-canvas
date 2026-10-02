"""Run the skill's generic browser probe using installed Playwright CLI."""
import argparse
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = Path.home() / '.codex/skills/playwright/scripts/playwright_cli.sh'


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def run(artifact_dir, evidence_dir):
    artifact_dir = Path(artifact_dir).resolve()
    evidence_dir = Path(evidence_dir).resolve(); evidence_dir.mkdir(parents=True, exist_ok=True)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(artifact_dir)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    session = 'arch-' + uuid.uuid4().hex[:10]
    def cli(*args):
        p = subprocess.run([str(CLI), '--session=' + session, *args], cwd=evidence_dir,
                           env={**os.environ, 'npm_config_offline': 'true'}, capture_output=True, text=True, timeout=90)
        if p.returncode or '### Error' in p.stdout:
            (evidence_dir / 'browser-error.txt').write_text(p.stdout + p.stderr)
            raise RuntimeError('Browser operation failed; see browser-error.txt')
        result = re.search(r'### Result\s*\n(.*?)(?=\n### |\Z)', p.stdout, re.S)
        return json.loads(result[1]) if result else None
    try:
        with tempfile.TemporaryDirectory(prefix='architecture-browser-') as temp:
            executable = os.environ.get('BROWSER_EXECUTABLE', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
            config = {'browser': {'browserName': 'chromium', 'launchOptions': {'headless': True, 'executablePath': executable}, 'contextOptions': {'viewport': {'width': 1680, 'height': 1050}}}}
            path = Path(temp) / 'config.json'; path.write_text(json.dumps(config))
            cli('open', f'http://127.0.0.1:{server.server_port}/architecture-canvas.html', '--config=' + str(path))
            result = cli('run-code', '--filename=' + str(ROOT / 'skills/architecture-audit-canvas/scripts/browser_smoke.js'))
            import hashlib
            result['canvas_sha256'] = hashlib.sha256((artifact_dir / 'architecture-canvas.html').read_bytes()).hexdigest()
            (evidence_dir / 'browser-validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({'checks': len(result['checks']), 'all_passed': all(result['checks'].values()), 'errors': result['errors']}, ensure_ascii=False))
            return result
    finally:
        try:
            cli('close')
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifacts', type=Path)
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    if not shutil.which('npx') or not CLI.exists():
        parser.error('Installed npx and Playwright CLI wrapper required; no automatic installation')
    run(args.artifacts, args.evidence)
