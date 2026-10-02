#!/usr/bin/env python3
"""Read-only snapshot comparison; exit 2 means source evidence is stale."""
import argparse
import json
from pathlib import Path
from audit_core import AuditError, drift, dump_json, load_json, walk_refs


def check(root, baseline, model=None):
    result = drift(root, baseline)
    touched = set(result['changed'] + result['removed'])
    impacted = []
    if model:
        for view in model.get('views', []):
            for row in view.get('nodes', []) + view.get('edges', []):
                if any(r['path'] in touched for r in walk_refs(row)):
                    impacted.append(view['id'] + ':' + row['id'])
        for row in model.get('findings', []) + model.get('questions', []):
            if any(r['path'] in touched for r in walk_refs(row)):
                impacted.append(row['id'])
    result['impacted_claims'] = impacted
    result['note'] = '新增文件也需审查；未列入受影响集合不等于结论仍正确。离线HTML本身不会监控磁盘。'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--snapshot', required=True, type=Path)
    p.add_argument('--model', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    try:
        result = check(a.repo, load_json(a.snapshot), load_json(a.model) if a.model else None)
        if a.out:
            dump_json(a.out, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (AuditError, OSError, ValueError) as exc:
        p.exit(1, str(exc) + '\n')
    p.exit(2 if result['stale'] else 0)


if __name__ == '__main__':
    main()
