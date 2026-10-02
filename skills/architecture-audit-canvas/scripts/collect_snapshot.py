#!/usr/bin/env python3
"""Capture source metadata; does not import the audited project."""
import argparse
from pathlib import Path
from audit_core import AuditError, dump_json, snapshot


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--exclude', action='append', default=[])
    p.add_argument('--max-bytes', type=int, default=2 * 1024 * 1024)
    a = p.parse_args()
    if a.out.is_symlink() or any(parent.is_symlink() for parent in a.out.parents):
        p.error('Output symlink is not allowed')
    if a.out.exists():
        p.error('Choose a new snapshot path; existing evidence is not overwritten')
    if a.max_bytes < 1:
        p.error('--max-bytes must be positive')
    excludes = list(a.exclude)
    if a.out.resolve().is_relative_to(a.repo.resolve()):
        excludes.append(a.out.resolve().relative_to(a.repo.resolve()).as_posix())
    try:
        s = snapshot(a.repo, excludes, a.max_bytes)
        dump_json(a.out, s)
    except (AuditError, OSError) as exc:
        p.exit(1, str(exc) + '\n')
    print(f"Snapshot {s['snapshot_id'][:12]}: {len(s['files'])} files; {len(s['excluded'])} exclusions")


if __name__ == '__main__':
    main()
