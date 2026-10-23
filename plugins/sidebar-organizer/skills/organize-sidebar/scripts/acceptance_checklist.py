#!/usr/bin/env python3
"""Canonical acceptance checklist. JSON by default; --check validates Markdown copies."""
import argparse
import json
from pathlib import Path


def item(id, scope, steps, evidence, prerequisites=None, stop=None, forbidden=None):
    return dict(id=id, scope=scope, prerequisites=prerequisites or 'Synthetic fixtures only; Python 3.10+; repository tests available.',
                steps=steps, evidence=evidence,
                stop=stop or 'Stop on any failed assertion or schema mismatch; retain the diagnostic and do not execute moves.',
                forbidden=forbidden or 'Do not access real chats, run the client, or mutate a sidebar during offline validation.')


ITEMS = [
    item('offline.doctor', 'offline_verified', 'Run CompatibilityTests and SafeProtocolTests doctor cases.', 'Known schemas accepted; unknown tools, arguments, returns and missing hostId block moves.'),
    item('offline.safe-plan', 'offline_verified', 'Run safe protocol determinism/protection/config tests on synthetic snapshots.', 'Deterministic v4 preview, stable operation IDs, pins and manual groups preserved.'),
    item('offline.receipt', 'offline_verified', 'Simulate confirmed and interrupted operations; reconcile before/after and journal.', 'Only matching IDs and fresh readback confirm moves; unknown outcomes remain unverified.'),
    item('offline.undo-plan', 'offline_verified', 'Run synthetic undo conflict, host and cloud evidence tests.', 'Only confirmed supported reverse moves appear; conflicts skipped; no section deletion.'),
    item('offline.budget', 'offline_verified', 'Run 20/50 record and actual budget exhaustion tests.', 'Budget shortfalls remain unverified; coverage never claims full history.'),
    item('offline.config', 'offline_verified', 'Run invalid version, scope, labels and sorting configuration tests.', 'Unknown fields rejected; protection remains enabled; sorting change is a preview.'),
]
for ident, steps, evidence in [
    ('group', 'Discover live schemas; doctor; approve a disposable test group; record returned sectionId and fresh list.', 'Created ID and exact membership readback plus separately recorded UI observation.'),
    ('move', 'Approve a scoped safe-plan for disposable records; journal each write; stop at first unknown result.', 'Exact thread/project, source, host and destination IDs; pins/manual groups unchanged.'),
    ('readback', 'Collect fresh before/after snapshots and journal; run receipt and acceptance-report.', 'Recomputed confirmed receipt for scoped metadata; separate UI observation required.'),
    ('undo', 'Confirm host supports original-section moves; request undo-plan; review and approve individual reversals.', 'Fresh reverse-placement readback; concurrent user edits preserved; repeat preview empty.'),
    ('upgrade', 'In an isolated test installation record version and manifest; upgrade; start fresh session; rediscover tools and rerun doctor.', 'Single installation, expected build SHA/digests, compatible schemas and repeat scoped acceptance.'),
    ('deletion-sync', 'Use only an explicitly authorized disposable record; independently observe deletion on each supported surface and refresh.', 'Independent host deletion evidence; list absence alone is insufficient; unsupported refresh remains blocked.'),
    ('ui', 'Inspect intended sidebar surface after readback; record client version, surface and visible grouping/order.', 'Direct UI observation; metadata confirmation is not UI visibility.'),
]:
    ITEMS.append(item('host.' + ident, 'host_required', steps, evidence,
                      'Separate explicit host authorization; disposable test records; current client version and schemas; private evidence directory.',
                      'Stop on missing capability, ambiguous identity, unknown write outcome, budget exhaustion or changed user placement; read back before any retry.',
                      'Never infer UI visibility or deletion from metadata; never bulk-delete, overwrite client state, bypass pins/manual groups or automatically retry unknown writes.'))


def validate(items):
    seen = set()
    required = {'id', 'scope', 'prerequisites', 'steps', 'evidence', 'stop', 'forbidden'}
    for row in items:
        if not isinstance(row, dict) or set(row) != required or any(not isinstance(row[k], str) or not row[k].strip() for k in required):
            raise ValueError('Incomplete checklist item')
        if row['id'] in seen or row['scope'] not in {'offline_verified', 'host_required'}:
            raise ValueError('Duplicate ID or invalid scope')
        seen.add(row['id'])
    if not items:
        raise ValueError('Empty checklist')


def render():
    validate(ITEMS)
    text = '# Acceptance checklist / 验收清单\n\nGenerated from `scripts/acceptance_checklist.py`; do not edit copies independently.\n\nOffline verified means synthetic regression coverage only. All host items remain unverified until separately executed with authorization. Metadata cannot prove UI visibility or deletion.\n\n'
    for row in ITEMS:
        text += '## ' + row['id'] + '\n\n'
        for key in ('scope', 'prerequisites', 'steps', 'evidence', 'stop', 'forbidden'):
            text += '- **' + key + '**: ' + row[key] + '\n'
        text += '\n'
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', nargs='+', type=Path)
    args = parser.parse_args()
    validate(ITEMS)
    if args.check:
        for path in args.check:
            if path.read_text(encoding='utf-8') != render():
                raise ValueError('Checklist drift: ' + str(path))
        print(json.dumps({'items': len(ITEMS), 'checkedDocuments': len(args.check)}))
    else:
        print(json.dumps({'schemaVersion': 1, 'items': ITEMS}, indent=2))


if __name__ == '__main__':
    main()
