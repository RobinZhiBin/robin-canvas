"""Bounded local evidence utilities. No project imports, network or shell execution."""
from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

VERSION = 1
MAX_BYTES = 2 * 1024 * 1024
EXTENSIONS = {'.py', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.html', '.css',
              '.scss', '.json', '.toml', '.yaml', '.yml', '.ini', '.conf', '.sql',
              '.sh', '.go', '.java', '.cs', '.rs', '.rb', '.php', '.vue', '.svelte', '.md', '.txt'}
NAMES = {'Dockerfile', 'Makefile', 'Procfile', 'CMakeLists.txt'}
SKIP_DIRS = {'.git', '.hg', '.svn', '.venv', 'venv', 'node_modules', '__pycache__',
             '.next', 'dist', 'build', 'coverage', 'output', 'artifacts', '.cache',
             '.idea', '.vscode', '.pytest_cache', '.playwright-cli'}
PRIVATE = re.compile(r'(^\.env($|\.)|(^|[._-])(credentials?|secrets?|passwords?|accounts)([._-]|$)|^id_(rsa|ed25519))', re.I)
SECRET_KEY = re.compile(r'''(?ix)["']?\b(?:[a-z0-9]+[_-])*(?:password|passwd|api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|private[_-]?key|secret|token|authorization)\b["']?\s*[:=]\s*''')
SECRET_PATTERN = re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)|(?i:Bearer\s+[A-Za-z0-9._~+/-]{10,})|[a-z]+://[^\s/:]+:[^\s/@]+@')
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:/@-]*$')


class AuditError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def contained(root, relative):
    """Reject traversal and *every* symlink component, including links inside root."""
    if not isinstance(relative, str) or '\\' in relative or '\x00' in relative:
        raise AuditError('Invalid relative evidence path')
    bits = PurePosixPath(relative)
    if bits.is_absolute() or not bits.parts or any(x in {'.', '..'} for x in relative.split('/')):
        raise AuditError('Evidence path must stay inside repository')
    root = Path(root).resolve()
    candidate = root
    for bit in bits.parts:
        candidate /= bit
        if candidate.is_symlink():
            raise AuditError('Symlink evidence is not allowed')
    if not candidate.resolve().is_relative_to(root):
        raise AuditError('Evidence path escapes repository')
    return candidate


def read_source(root, relative, limit=MAX_BYTES):
    path = contained(root, relative)
    if not path.is_file() or path.stat().st_size > limit:
        raise AuditError('Missing or oversized evidence file: ' + relative)
    raw = path.read_bytes()
    if len(raw) > limit or b'\x00' in raw:
        raise AuditError('Binary or oversized evidence file: ' + relative)
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise AuditError('Non UTF-8 evidence file: ' + relative) from exc
    return raw, text


def git(root, *args, stdin=None):
    try:
        p = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
                            '-C', str(root), *args], input=stdin, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=20, check=False)
        return p.stdout if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def discover(root, excludes=(), max_bytes=MAX_BYTES):
    root = Path(root).resolve()
    if not root.is_dir():
        raise AuditError('Repository directory does not exist')
    candidates, excluded = [], []
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            reason = ('symlink' if path.is_symlink() else 'generated/private directory'
                      if name in SKIP_DIRS or PRIVATE.search(name) else 'scope exclusion'
                      if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel + '/', g) for g in excludes) else '')
            if reason:
                dirs.remove(name)
                excluded.append({'path': rel, 'reason': reason, 'directory': True})
        for name in sorted(files):
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            reason = ('symlink' if path.is_symlink() else 'private filename' if PRIVATE.search(name)
                      else 'scope exclusion' if any(fnmatch.fnmatch(rel, g) for g in excludes)
                      else 'unsupported extension' if path.suffix.lower() not in EXTENSIONS and name not in NAMES
                      else 'oversized file' if path.stat().st_size > max_bytes else '')
            if reason:
                excluded.append({'path': rel, 'reason': reason})
            else:
                candidates.append(rel)
    ignored = git(root, 'check-ignore', '-z', '--stdin', stdin=('\0'.join(candidates) + '\0').encode()) if candidates else None
    # check-ignore returns 1 for no matches; git() treats that as no exclusions.
    ignored = set(ignored.decode().strip('\0').split('\0')) if ignored else set()
    included = []
    for relative in sorted(candidates):
        if relative in ignored:
            excluded.append({'path': relative, 'reason': 'gitignored'})
            continue
        try:
            raw, text = read_source(root, relative, max_bytes)
        except AuditError:
            excluded.append({'path': relative, 'reason': 'nontext/unreadable'})
            continue
        included.append({'path': relative, 'sha256': digest(raw), 'bytes': len(raw), 'lines': len(text.splitlines())})
    return included, sorted(excluded, key=lambda x: x['path'])


def snapshot(root, excludes=(), max_bytes=MAX_BYTES):
    root = Path(root).resolve()
    files, excluded = discover(root, excludes, max_bytes)
    head = git(root, 'rev-parse', 'HEAD')
    status = git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
    tracked = git(root, 'ls-files', '-z')
    known = set(tracked.decode().strip('\0').split('\0')) if tracked else set()
    for row in files:
        row['tracked'] = row['path'] in known
    return {'schema_version': VERSION, 'snapshot_id': digest(files), 'created_at': now(),
            'project': root.name, 'git': {'head': head.decode().strip() if head else None,
            'dirty': bool(status) if status is not None else None},
            'scope': {'excludes': list(excludes), 'max_bytes': max_bytes,
                      'policy': 'utf8-source-config-docs-v1; untracked included; ignored/private/symlink/generated excluded'},
            'files': files, 'excluded': excluded,
            'limitations': ['快照只覆盖已列文件；排除项不算已审查。', '不执行项目模块，也不验证现场部署。']}


def drift(root, baseline):
    if baseline.get('schema_version') != VERSION:
        raise AuditError('Unsupported snapshot version')
    if baseline.get('snapshot_id') != digest(baseline['files']):
        raise AuditError('Snapshot metadata digest mismatch')
    old = {r['path']: r for r in baseline['files']}
    fresh = snapshot(root, baseline['scope']['excludes'], baseline['scope']['max_bytes'])
    new = {r['path']: r for r in fresh['files']}
    changed = sorted(p for p in old.keys() & new.keys() if old[p] != new[p])
    added, removed = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    return {'baseline_id': baseline['snapshot_id'], 'current_id': fresh['snapshot_id'],
            'checked_at': now(), 'changed': changed, 'added': added, 'removed': removed,
            'stale': bool(changed or added or removed), 'current_git': fresh['git']}


def redact(text):
    """Conservative line-preserving scrub; not a claim of exhaustive secret detection."""
    lines = text.splitlines()
    hidden = set()
    pem = False
    for i, line in enumerate(lines):
        if re.search(r'-----BEGIN .*PRIVATE KEY-----', line):
            pem = True
        if pem:
            hidden.add(i)
            if re.search(r'-----END .*PRIVATE KEY-----', line):
                pem = False
        if SECRET_PATTERN.search(line):
            hidden.add(i)
        match = SECRET_KEY.search(line)
        if match:
            tail = line[match.end():].strip()
            # Variable references contain no literal value. Quoted values and structured
            # blocks are withheld; multiline/structured cases withhold the whole file.
            if tail.startswith(('"""', "'''", '|', '>', '[', '{', '(', '`', '\\')) or tail.endswith('\\') or not tail:
                hidden.update(range(len(lines)))
            else:
                hidden.add(i)
    return '\n'.join('[REDACTED: source line withheld]' if i in hidden else line for i, line in enumerate(lines)), len(hidden)


def scrub(value):
    if isinstance(value, str):
        return redact(value)[0]
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: '[REDACTED: sensitive field]' if SECRET_KEY.search(str(k) + ': ') else scrub(v)
                for k, v in value.items()}
    return value


def index_sources(root, snap):
    """Python AST + explicitly limited JS/TS lexical indexes, no imports of target."""
    modules, edges, routes = [], [], []
    known = {r['path'][:-3].replace('/', '.').removesuffix('.__init__'): r['path']
             for r in snap['files'] if r['path'].endswith('.py')}
    def ref(path, line, end=None, symbol=None):
        return {k: v for k, v in {'path': path, 'line': line, 'end': end or line, 'symbol': symbol}.items() if v is not None}
    for row in snap['files']:
        path = row['path']
        raw, text = read_source(root, path, snap['scope']['max_bytes'])
        if digest(raw) != row['sha256']:
            raise AuditError('Source changed during index: ' + path)
        category = ('test' if 'test' in Path(path).parts or 'tests' in Path(path).parts or Path(path).name.startswith('test_')
                    else 'frontend' if Path(path).suffix in {'.html', '.css', '.scss'}
                    else 'documentation' if Path(path).suffix == '.md'
                    else 'deployment' if Path(path).suffix in {'.yaml', '.yml', '.toml', '.conf'} or Path(path).name == 'Dockerfile'
                    else 'application')
        item = {**row, 'id': path, 'category': category, 'doc': '', 'symbols': [], 'imports': [],
                'refs': [ref(path, 1 if row['lines'] else 0)], 'analysis_status': 'indexed_only'}
        modules.append(item)
        if path.endswith('.py'):
            try:
                tree = ast.parse(text)
            except SyntaxError:
                item['index_limit'] = 'Python syntax unsupported; manual evidence required'
                continue
            item['symbol_index_kind'] = 'python-ast'
            item['doc'] = (ast.get_docstring(tree) or '').split('\n')[0]
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            def scope(node):
                names = []
                node = parents.get(node)
                while node:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        names.append(node.name)
                    node = parents.get(node)
                return '.'.join(reversed(names))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name = '.'.join(filter(None, [scope(node), node.name]))
                    calls = [{'text': ast.unparse(c.func), 'refs': [ref(path, c.lineno, c.end_lineno, name)]}
                             for c in ast.walk(node) if isinstance(c, ast.Call) and scope(c) == name]
                    item['symbols'].append({'id': path + '::' + name, 'name': name,
                        'kind': 'class' if isinstance(node, ast.ClassDef) else 'function',
                        'line': node.lineno, 'end': node.end_lineno, 'calls': calls,
                        'doc': (ast.get_docstring(node) or '').split('\n')[0],
                        'refs': [ref(path, node.lineno, min(node.lineno + 7, node.end_lineno), name)]})
                    for d in getattr(node, 'decorator_list', []):
                        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in {'get', 'post', 'put', 'delete', 'patch', 'route'} and d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str):
                            routes.append({'method': d.func.attr, 'url': d.args[0].value, 'symbol': name,
                                           'status': 'syntactic_route_candidate', 'refs': [ref(path, d.lineno, node.lineno)]})
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        names = [v.name for v in node.names]
                    else:
                        package = path.split('/')[:-1]
                        base = '.'.join(package[:len(package) - node.level + 1] + ([node.module] if node.module else [])) if node.level else node.module or ''
                        names = [base] + [base + '.' + v.name for v in node.names]
                    targets = sorted({known[x] for x in names if x in known})
                    r = ref(path, node.lineno, node.end_lineno)
                    statement = ast.get_source_segment(text, node)
                    item['imports'].append({'statement': statement, 'targets': targets, 'refs': [r]})
                    for target in targets:
                        edges.append({'id': 'import-' + digest([path, node.lineno, target])[:14],
                            'from': path, 'to': target, 'kind': 'import', 'label': '静态导入',
                            'detail': '源码中的导入表达式；不证明一次真实调用。', 'refs': [r]})
        elif Path(path).suffix in {'.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.html', '.vue', '.svelte'}:
            item['symbol_index_kind'] = 'lexical-js-ts'
            item['index_limit'] = '词法候选，非完整 AST；箭头函数、类方法及动态目标需审查'
            for match in re.finditer(r'\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(', text):
                line = text[:match.start()].count('\n') + 1
                item['symbols'].append({'id': path + '::' + match[1] + '@' + str(line), 'name': match[1],
                    'kind': 'lexical function candidate', 'line': line, 'end': min(line + 7, row['lines']),
                    'doc': '', 'calls': [], 'refs': [ref(path, line, min(line + 7, row['lines']))]})
    return scrub({'modules': modules, 'edges': edges, 'routes': routes,
                  'limitations': ['Python AST 是静态语法证据，不解析完整动态分派。',
                  'JS/TS 只提供词法候选，不声称完整函数、路由或调用图。',
                  '文件进入目录表示已索引，不表示职责和风险已审查。']})


def walk_refs(value):
    if isinstance(value, dict):
        if 'path' in value and 'line' in value:
            yield value
        for child in value.values():
            yield from walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_refs(child)


def validate_model(model, snap, root):
    if not isinstance(model, dict):
        return ['Model must be an object']
    errors = []
    files = {r['path']: r for r in snap['files']}
    if model.get('schema_version') != VERSION:
        errors.append('model.schema_version must be 1')
    if model.get('snapshot_id') != snap['snapshot_id']:
        errors.append('model.snapshot_id does not match snapshot')
    for field in ['title', 'summary']:
        if not isinstance(model.get(field), str) or not model[field].strip():
            errors.append('Missing model.' + field)
    review = model.get('review', {})
    if not isinstance(review, dict):
        return ['review must be an object']
    for group in ['views', 'findings', 'questions', 'reviewed_modules', 'limitations']:
        if not isinstance(model.get(group, []), list):
            errors.append(group + ' must be an array')
    if errors:
        return errors
    if review.get('status') not in {'draft', 'reviewed'}:
        errors.append('review.status must be draft or reviewed')
    if review.get('status') == 'reviewed' and (not review.get('reviewer') or review.get('snapshot_id') != snap['snapshot_id']):
        errors.append('Reviewed model needs reviewer and current snapshot_id; declaration is not proof')
    seen_views = set()
    for view in model.get('views', []):
        if not isinstance(view, dict) or not isinstance(view.get('nodes'), list) or not isinstance(view.get('edges'), list):
            errors.append('Each view needs nodes and edges arrays')
            continue
        if not view.get('title') or not view['nodes']:
            errors.append('View needs title and at least one node')
        if not all(isinstance(x, dict) for x in view['nodes'] + view['edges']):
            errors.append('Nodes and edges must be objects')
            continue
        vid = view.get('id', '')
        if not ID.fullmatch(vid) or vid in seen_views:
            errors.append('Invalid/duplicate view id')
        seen_views.add(vid)
        nodes = [n.get('id', '') for n in view.get('nodes', [])]
        if len(nodes) != len(set(nodes)):
            errors.append('Duplicate node ids in ' + vid)
        seen_edges = set()
        for obj in view.get('nodes', []) + view.get('edges', []):
            oid = obj.get('id', '')
            if not ID.fullmatch(oid):
                errors.append('Invalid node/edge id in ' + vid)
            status = obj.get('status')
            if not isinstance(obj.get('refs', []), list):
                errors.append('refs must be an array: ' + oid)
            if status not in {'confirmed', 'unknown', 'conflict'}:
                errors.append('Explicit status required: ' + oid)
            if status == 'confirmed' and (not obj.get('refs') or not obj.get('evidence_note')):
                errors.append('Confirmed claim needs refs and evidence_note: ' + oid)
            if status != 'confirmed' and not obj.get('uncertainty'):
                errors.append('Unknown/conflict needs uncertainty: ' + oid)
            if obj.get('module') and obj['module'] not in files:
                errors.append('Module outside snapshot: ' + oid)
        for edge in view.get('edges', []):
            if edge.get('id') in seen_edges:
                errors.append('Duplicate edge id in ' + vid)
            seen_edges.add(edge.get('id'))
            if edge.get('from') not in nodes or edge.get('to') not in nodes:
                errors.append('Dangling edge in ' + vid)
            if edge.get('relation') not in {'direct', 'aggregate', 'static'}:
                errors.append('Edge relation must be direct/aggregate/static')
            if edge.get('relation') == 'aggregate' and (not edge.get('via') or len(edge.get('refs', [])) < 2):
                errors.append('Aggregate edge requires via and intermediate refs')
    if not seen_views:
        errors.append('At least one scoped business view is required')
    for group, fields in [('findings', ['id', 'title', 'fact', 'impact', 'recommendation', 'severity', 'refs']),
                          ('questions', ['id', 'question', 'why', 'owner'])]:
        seen = set()
        for row in model.get(group, []):
            if not isinstance(row, dict):
                errors.append(group + ' entries must be objects')
                continue
            if any(not row.get(f) for f in fields):
                errors.append('Incomplete ' + group + ' entry')
            if row.get('id') in seen:
                errors.append('Duplicate ' + group + ' id')
            seen.add(row.get('id'))
            if not isinstance(row.get('id'), str) or not ID.fullmatch(row['id']):
                errors.append('Invalid ' + group + ' id')
            if group == 'findings' and row.get('severity') not in {'P0', 'P1', 'P2', 'P3'}:
                errors.append('Invalid severity')
            if group == 'questions' and row.get('owner') not in {'technical', 'business'}:
                errors.append('Question owner must be technical/business')
    for r in walk_refs(model):
        try:
            path = r['path']
            contained(root, path)
            row = files[path]
            line, end = r['line'], r.get('end', r['line'])
            if not isinstance(line, int) or not isinstance(end, int) or not 1 <= line <= end <= row['lines']:
                raise AuditError('Invalid reference lines')
            if r.get('type', 'code') not in {'code', 'config', 'document', 'runtime'}:
                raise AuditError('Invalid evidence type')
            if r.get('type') == 'runtime':
                stamp = r.get('observed_at')
                if not isinstance(stamp, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', stamp):
                    raise AuditError('Runtime evidence needs timezone-aware ISO observed_at')
                observed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                if observed.utcoffset() is None:
                    raise AuditError('Runtime evidence needs a timezone')
        except (KeyError, TypeError, ValueError):
            errors.append('Invalid or out-of-scope reference')
    for path in model.get('reviewed_modules', []):
        if path not in files:
            errors.append('Reviewed module is outside snapshot')
    return errors


def evidence_snippets(root, snap, refs):
    """Only referenced lines; unrelated full source is never put in the artifact."""
    files = {r['path']: r for r in snap['files']}
    ranges = {}
    for r in refs:
        path = r['path']
        if path not in files:
            continue
        total = files[path]['lines']
        start = max(1, r['line'] - 2)
        # Full function requests remain bounded and visibly show omitted sections.
        end = min(total, max(r['line'] + 6, min(r.get('end', r['line']), r['line'] + 79)))
        ranges.setdefault(path, set()).update(range(start, end + 1))
    sources, masked = {}, 0
    for path, numbers in ranges.items():
        raw, text = read_source(root, path, snap['scope']['max_bytes'])
        if digest(raw) != files[path]['sha256']:
            raise AuditError('Source changed while collecting snippets')
        safe, n = redact(text)
        masked += n
        lines = safe.splitlines()
        sources[path] = {'lines': len(lines), 'sha256': files[path]['sha256'],
                         'snippets': {str(i): lines[i - 1] for i in sorted(numbers)},
                         'redacted_lines': n, 'mode': 'referenced-snippets'}
    return sources, masked
