"""Independent synthetic regression fixtures for SB-01 through SB-07."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_sidebar_plan import planner as p, fixture, simulate, ROOT, SCRIPT


class SafeProtocolTests(unittest.TestCase):
    def test_doctor_unknown_adapter_and_schema(self):
        self.assertTrue(hasattr(p, 'diagnose'), 'missing doctor')
        for change, reason in [('adapter', 'unknown_adapter'), ('fields', 'schema_mismatch'), ('defaults', 'unknown_default_sections')]:
            s = fixture()
            s['capabilities'] = {'adapter': 'native-v1', 'tools': {}, 'defaultSectionIds': sorted(p.DEFAULTS)}
            if change == 'adapter': s['capabilities']['adapter'] = 'future'
            if change == 'fields': s['sidebar']['groups'] = s['sidebar'].pop('sections')
            if change == 'defaults': s['capabilities']['defaultSectionIds'].append('future-default')
            d = p.diagnose(s)
            self.assertIn(reason, d['reasons'])
            self.assertFalse(d['canPlanMoves'])
            self.assertEqual(p.safe_plan(s)['moves'], [])
        self.assertEqual(p.diagnose(fixture())['clientVersion'], 'unknown')
        self.assertIn('legacy_snapshot', p.diagnose(fixture())['reasons'])

    def test_missing_and_renamed_tools_fail_closed(self):
        self.assertTrue(hasattr(p, 'diagnose'), 'missing doctor')
        s = fixture()
        s['capabilities'] = {'adapter': 'native-v1', 'tools': {}, 'defaultSectionIds': sorted(p.DEFAULTS)}
        self.assertFalse(p.diagnose(s)['canPlanMoves'])
        s['capabilities']['tools'] = {'move_thread_to_sidebar_section': ['renamedId', 'sectionId']}
        self.assertIn('tool_schema_mismatch:move_thread_to_sidebar_section', p.diagnose(s)['reasons'])

    def test_protocol_determinism_and_empty_groups(self):
        self.assertTrue(hasattr(p, 'safe_plan'), 'missing v4 planner')
        s = fixture(); plan = p.safe_plan(s)
        self.assertEqual(plan, p.safe_plan(s))
        self.assertEqual(plan['schemaVersion'], 4)
        self.assertTrue(plan['ruleVersion']); self.assertTrue(plan['capabilityVersion'])
        self.assertEqual(len({m['operationId'] for m in plan['moves']}), 5)
        self.assertTrue(all('category' in m and 'expectedTargetId' in m and m['fromSection'] for m in plan['moves']))
        self.assertEqual(len(plan['targets']), 4)
        s['projects']['projects'] = []; s['sidebar']['threads'] = []; s['sidebar']['pinnedThreads'] = []
        for section in s['sidebar']['sections']: section['itemKeys'] = []
        self.assertEqual(p.safe_plan(s)['targets'], [])
        self.assertEqual(p.safe_plan(s)['moves'], [])

    def test_mapping_language_rename_delete_and_ambiguity(self):
        self.assertTrue(hasattr(p, 'safe_plan'), 'missing mappings')
        s = fixture(); s['sidebar']['sections'].append({'sectionId': 'known', 'name': 'Renamed', 'itemKeys': []})
        mapping = {'local.chats': 'known'}
        for language in ['zh', 'en']:
            plan = p.safe_plan(s, language, mapping=mapping)
            self.assertEqual(next(m for m in plan['moves'] if m.get('threadId') == 't-new')['expectedTargetId'], 'known')
        s['sidebar']['sections'].pop()
        plan = p.safe_plan(s, mapping=mapping)
        self.assertNotIn('t-new', [m.get('threadId') for m in plan['moves']])
        self.assertIn('mapped_section_missing', [x['reason'] for x in plan['skipped']])
        for n in range(2): s['sidebar']['sections'].append({'sectionId': f'dup-{n}', 'name': '本机 · 聊天', 'itemKeys': []})
        self.assertTrue(any(t['state'] == 'ambiguous' for t in p.safe_plan(s)['targets']))

    def test_receipts_unknown_create_readback_and_wrong_id(self):
        self.assertTrue(hasattr(p, 'reconcile_receipt'), 'missing receipt protocol')
        before = fixture(); plan = p.safe_plan(before)
        pending = p.reconcile_receipt(before, before, plan)
        self.assertTrue(all(r['state'] == 'pending' for r in pending['operations']))
        target = plan['targets'][0]
        journal = {'schemaVersion': 1, 'operations': [{'operationId': target['operationId'], 'state': 'unknown'}]}
        result = p.reconcile_receipt(before, before, plan, journal)
        self.assertNotIn(target['operationId'], result['retryable'])
        after = simulate(before, plan)
        result = p.reconcile_receipt(before, after, plan, journal)
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(result['confirmedMoves'], [])
        creates = []
        for t in plan['targets']:
            sid = next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])
            creates.append({'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': sid})
        creates.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        journal = {'schemaVersion': 2, 'operations': creates, 'actualToolCalls': 12}
        result = p.reconcile_receipt(before, after, plan, journal)
        self.assertEqual(len(result['confirmedMoves']), 5)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(result['budget']['actualToolCalls'], 12)
        journal['operations'][0]['sectionId'] = 'wrong'
        self.assertLess(len(p.reconcile_receipt(before, after, plan, journal)['confirmedMoves']), 5)
        changed = copy.deepcopy(plan); changed['moves'].pop()
        with self.assertRaises(ValueError): p.reconcile_receipt(before, after, changed)

    def test_conflicts_and_idempotent_undo(self):
        self.assertTrue(hasattr(p, 'undo_plan'), 'missing undo')
        before = fixture(); plan = p.safe_plan(before); after = simulate(before, plan)
        ops = [{'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])} for t in plan['targets']]
        ops.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        journal = {'schemaVersion': 2, 'operations': ops}
        receipt = p.reconcile_receipt(before, after, plan, journal)
        undo = p.undo_plan(before, after, plan, receipt, can_move_back=True)
        self.assertEqual(len(undo['moves']), 5)
        self.assertEqual(p.undo_plan(before, before, plan, receipt, can_move_back=True)['moves'], [])
        self.assertEqual(p.undo_plan(before, after, plan, receipt)['status'], 'unsupported')
        after['sidebar']['pinnedThreads'].append(copy.deepcopy(after['sidebar']['threads'][0]))
        self.assertEqual(len(p.undo_plan(before, after, plan, receipt, can_move_back=True)['moves']), 4)
        current = copy.deepcopy(before)
        key = plan['moves'][0]['key']
        for s in current['sidebar']['sections']: s['itemKeys'] = [k for k in s['itemKeys'] if k != key]
        current['sidebar']['sections'][1]['itemKeys'].append(key)
        conflict = p.reconcile_receipt(before, current, plan)
        self.assertIn('user_moved', [r.get('reason') for r in conflict['operations']])

    def test_budget_and_coverage_20_50(self):
        self.assertTrue(hasattr(p, 'safe_plan'), 'missing budget')
        for n in (20, 50):
            s = fixture(); s['sidebar']['threads'] = [{'id': f'cloud-{i}', 'kind': 'codex', 'hostId': 'durable'} for i in range(n)]
            s['sidebar']['sections'][3]['itemKeys'] = [f'codex:thread:durable:cloud-{i}' for i in range(n)]
            plan = p.safe_plan(s, budget=1)
            self.assertEqual(plan['budget']['cloudVerificationCalls'], n * 2)
            self.assertFalse(plan['budget']['sufficient'])
            self.assertFalse(plan['coverage']['complete'])
            self.assertIn('unverified', plan['coverage'])
            self.assertEqual(p.reconcile_receipt(s, s, plan)['status'], 'unverified')

    def test_config_validation_scope_labels_sort_and_protection(self):
        self.assertTrue(hasattr(p, 'safe_plan'), 'missing config')
        for config in [{'version': 2}, {'version': 1, 'disablePins': True}, {'version': 1, 'sort': 'random'}, {'version': 1, 'createEmptyGroups': 'yes'}, {'version': 1, 'labels': {'unknown': 'x'}}]:
            with self.subTest(config=config), self.assertRaises(ValueError): p.safe_plan(fixture(), config=config)
        config = {'version': 1, 'sources': ['codex'], 'hosts': ['local'], 'excludeIds': ['t-new'], 'labels': {'local.chats': 'Custom'}, 'sort': 'manual', 'createEmptyGroups': False}
        plan = p.safe_plan(fixture(), config=config)
        self.assertEqual([m.get('threadId') for m in plan['moves'] if m['entity'] == 'chat'], ['t-old'])
        self.assertEqual(next(m['targetName'] for m in plan['moves'] if m.get('threadId') == 't-old'), 'Custom')
        self.assertEqual(plan['sortingPreview'], {'before': 'manual', 'after': 'manual', 'requiresApproval': False})
        self.assertEqual({x['reason'] for x in plan['protected']}, {'pinned', 'project_member', 'already_filed'})

    def test_partial_interruption_unknown_move_and_target_disappearance(self):
        before = fixture(); plan = p.safe_plan(before); after = simulate(before, plan)
        ops = [{'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])} for t in plan['targets']]
        ops.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        move = plan['moves'][0]; key = move['key']
        for section in after['sidebar']['sections']: section['itemKeys'] = [k for k in section['itemKeys'] if k != key]
        next(s for s in after['sidebar']['sections'] if s['sectionId'] == move['fromSection'])['itemKeys'].append(key)
        next(r for r in ops if r['operationId'] == move['operationId'])['state'] = 'unknown'
        result = p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': ops})
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(len(result['confirmedMoves']), 4)
        self.assertNotIn(move['operationId'], result['retryable'])
        # A new read proving the move completes the same interrupted plan.
        final = simulate(before, plan)
        self.assertEqual(p.reconcile_receipt(before, final, plan, {'schemaVersion': 2, 'operations': ops})['status'], 'confirmed')
        mapped = p.safe_plan(before, mapping={'local.chats': 'manual'})
        gone = copy.deepcopy(before)
        gone['sidebar']['sections'] = [s for s in gone['sidebar']['sections'] if s['sectionId'] != 'manual']
        self.assertIn('target_disappeared', [r['reason'] for r in p.reconcile_receipt(before, gone, mapped)['operations']])

    def test_undo_rejects_changed_host_and_cloud_evidence(self):
        before = fixture(); plan = p.safe_plan(before); after = simulate(before, plan)
        ops = [{'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])} for t in plan['targets']]
        ops.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        receipt = p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': ops})
        # Capability disappearance must stop every reverse action.
        after['capabilities'] = {'adapter': 'future', 'tools': {}, 'defaultSectionIds': []}
        self.assertEqual(p.undo_plan(before, after, plan, receipt, can_move_back=True)['moves'], [])

    def test_invalid_capabilities_and_unknown_journal_fail_closed(self):
        for caps in [[], {'adapter': 'native-v1', 'tools': None, 'defaultSectionIds': None}]:
            s = fixture(); s['capabilities'] = caps
            self.assertFalse(p.diagnose(s)['canPlanMoves'])
        before = fixture(); plan = p.safe_plan(before)
        with self.assertRaises(ValueError):
            p.reconcile_receipt(before, before, plan, {'schemaVersion': 2, 'operations': [{'operationId': 'foreign', 'state': 'confirmed'}]})

    def test_configured_sort_and_labels_can_confirm(self):
        before = fixture(); plan = p.safe_plan(before, config={'version': 1, 'sort': 'manual', 'labels': {'local.chats': 'Custom'}})
        after = simulate(before, plan)
        after['sidebar']['sidebarPreferences']['sorting']['chats'] = 'manual'
        ops = [{'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])} for t in plan['targets']]
        ops.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        self.assertEqual(p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': ops})['status'], 'confirmed')
        after['sidebar']['sidebarPreferences']['sorting']['chats'] = 'updated_at'
        self.assertEqual(p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': ops})['status'], 'unverified')

    def test_actual_budget_exhaustion_and_undo_fresh_cloud_identity(self):
        before = fixture(); plan = p.safe_plan(before, budget=100); after = simulate(before, plan)
        ops = [{'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])} for t in plan['targets']]
        ops.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        result = p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': ops, 'actualToolCalls': 101})
        self.assertEqual(result['status'], 'unverified')
        from test_sidebar_plan import cloud_fixture
        raw, reads = cloud_fixture(); before = p.capture_cloud(raw, reads); plan = p.safe_plan(before)
        after = p.capture_cloud(simulate(raw, plan), reads)
        ops = [{'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])} for t in plan['targets']]
        ops.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        receipt = p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': ops})
        self.assertEqual(len(receipt['confirmedMoves']), 6)
        after.pop('cloudEvidence')
        undo = p.undo_plan(before, after, plan, receipt, can_move_back=True)
        self.assertNotIn('durable-demo', [m.get('threadId') for m in undo['moves']])

    def test_new_records_and_aliases_keep_overall_receipt_unverified(self):
        before = fixture(); plan = p.safe_plan(before); after = simulate(before, plan)
        ops = [{'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])} for t in plan['targets']]
        ops.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        after['sidebar']['threads'].append({'id': 'new-concurrent', 'kind': 'chatgpt'})
        after['sidebar']['sections'][4]['itemKeys'].append('chatgpt:conversation:new-concurrent')
        receipt = p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': ops})
        self.assertEqual(receipt['status'], 'unverified')
        self.assertEqual(len(receipt['confirmedMoves']), 5)
        self.assertTrue(any('new_record_outside_plan' in reason for reason in receipt['unverified']))

    def test_safe_cli_roundtrip_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'in.json', Path(tmp)/'out.json'
            source.write_text(json.dumps(fixture()), encoding='utf-8')
            cmd = [sys.executable, str(SCRIPT), 'safe-plan', '--input', str(source), '--output', str(out)]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(json.loads(out.read_text(encoding='utf-8'))['schemaVersion'], 4)
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 1)
            plan = p.safe_plan(fixture()); after = simulate(fixture(), plan)
            plan_path, after_path, journal_path = Path(tmp)/'plan.json', Path(tmp)/'after.json', Path(tmp)/'journal.json'
            plan_path.write_text(json.dumps(plan), encoding='utf-8'); after_path.write_text(json.dumps(after), encoding='utf-8')
            ops = [{'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])} for t in plan['targets']]
            ops.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
            journal_path.write_text(json.dumps({'schemaVersion': 2, 'operations': ops}), encoding='utf-8')
            receipt_cmd = [sys.executable, str(SCRIPT), 'receipt', '--before', str(source), '--after', str(after_path), '--plan', str(plan_path), '--journal', str(journal_path), '--output', str(Path(tmp)/'receipt.json')]
            self.assertEqual(subprocess.run(receipt_cmd, capture_output=True).returncode, 0)

if __name__ == '__main__': unittest.main()
