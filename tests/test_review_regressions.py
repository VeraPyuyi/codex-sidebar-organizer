"""Review regressions using offline helpers and synthetic snapshots only."""
import copy
import unittest

from test_sidebar_plan import planner as p, fixture, simulate, cloud_fixture


def recorded_operations(plan, after):
    """Synthetic native write log, separate from the snapshot placement model."""
    creates = [
        {'operationId': t['operationId'], 'state': 'confirmed',
         'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])}
        for t in plan['targets'] if t['state'] == 'create'
    ]
    moves = [{'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves']]
    return creates + moves


class ReviewRegressionTests(unittest.TestCase):
    def test_unjournaled_placement_never_confirms_or_undoes(self):
        before = fixture()
        plan = p.safe_plan(before)
        after = simulate(before, plan)
        creates = [r for r in recorded_operations(plan, after) if 'sectionId' in r]
        receipt = p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': creates})
        self.assertEqual(receipt['status'], 'unverified')
        self.assertEqual(receipt['confirmedMoves'], [])
        self.assertEqual(receipt['coverage']['proven'], [])
        self.assertEqual(receipt['retryable'], [])
        self.assertEqual(p.undo_plan(before, after, plan, receipt, can_move_back=True)['moves'], [])
        move_ids = {m['operationId'] for m in plan['moves']}
        self.assertTrue(all(r['state'] == 'unknown' for r in receipt['operations'] if r['operationId'] in move_ids))

    def test_reused_destinations_without_journal_never_confirm_or_undo(self):
        before = fixture()
        before['sidebar']['sections'].extend(
            {'sectionId': f'existing-{i}', 'name': name, 'itemKeys': []}
            for i, name in enumerate(p.LABELS['zh'][:4]))
        plan = p.safe_plan(before)
        after = simulate(before, plan)
        receipt = p.reconcile_receipt(before, after, plan)
        self.assertEqual(receipt['status'], 'unverified')
        self.assertEqual(receipt['confirmedMoves'], [])
        self.assertEqual(p.undo_plan(before, after, plan, receipt, can_move_back=True)['moves'], [])

    def test_pending_move_at_origin_is_not_retryable(self):
        before = fixture()
        plan = p.safe_plan(before)
        after = simulate(before, plan)
        move = plan['moves'][0]
        for section in after['sidebar']['sections']:
            section['itemKeys'] = [k for k in section['itemKeys'] if k != move['key']]
        next(s for s in after['sidebar']['sections'] if s['sectionId'] == move['fromSection'])['itemKeys'].append(move['key'])
        operations = recorded_operations(plan, after)
        next(r for r in operations if r['operationId'] == move['operationId'])['state'] = 'pending'
        receipt = p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': operations})
        self.assertNotIn(move['operationId'], receipt['retryable'])
        self.assertEqual(next(r['state'] for r in receipt['operations'] if r['operationId'] == move['operationId']), 'unknown')
        self.assertEqual(len(receipt['confirmedMoves']), 4)
        # A fresh destination read can resolve an attempted pending write.
        final = p.reconcile_receipt(before, simulate(before, plan), plan, {'schemaVersion': 2, 'operations': operations})
        self.assertEqual(final['status'], 'confirmed')

    def test_undo_requires_available_host_and_source(self):
        before = fixture()
        plan = p.safe_plan(before)
        after = simulate(before, plan)
        receipt = p.reconcile_receipt(before, after, plan, {
            'schemaVersion': 2, 'operations': recorded_operations(plan, after)})
        self.assertEqual(len(p.undo_plan(before, after, plan, receipt, True)['moves']), 5)
        for field, values, expected in [
            ('unavailableHosts', ['local'], {'chatgpt:project:p-cloud', 'chatgpt:conversation:t-cloud'}),
            ('unavailableHosts', [{'renamedHost': 'local'}], {'chatgpt:project:p-cloud', 'chatgpt:conversation:t-cloud'}),
            ('unavailableSources', ['chatgpt'], {'codex:project:p-local', 'codex:thread:local:t-new', 'codex:thread:local:t-old'}),
            ('unavailableSources', [{'renamedSource': 'codex'}], set()),
        ]:
            with self.subTest(field=field, values=values):
                current = copy.deepcopy(after)
                current['sidebar'][field] = values
                undo = p.undo_plan(before, current, plan, receipt, True)
                self.assertEqual({m['key'] for m in undo['moves']}, expected)
                self.assertTrue(all(r['reason'] == 'fresh_identity_unavailable' for r in undo['skipped']))

    def test_undo_unresolved_alias_blocks_reverse_placements(self):
        before = fixture()
        plan = p.safe_plan(before)
        after = simulate(before, plan)
        receipt = p.reconcile_receipt(before, after, plan, {
            'schemaVersion': 2, 'operations': recorded_operations(plan, after)})
        after['sidebar']['sections'][1]['itemKeys'].append('codex:thread:local:client-new-thread:unresolved')
        undo = p.undo_plan(before, after, plan, receipt, True)
        self.assertEqual(undo['moves'], [])
        self.assertTrue(all(r['reason'] == 'fresh_identity_unavailable' for r in undo['skipped']))

    def test_undo_native_durable_key_requires_fresh_cloud_evidence(self):
        raw, reads = cloud_fixture()
        raw['sidebar']['sections'][3]['itemKeys'][0] = 'codex:thread:durable:durable-demo'
        before = p.capture_cloud(raw, reads)
        plan = p.safe_plan(before)
        after = p.capture_cloud(simulate(raw, plan), reads)
        receipt = p.reconcile_receipt(before, after, plan, {
            'schemaVersion': 2, 'operations': recorded_operations(plan, after)})
        self.assertEqual(len(receipt['confirmedMoves']), 6)
        self.assertEqual(len(p.undo_plan(before, after, plan, receipt, True)['moves']), 6)
        after.pop('cloudEvidence')
        undo = p.undo_plan(before, after, plan, receipt, True)
        self.assertNotIn('durable-demo', [m.get('threadId') for m in undo['moves']])
        self.assertIn({'key': 'codex:thread:durable:durable-demo', 'reason': 'fresh_identity_unavailable'}, undo['skipped'])
        # Fresh evidence bound to the current inventory restores eligibility.
        self.assertEqual(len(p.undo_plan(before, p.capture_cloud(after, reads), plan, receipt, True)['moves']), 6)

    def test_v4_excluded_placements_are_still_protected(self):
        for scope in [
            {'excludeIds': ['t-new']},
            {'excludeIds': ['codex:thread:local:t-new']},
            {'sources': ['chatgpt']},
            {'hosts': []},
        ]:
            with self.subTest(scope=scope):
                before = fixture()
                plan = p.safe_plan(before, config={'version': 1, **scope})
                self.assertNotIn('t-new', [m.get('threadId') for m in plan['moves']])
                after = simulate(before, plan)
                journal = {'schemaVersion': 2, 'operations': recorded_operations(plan, after)}
                self.assertEqual(p.reconcile_receipt(before, after, plan, journal)['status'], 'confirmed')
                key = 'codex:thread:local:t-new'
                after['sidebar']['sections'][3]['itemKeys'].remove(key)
                after['sidebar']['sections'][1]['itemKeys'].append(key)
                receipt = p.reconcile_receipt(before, after, plan, journal)
                self.assertEqual(receipt['status'], 'unverified')
                self.assertIn('unplanned_placement_change:' + key, receipt['errors'])
                self.assertEqual(receipt['confirmedMoves'], [])
                self.assertEqual(receipt['coverage']['proven'], [])

    def test_unknown_requested_empty_group_prevents_overall_confirmation(self):
        before = fixture()
        plan = p.safe_plan(before, config={'version': 1, 'createEmptyGroups': True})
        after = simulate(before, plan)
        journal = {'schemaVersion': 2, 'operations': recorded_operations(plan, after)}
        self.assertEqual(p.reconcile_receipt(before, after, plan, journal)['status'], 'confirmed')
        empty = next(t for t in plan['targets'] if t['category'] == 'unconfirmed')
        after['sidebar']['sections'] = [s for s in after['sidebar']['sections'] if s['name'] != empty['name']]
        for state in ('unknown', 'pending', None):
            with self.subTest(state=state):
                attempted = copy.deepcopy(journal)
                entry = next(r for r in attempted['operations'] if r['operationId'] == empty['operationId'])
                if state is None:
                    attempted['operations'].remove(entry)
                else:
                    entry['state'] = state
                    entry.pop('sectionId')
                receipt = p.reconcile_receipt(before, after, plan, attempted)
                self.assertEqual(receipt['status'], 'unverified')
                self.assertEqual(len(receipt['confirmedMoves']), 5)
                self.assertTrue(any(r['operationId'] == empty['operationId'] for r in receipt['coverage']['unverified']))
                if state is not None:
                    self.assertNotIn(empty['operationId'], receipt['retryable'])

    def assert_budget_unverified(self, receipt, reason):
        self.assertEqual(receipt['status'], 'unverified')
        self.assertFalse(receipt['budget']['sufficient'])
        self.assertEqual(receipt['budget'].get('reason'), reason)
        self.assertIn(reason, receipt['unverified'])
        self.assertEqual(receipt['confirmedMoves'], [])
        self.assertEqual(receipt['coverage']['proven'], [])
        self.assertEqual(receipt['retryable'], [])
        self.assertFalse(any(r['state'] == 'confirmed' for r in receipt['operations']))
        self.assertEqual(len(receipt['coverage']['unverified']), 9)

    def test_finite_budget_requires_actual_calls_before_proving_moves(self):
        before = fixture()
        plan = p.safe_plan(before, budget=100)
        after = simulate(before, plan)
        journal = {'schemaVersion': 2, 'operations': recorded_operations(plan, after)}
        receipt = p.reconcile_receipt(before, after, plan, journal)
        self.assert_budget_unverified(receipt, 'actual_tool_calls_unknown')
        self.assertEqual(p.undo_plan(before, after, plan, receipt, True)['moves'], [])
        journal['actualToolCalls'] = 100
        measured = p.reconcile_receipt(before, after, plan, journal)
        self.assertEqual(measured['status'], 'confirmed')
        self.assertTrue(measured['budget']['sufficient'])
        self.assertEqual(len(measured['coverage']['proven']), 5)

    def test_actual_budget_overrun_never_reports_sufficient_or_proven(self):
        before = fixture()
        plan = p.safe_plan(before, budget=100)
        after = simulate(before, plan)
        journal = {'schemaVersion': 2, 'operations': recorded_operations(plan, after), 'actualToolCalls': 101}
        receipt = p.reconcile_receipt(before, after, plan, journal)
        self.assert_budget_unverified(receipt, 'actual_tool_calls_exceed_budget')
        self.assertEqual(p.undo_plan(before, after, plan, receipt, True)['moves'], [])

    def test_insufficient_estimate_never_reports_proven(self):
        before = fixture()
        plan = p.safe_plan(before, budget=1)
        after = simulate(before, plan)
        journal = {'schemaVersion': 2, 'operations': recorded_operations(plan, after), 'actualToolCalls': 1}
        receipt = p.reconcile_receipt(before, after, plan, journal)
        self.assert_budget_unverified(receipt, 'estimated_tool_calls_exceed_budget')

    def test_doctor_rejects_missing_or_renamed_host_route(self):
        before = fixture()
        before['capabilities'] = {
            'adapter': 'native-v1',
            'defaultSectionIds': ['threads', 'chats', 'projects', 'orbit', 'agents'],
            'tools': {
                'list_threads': ['limit'], 'list_projects': [],
                'create_sidebar_section': ['name'],
                'move_project_to_sidebar_section': ['projectId', 'sectionId'],
                'move_thread_to_sidebar_section': ['threadId', 'source', 'hostId', 'sectionId'],
            },
        }
        before['projects']['projects'][0].update(projectKind='remote', hostId='machine-a')
        before['sidebar']['threads'][0]['hostId'] = 'machine-a'
        before['sidebar']['sections'][3]['itemKeys'][0] = 'codex:thread:machine-a:t-new'
        self.assertEqual(p.diagnose(before)['status'], 'ready')
        self.assertTrue(any(m.get('hostId') == 'machine-a' for m in p.safe_plan(before)['moves']))
        for replacement in (None, 'renamedHostId'):
            with self.subTest(replacement=replacement):
                changed = copy.deepcopy(before)
                fields = changed['capabilities']['tools']['move_thread_to_sidebar_section']
                fields.remove('hostId')
                if replacement:
                    fields.append(replacement)
                doctor = p.diagnose(changed)
                self.assertEqual(doctor['status'], 'degraded')
                self.assertFalse(doctor['canPlanMoves'])
                self.assertIn('tool_schema_mismatch:move_thread_to_sidebar_section', doctor['reasons'])
                self.assertEqual(p.safe_plan(changed)['moves'], [])


if __name__ == '__main__':
    unittest.main()
