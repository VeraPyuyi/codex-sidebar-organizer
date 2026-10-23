"""Synthetic regressions for the three Important compatibility review findings."""
import copy
import unittest

from test_acceptance_compat import capable
from test_sidebar_plan import planner as p, simulate


class CompatibilityReviewTests(unittest.TestCase):
    def assert_degraded_plan(self, snapshot, field):
        plan = p.safe_plan(snapshot)
        self.assertEqual(plan['moves'], [])
        self.assertEqual(plan['doctor']['status'], 'degraded')
        self.assertFalse(plan['doctor']['canPlanMoves'])
        self.assertTrue(any(field in reason for reason in plan['doctor']['reasons']), plan['doctor'])
        self.assertFalse(any(t['state'] == 'create' for t in plan['targets']))

    def test_nonobject_snapshot_degrades_without_raising(self):
        for snapshot in (None, [], 'unknown', 1):
            with self.subTest(snapshot=snapshot):
                self.assert_degraded_plan(snapshot, 'schema_mismatch')

    def test_unindexed_pinned_host_cannot_bypass_protection(self):
        for replacement in ('missing', 'renamed', None, ''):
            with self.subTest(replacement=replacement):
                snapshot = capable()
                pin = copy.deepcopy(snapshot['sidebar']['threads'][0])
                if replacement in ('missing', 'renamed'):
                    host = pin.pop('hostId')
                    if replacement == 'renamed':
                        pin['renamedHostId'] = host
                else:
                    pin['hostId'] = replacement
                snapshot['sidebar']['pinnedThreads'].append(pin)
                original = copy.deepcopy(snapshot)
                self.assert_degraded_plan(snapshot, 'sidebar.pinnedThreads[1].hostId')
                self.assertIn('missing_hostId', p.diagnose(snapshot)['reasons'])
                self.assertEqual(snapshot, original)

    def test_unindexable_raw_records_degrade_with_field_location(self):
        for collection, fields in (
                ('projects', ('projectId', 'projectKind', 'hostId')),
                ('threads', ('id', 'kind', 'hostId')),
                ('pinnedThreads', ('id', 'kind', 'hostId'))):
            for field in fields:
                with self.subTest(collection=collection, field=field):
                    snapshot = capable()
                    parent = 'projects' if collection == 'projects' else 'sidebar'
                    snapshot[parent][collection][0].pop(field)
                    self.assert_degraded_plan(snapshot, f'{parent}.{collection}[0].{field}')

    def test_missing_or_renamed_project_membership_blocks_moves(self):
        for collection, position in (('threads', 2), ('threads', 0), ('pinnedThreads', 0)):
            for renamed in (False, True):
                with self.subTest(collection=collection, position=position, renamed=renamed):
                    snapshot = capable()
                    row = snapshot['sidebar'][collection][position]
                    membership = row.pop('projectId')
                    if renamed:
                        row['renamedProjectId'] = membership
                    self.assert_degraded_plan(snapshot, f'sidebar.{collection}[{position}].projectId')

    def test_malformed_project_membership_is_not_treated_as_unassigned(self):
        for value in (False, 0, '', [], {}):
            with self.subTest(value=value):
                snapshot = capable()
                snapshot['sidebar']['threads'][0]['projectId'] = value
                self.assert_degraded_plan(snapshot, 'sidebar.threads[0].projectId')

    def test_unknown_legacy_parameter_blocks_each_known_tool(self):
        for name in p.TOOL_FIELDS:
            with self.subTest(tool=name):
                snapshot = capable()
                snapshot['capabilities']['tools'][name].append('workspaceId')
                self.assert_degraded_plan(snapshot, 'tool_schema_mismatch:' + name)

    def test_unknown_structured_parameter_blocks_without_optional_allowlist(self):
        for name, fields in p.TOOL_FIELDS.items():
            for alias in ('inputSchema', 'parameters'):
                for required in (False, True):
                    with self.subTest(tool=name, alias=alias, required=required):
                        snapshot = capable()
                        properties = {key: {'type': 'integer' if key == 'limit' else 'string'} for key in fields}
                        properties['workspaceId'] = {'type': 'string'}
                        snapshot['capabilities']['tools'][name] = {alias: {
                            'type': 'object', 'properties': properties,
                            'required': list(fields) + (['workspaceId'] if required else [])}}
                        self.assert_degraded_plan(snapshot, 'tool_schema_mismatch:' + name)

    def test_duplicate_legacy_parameters_are_ambiguous(self):
        snapshot = capable()
        snapshot['capabilities']['tools']['list_threads'].append('limit')
        self.assert_degraded_plan(snapshot, 'tool_schema_mismatch:list_threads')

    def test_readback_missing_protection_field_never_confirms_affected_move(self):
        before = capable()
        plan = p.safe_plan(before)
        after = simulate(before, plan)
        operations = [{'operationId': t['operationId'], 'state': 'confirmed',
                       'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])}
                      for t in plan['targets']]
        operations.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        del after['sidebar']['threads'][0]['projectId']
        receipt = p.reconcile_receipt(before, after, plan, {'schemaVersion': 2, 'operations': operations})
        self.assertEqual(receipt['status'], 'unverified')
        self.assertNotIn('t-new', [m.get('threadId') for m in receipt['confirmedMoves']])
        self.assertEqual(receipt['retryable'], [])
        self.assertEqual(p.undo_plan(before, after, plan, receipt, can_move_back=True)['moves'], [])


if __name__ == '__main__':
    unittest.main()
