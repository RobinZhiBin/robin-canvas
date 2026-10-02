#!/usr/bin/env python3
"""Validate structural evidence, drift and artifact hashes; not semantic truth."""
import argparse
import json
from pathlib import Path
from audit_core import AuditError, digest, drift, load_json, scrub, validate_model


def validate(root, snap, model, output=None):
    errors = validate_model(model, snap, root)
    changes = drift(root, snap)
    if changes['stale']:
        errors.append('Source snapshot is stale')
    if output:
        output = Path(output)
        manifest = load_json(output / 'manifest.json')
        if manifest['snapshot_id'] != snap['snapshot_id']:
            errors.append('Artifact snapshot differs')
        safe_model = scrub(model)
        model_hash = digest(safe_model)
        if manifest.get('model_sha256') != model_hash:
            errors.append('Artifact model digest differs from supplied model')
        if load_json(output / 'audit-model.json') != safe_model:
            errors.append('Delivered model differs from supplied model')
        if load_json(output / 'snapshot.json') != snap:
            errors.append('Delivered snapshot metadata differs')
        required = {'architecture-canvas.html', 'architecture-report.md', 'open-questions.md', 'canvas-data.json', 'snapshot.json', 'audit-model.json'}
        if not required <= manifest['files'].keys():
            errors.append('Manifest omits required artifacts')
        for name, expected in manifest['files'].items():
            if Path(name).name != name:
                errors.append('Invalid artifact path')
                continue
            path = output / name
            if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != expected:
                errors.append('Artifact hash mismatch: ' + name)
        data = load_json(output / 'canvas-data.json')
        if data['meta']['snapshotId'] != snap['snapshot_id']:
            errors.append('Canvas snapshot differs')
        if data['meta'].get('modelSha256') != model_hash:
            errors.append('Canvas model digest differs')
        for group in ['views', 'findings', 'questions']:
            if data.get(group, []) != safe_model.get(group, []):
                errors.append('Canvas model content differs: ' + group)
    return {'valid': not errors, 'errors': errors, 'drift': changes,
            'note': '结构校验通过不证明引用支持语义结论，也不代替秘密检查/浏览器验收。'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ['repo', 'snapshot', 'model']:
        p.add_argument('--' + flag, required=True, type=Path)
    p.add_argument('--artifacts', type=Path)
    a = p.parse_args()
    try:
        result = validate(a.repo, load_json(a.snapshot), load_json(a.model), a.artifacts)
    except (AuditError, OSError, ValueError, KeyError) as exc:
        p.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    p.exit(0 if result['valid'] else 1)


if __name__ == '__main__':
    main()
