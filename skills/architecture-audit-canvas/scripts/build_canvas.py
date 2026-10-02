#!/usr/bin/env python3
"""Build one offline HTML and paired reports from a reviewed evidence model."""
from __future__ import annotations
import argparse
import json
import shutil
import tempfile
from pathlib import Path
from audit_core import (AuditError, digest, drift, dump_json, evidence_snippets,
                        index_sources, load_json, now, scrub, validate_model, walk_refs)

ASSET = Path(__file__).resolve().parents[1] / 'assets/canvas-template.html'


def plain(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('`', '\\`')


def refs_text(refs):
    def label(r):
        kind = r.get('type', 'code')
        observed = '；观察时间 ' + plain(r['observed_at']) if kind == 'runtime' else ''
        return f"`{plain(r['path'])}:{r['line']}` [{kind}{observed}]"
    return '; '.join(label(r) for r in refs) or '待确认：没有直接证据'


def reports(model, data):
    meta = data['meta']
    lines = ['# ' + plain(model['title']), '', plain(model['summary']), '',
        '## 证据基线', '', f"- 快照：`{meta['snapshotId']}`；采集时间：{meta['createdAt']}。",
        f"- Git HEAD：`{meta['commit'] or '非 Git / 无提交'}`；未提交修改：{meta['dirty']}。",
        f"- 已索引 {len(data['modules'])} 文件；声明已审查 {len(model.get('reviewed_modules', []))} 文件。",
        f"- 审查状态：{model['review']['status']}；该状态是审查者声明，不代替独立验证。",
        '- 运行现场：' + plain(meta['runtimeStatus']),
        '- 浏览器与秘密内容人工检查需另留验收记录；生成成功不代表这些检查通过。', '',
        '## 重点链路', '']
    for view in model['views']:
        lines += ['### ' + plain(view['title']), '', plain(view.get('summary', '')), '']
        for node in view['nodes']:
            lines += [f"- **{plain(node['label'])}** [{node['status']}]：{plain(node.get('detail', ''))}",
                      '  - 证据：' + refs_text(node.get('refs', []))]
            if node.get('uncertainty'):
                lines.append('  - 待确认：' + plain(node['uncertainty']))
        lines += ['', '关系与分支：', '']
        for edge in view['edges']:
            lines += [f"- `{edge['from']}` → `{edge['to']}`：{plain(edge['label'])} [{edge['relation']} / {edge['status']}]。{plain(edge.get('detail', ''))}",
                      '  - 证据：' + refs_text(edge.get('refs', []))]
            if edge.get('via'):
                lines.append('  - 中间路径：' + plain(' → '.join(edge['via'])))
    lines += ['', '## 风险与坏味道', '']
    for f in model.get('findings', []):
        lines += [f"### {f['id']} · {f['severity']} · {plain(f['title'])}", '',
                  '**事实：** ' + plain(f['fact']), '', '**影响与边界：** ' + plain(f['impact']), '',
                  '**建议：** ' + plain(f['recommendation']), '', '证据：' + refs_text(f['refs']), '']
    if not model.get('findings'):
        lines += ['本范围未列出已证实风险，不表示系统无风险。', '']
    lines += ['## 未覆盖与限制', ''] + ['- ' + plain(x) for x in meta['limitations']]
    q = ['# 待确认问题', '', f"对应快照：`{meta['snapshotId']}`。已确认的业务决定不重复询问。", '']
    for item in model.get('questions', []):
        q += ['## ' + item['id'] + ' · ' + plain(item['question']), '',
              '责任类型：' + plain(item['owner']), '', '影响：' + plain(item['why']), '',
              '下一步证据：' + plain(item.get('next_evidence', '由责任人补齐')), '',
              '提出依据：' + refs_text(item.get('refs', [])), '']
    if not model.get('questions'):
        q += ['本范围暂无已列问题；不代表全部外部行为已验证。']
    return '\n'.join(lines) + '\n', '\n'.join(q) + '\n'


def build(root, snap, model, destination):
    root, destination = Path(root).resolve(), Path(destination)
    if destination.exists():
        raise AuditError('Use a new output directory; existing audit is never overwritten')
    if destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
        raise AuditError('Output symlink is not allowed')
    errors = validate_model(model, snap, root)
    if errors:
        raise AuditError('\n'.join(errors))
    before = drift(root, snap)
    if before['stale']:
        raise AuditError('Snapshot stale; run check_drift.py and re-review affected evidence')
    index = index_sources(root, snap)
    safe_model = scrub(model)
    reviewed = set(model.get('reviewed_modules', []))
    snippet_refs = list(walk_refs(safe_model))
    for mod in index['modules']:
        mod['analysis_status'] = 'reviewed' if mod['path'] in reviewed else 'indexed_only'
        if mod['path'] in reviewed and Path(mod['path']).suffix in {'.py', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx'}:
            snippet_refs.extend(walk_refs(mod['symbols']))
            snippet_refs.extend(walk_refs(mod['imports']))
    sources, masked = evidence_snippets(root, snap, snippet_refs)
    runtime_refs = [r for r in walk_refs(model) if r.get('type') == 'runtime']
    metadata = {'schemaVersion': 1, 'title': safe_model['title'], 'summary': safe_model['summary'],
        'snapshotId': snap['snapshot_id'], 'modelSha256': digest(safe_model), 'createdAt': snap['created_at'], 'builtAt': now(),
        'commit': snap['git']['head'], 'dirty': snap['git']['dirty'], 'review': safe_model['review'],
        'runtimeStatus': '存在附时间的运行观察；仅证明引用中的范围' if runtime_refs else '未核验运行现场',
        'redactedLines': masked, 'coverage': {'indexed': len(index['modules']), 'reviewed': len(reviewed), 'excluded': len(snap['excluded'])},
        'limitations': index['limitations'] + safe_model.get('limitations', []) + [
            '图上追踪沿已审查关系导航，不是实时调用栈或完整动态调用图。',
            '仅内嵌有引用的脱敏片段；省略不等于源文件不存在。',
            '自动脱敏并非穷尽检查；交付前必须人工核查 HTML/JSON 的实际内容。',
            '此文件是固定快照，不会自动读取磁盘；使用 check_drift.py 检查是否过期。']}
    data = {'meta': metadata, **index, 'views': safe_model['views'], 'findings': safe_model.get('findings', []),
            'questions': safe_model.get('questions', []), 'sources': sources, 'scc': [], 'excluded': snap['excluded']}
    template = ASSET.read_text(encoding='utf-8')
    if template.count('/*__AUDIT_DATA__*/') != 1:
        raise AuditError('Invalid canvas template')
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    html = template.replace('/*__AUDIT_DATA__*/', payload)
    report, questions = reports(safe_model, data)
    # Recheck every scoped file immediately before emission; a moving checkout fails.
    if drift(root, snap)['stale']:
        raise AuditError('Source changed during build; no deliverable emitted')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.architecture-stage-', dir=destination.parent))
    try:
        (stage / 'architecture-canvas.html').write_text(html, encoding='utf-8')
        (stage / 'architecture-report.md').write_text(report, encoding='utf-8')
        (stage / 'open-questions.md').write_text(questions, encoding='utf-8')
        dump_json(stage / 'canvas-data.json', data)
        dump_json(stage / 'snapshot.json', snap)
        dump_json(stage / 'audit-model.json', safe_model)
        manifest = {'schema_version': 1, 'snapshot_id': snap['snapshot_id'], 'created_at': now(),
                    'model_sha256': digest(safe_model),
                    'review_status': model['review']['status'], 'browser_verified': False,
                    'semantic_review_is_declaration': True,
                    'files': {p.name: digest(p.read_bytes()) for p in sorted(stage.iterdir())}}
        dump_json(stage / 'manifest.json', manifest)
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ['repo', 'snapshot', 'model', 'out']:
        p.add_argument('--' + flag, required=True, type=Path)
    a = p.parse_args()
    try:
        result = build(a.repo, load_json(a.snapshot), load_json(a.model), a.out)
    except (AuditError, OSError, ValueError) as exc:
        p.exit(1, str(exc) + '\n')
    print(f"Built {len(result['files'])} files; browser and semantic acceptance are separate")


if __name__ == '__main__':
    main()
