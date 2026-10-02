"""Behavioral invariants of evidence production; never runs a target module."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT / 'skills/architecture-audit-canvas/scripts'
sys.path.insert(0, str(SCRIPTS))
from audit_core import AuditError, contained, drift, evidence_snippets, index_sources, redact, snapshot, validate_model
from build_canvas import build
from validate_artifacts import validate


def model_for(snap):
    return {'schema_version': 1, 'snapshot_id': snap['snapshot_id'], 'title': '合成受理链',
        'summary': '仅审查隔离夹具，未运行被审项目。', 'review': {'status': 'draft'},
        'reviewed_modules': ['server.py', 'storage.py'], 'limitations': ['未核验现场'],
        'views': [{'id': 'intake', 'title': '接收与保存', 'summary': '输入校验后同步调用内存保存。',
            'nodes': [{'id': 'api', 'label': '接收入口', 'kind': 'api', 'module': 'server.py',
                'status': 'confirmed', 'detail': '校验 reference 后调用 save。', 'evidence_note': '函数中有条件校验和 return save(body)。',
                'refs': [{'path': 'server.py', 'line': 5, 'end': 8}]},
                {'id': 'store', 'label': '进程内记录', 'kind': 'store', 'module': 'storage.py',
                 'status': 'confirmed', 'detail': '向列表追加一份输入字典。', 'evidence_note': 'records 为模块列表，save 执行 append。',
                 'refs': [{'path': 'storage.py', 'line': 2, 'end': 7}]}],
            'edges': [{'id': 'save', 'from': 'api', 'to': 'store', 'label': '同步保存', 'kind': 'call',
                'relation': 'direct', 'status': 'confirmed', 'detail': 'receive 返回 save 结果。',
                'evidence_note': '导入绑定与实际调用共同说明目标。',
                'refs': [{'path': 'server.py', 'line': 2}, {'path': 'server.py', 'line': 8}]}]}],
        'findings': [{'id': 'F1', 'severity': 'P1', 'title': '进程退出后记录不可恢复',
            'fact': '示例只向进程内列表追加，没有持久化实现。', 'impact': '只在本夹具范围成立，未证明真实系统行为。',
            'recommendation': '若业务要求重启恢复，需持久化并验证恢复。',
            'refs': [{'path': 'storage.py', 'line': 2, 'end': 7}]}],
        'questions': [{'id': 'Q1', 'question': '是否需要跨重启保留？', 'why': '决定存储契约。',
            'owner': 'business', 'refs': [{'path': 'storage.py', 'line': 2}]}]}


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='architecture-test-')
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.base / 'repo'; self.repo.mkdir()
        for p in (PROJECT / 'tests/fixtures/python_intake').iterdir():
            (self.repo / p.name).write_bytes(p.read_bytes())
        self.snap = snapshot(self.repo)
        self.model = model_for(self.snap)

    def tearDown(self):
        self.tmp.cleanup()

    def test_untracked_and_yml_are_included_gitignored_excluded(self):
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / '.gitignore').write_text('ignored.py\n')
        (self.repo / 'ignored.py').write_text('x=1\n')
        s = snapshot(self.repo)
        paths = {r['path'] for r in s['files']}
        self.assertTrue({'server.py', 'deploy.yml'} <= paths)
        self.assertNotIn('ignored.py', paths)
        self.assertFalse(next(r for r in s['files'] if r['path'] == 'server.py')['tracked'])

    def test_new_modified_removed_files_invalidate_without_commit(self):
        (self.repo / 'server.py').write_text('new=1\n')
        (self.repo / 'new.ts').write_text('export const n=1;\n')
        (self.repo / 'storage.py').unlink()
        r = drift(self.repo, self.snap)
        self.assertEqual(r['changed'], ['server.py'])
        self.assertEqual(r['added'], ['new.ts'])
        self.assertEqual(r['removed'], ['storage.py'])

    def test_symlinks_and_private_data_excluded(self):
        outside = self.base / 'outside.py'; outside.write_text('private_data=1\n')
        (self.repo / 'alias.py').symlink_to(outside)
        (self.repo / '.env').write_text('SYNTHETIC_ONLY=not-a-real-secret\n')
        (self.repo / 'accounts.json').write_text('{}')
        s = snapshot(self.repo)
        self.assertTrue({'alias.py', '.env', 'accounts.json'} <= {r['path'] for r in s['excluded']})
        for path in ['../outside.py', str(outside), 'alias.py', 'x/../../outside.py']:
            with self.assertRaises(AuditError): contained(self.repo, path)

    def test_never_imports_project_code(self):
        marker = self.base / 'must-not-exist'
        (self.repo / 'unsafe.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
        index_sources(self.repo, snapshot(self.repo))
        self.assertFalse(marker.exists())

    def test_python_calls_and_ts_limit_are_honest(self):
        idx = index_sources(self.repo, self.snap)
        self.assertTrue(any(e['to'] == 'storage.py' for e in idx['edges']))
        ts = PROJECT / 'tests/fixtures/typescript_jobs'
        result = index_sources(ts, snapshot(ts))
        queue = next(m for m in result['modules'] if m['path'] == 'queue.ts')
        self.assertIn('非完整 AST', queue['index_limit'])
        self.assertEqual([s['name'] for s in queue['symbols']], ['take'])

    def test_confirmed_without_evidence_and_dangling_edges_fail(self):
        model = copy.deepcopy(self.model)
        model['views'][0]['nodes'][0]['refs'] = []
        model['views'][0]['edges'][0]['to'] = 'missing'
        self.assertGreaterEqual(len(validate_model(model, self.snap, self.repo)), 2)

    def test_unknown_requires_explicit_reason(self):
        model = copy.deepcopy(self.model)
        node = model['views'][0]['nodes'][0]
        node.update(status='unknown', refs=[])
        self.assertTrue(validate_model(model, self.snap, self.repo))
        node['uncertainty'] = '缺少运行证据'
        self.assertEqual(validate_model(model, self.snap, self.repo), [])

    def test_aggregate_needs_intermediate_evidence(self):
        model = copy.deepcopy(self.model)
        edge = model['views'][0]['edges'][0]
        edge.update(relation='aggregate')
        self.assertTrue(validate_model(model, self.snap, self.repo))
        edge['via'] = ['server.receive', 'storage.save']
        self.assertEqual(validate_model(model, self.snap, self.repo), [])

    def test_out_of_bounds_and_out_of_scope_refs_rejected(self):
        for ref in [{'path': 'server.py', 'line': 999}, {'path': '../outside.py', 'line': 1}]:
            model = copy.deepcopy(self.model); model['views'][0]['nodes'][0]['refs'] = [ref]
            self.assertTrue(validate_model(model, self.snap, self.repo))

    def test_multiline_private_key_and_config_literal_scrub(self):
        source = 'x=1\npassword: "SYNTHETIC-PASSWORD"\n-----BEGIN PRIVATE KEY-----\nSYNTHETIC-BLOCK\n-----END PRIVATE KEY-----\ny=2'
        safe, n = redact(source)
        self.assertEqual(len(safe.splitlines()), len(source.splitlines()))
        self.assertNotIn('SYNTHETIC-', safe)
        self.assertEqual(n, 4)
        safe, _ = redact('api_key: |\n  SYNTHETIC-MULTILINE\nnext: value')
        self.assertNotIn('SYNTHETIC-', safe)

    def test_yaml_unquoted_and_prefixed_names_scrub(self):
        text = 'api_key: SYNTHETIC-PLAIN\nDEFAULT_API_KEY = "SYNTHETIC-PREFIX"\napiKey: "SYNTHETIC-CAMEL"'
        safe, _ = redact(text)
        self.assertNotIn('SYNTHETIC-', safe)

    def test_only_referenced_snippets_and_line_numbers(self):
        (self.repo / 'long.py').write_text('\n'.join('row_' + str(i) + '=0' for i in range(1, 301)))
        s = snapshot(self.repo)
        result, _ = evidence_snippets(self.repo, s, [{'path': 'long.py', 'line': 100, 'end': 300}])
        self.assertIn('100', result['long.py']['snippets'])
        self.assertNotIn('300', result['long.py']['snippets'])
        self.assertNotIn('1', result['long.py']['snippets'])

    def test_build_offline_payload_and_hash_verification(self):
        self.model['summary'] = '</script><script>window.SYNTHETIC_ATTACK=1</script>'
        out = self.base / 'delivery'
        manifest = build(self.repo, self.snap, self.model, out)
        self.assertFalse(manifest['browser_verified'])
        self.assertTrue(validate(self.repo, self.snap, self.model, out)['valid'])
        html = (out / 'architecture-canvas.html').read_text()
        self.assertNotIn('</script><script>window.SYNTHETIC_ATTACK', html)
        self.assertIn('connect-src \'none\'', html)
        self.assertEqual(json.loads((out / 'canvas-data.json').read_text())['meta']['snapshotId'], self.snap['snapshot_id'])
        (out / 'architecture-report.md').write_text('tampered')
        self.assertFalse(validate(self.repo, self.snap, self.model, out)['valid'])

    def test_stale_build_refuses_and_existing_output_preserved(self):
        out = self.base / 'delivery'
        out.mkdir(); (out / 'user.txt').write_text('keep')
        with self.assertRaises(AuditError): build(self.repo, self.snap, self.model, out)
        self.assertEqual((out / 'user.txt').read_text(), 'keep')
        (self.repo / 'server.py').write_text('changed=1')
        with self.assertRaises(AuditError): build(self.repo, self.snap, self.model, self.base / 'new')
        self.assertFalse((self.base / 'new').exists())

    def test_changed_model_cannot_validate_old_artifacts(self):
        out = self.base / 'delivery'
        build(self.repo, self.snap, self.model, out)
        changed = copy.deepcopy(self.model)
        changed['summary'] = 'A different architecture conclusion'
        edge = changed['views'][0]['edges'][0]
        edge.update(status='unknown', uncertainty='Not yet verified')
        result = validate(self.repo, self.snap, changed, out)
        self.assertFalse(result['valid'])
        self.assertTrue(any('model' in e for e in result['errors']))

    def test_unreviewed_data_is_not_embedded(self):
        (self.repo / 'data').mkdir()
        (self.repo / 'data/customers.json').write_text('{"name":"SYNTHETIC-CUSTOMER-DATA"}')
        snap = snapshot(self.repo); model = model_for(snap)
        out = self.base / 'delivery'
        build(self.repo, snap, model, out)
        data = json.loads((out / 'canvas-data.json').read_text())
        self.assertNotIn('data/customers.json', data['sources'])
        self.assertNotIn('SYNTHETIC-CUSTOMER-DATA', (out / 'architecture-canvas.html').read_text())

    def test_multiline_secret_does_not_reach_deliverable(self):
        (self.repo / 'storage.py').write_text((self.repo / 'storage.py').read_text() + '\nPASSWORD = (\n    "SYNTHETIC-PARENTHESIZED"\n)\n')
        snap = snapshot(self.repo); model = model_for(snap)
        out = self.base / 'delivery'; build(self.repo, snap, model, out)
        for filename in ['canvas-data.json', 'architecture-canvas.html']:
            text = (out / filename).read_text()
            self.assertNotIn('SYNTHETIC-PARENTHESIZED', text)
            self.assertIn('REDACTED', text)
        for text in ['PASSWORD = \\\n "SYNTHETIC-CONTINUED"', 'apiKey: `\nSYNTHETIC-TEMPLATE\n`']:
            self.assertNotIn('SYNTHETIC-', redact(text)[0])

    def test_runtime_time_is_validated_and_displayed(self):
        model = copy.deepcopy(self.model)
        ref = model['views'][0]['nodes'][0]['refs'][0]
        for invalid in ['', 'NOT-A-TIMESTAMP', '2026-10-02T12:00:00', '2026-99-02T12:00:00Z']:
            ref.update(type='runtime', observed_at=invalid)
            self.assertTrue(validate_model(model, self.snap, self.repo))
        ref['observed_at'] = '2026-10-02T12:00:00+08:00'
        self.assertEqual(validate_model(model, self.snap, self.repo), [])
        out = self.base / 'delivery'; build(self.repo, self.snap, model, out)
        self.assertIn('观察时间 2026-10-02T12:00:00+08:00', (out / 'architecture-report.md').read_text())
        html = (out / 'architecture-canvas.html').read_text()
        self.assertIn('evidenceLabel(r)', html)
        self.assertIn('r.observed_at', html)

    def test_snapshot_output_symlink_rejected(self):
        target = self.base / 'outside.json'
        link = self.base / 'snapshot.json'; link.symlink_to(target)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'collect_snapshot.py'), '--repo', str(self.repo), '--out', str(link)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())

    def test_snapshot_integrity_and_tracking_changes(self):
        altered = copy.deepcopy(self.snap); altered['files'][0]['lines'] += 1
        with self.assertRaises(AuditError): drift(self.repo, altered)
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        before = snapshot(self.repo)
        subprocess.run(['git', '-C', str(self.repo), 'add', 'server.py'], check=True)
        self.assertTrue(drift(self.repo, before)['stale'])


if __name__ == '__main__':
    unittest.main()
