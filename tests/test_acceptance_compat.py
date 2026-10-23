"""Synthetic acceptance and compatibility contracts; no host access."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_sidebar_plan import planner as p, fixture, simulate, ROOT, SCRIPT


def capable():
    s = fixture()
    s['capabilities'] = {'adapter': 'native-v1', 'defaultSectionIds': sorted(p.DEFAULTS),
                         'tools': copy.deepcopy(p.TOOL_FIELDS)}
    return s


class CompatibilityTests(unittest.TestCase):
    def test_legacy_parameter_lists_are_deprecated_but_usable(self):
        d = p.diagnose(capable())
        self.assertTrue(d['canPlanMoves'])
        self.assertIn('deprecated:parameter_list', d['reasons'])

    def test_structured_schema_and_old_parameters_alias(self):
        for field in ('inputSchema', 'parameters'):
            s = capable()
            s['capabilities']['tools'] = {name: {field: {'type': 'object', 'properties': {
                key: {'type': 'integer' if key == 'limit' else 'string'} for key in fields},
                'required': fields}} for name, fields in p.TOOL_FIELDS.items()}
            d = p.diagnose(s)
            self.assertTrue(d['canPlanMoves'], d)
            self.assertEqual('deprecated:parameters' in d['reasons'], field == 'parameters')
            self.assertEqual(len(p.safe_plan(s)['moves']), 5)

    def test_unknown_tool_parameter_return_and_host_changes_block(self):
        for change in ('tool', 'parameter', 'return', 'host', 'required', 'type'):
            with self.subTest(change=change):
                s = capable()
                if change == 'tool': del s['capabilities']['tools']['list_threads']
                elif change == 'parameter': s['capabilities']['tools']['move_thread_to_sidebar_section'][0] = 'conversationId'
                elif change == 'return': s['sidebar']['groups'] = s['sidebar'].pop('sections')
                elif change == 'host': del s['sidebar']['threads'][0]['hostId']
                else:
                    s['capabilities']['tools']['list_threads'] = {'inputSchema': {
                        'type': 'object', 'properties': {'limit': {'type': 'string' if change == 'type' else 'integer'}, 'cursor': {'type': 'string'}},
                        'required': ['limit', 'cursor'] if change == 'required' else ['limit']}}
                self.assertFalse(p.diagnose(s)['canPlanMoves'])
                self.assertEqual(p.safe_plan(s)['moves'], [])
                self.assertFalse(any(t['state'] == 'create' for t in p.safe_plan(s)['targets']))

    def test_unknown_output_schema_blocks(self):
        s = capable()
        s['capabilities']['tools']['list_threads'] = {'inputSchema': {'type': 'object', 'properties': {'limit': {'type': 'integer'}}},
                                                     'outputSchema': {'type': 'object', 'properties': {'items': {'type': 'array'}}}}
        self.assertFalse(p.diagnose(s)['canPlanMoves'])

    def test_local_state_id_alias_is_reported_deprecated(self):
        from test_sidebar_plan import alias_fixture
        raw, state = alias_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic-state.json'
            path.write_text(json.dumps(state), encoding='utf-8')
            captured = p.capture_identity(raw, path)
        self.assertIn('deprecated:local-sidebar-custom-sections-v3.id', p.diagnose(captured)['reasons'])
        self.assertTrue(p.diagnose(captured)['canPlanMoves'])


class AcceptanceTests(unittest.TestCase):
    def test_release_includes_checklist_and_validator(self):
        spec = importlib.util.spec_from_file_location('builder', ROOT / 'scripts/build_release.py')
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        self.assertIn('scripts/acceptance_checklist.py', builder.SKILL_FILES)
        self.assertIn('references/acceptance-checklist.md', builder.SKILL_FILES)

    def test_checklist_structure_and_document_drift(self):
        path = SCRIPT.with_name('acceptance_checklist.py')
        self.assertTrue(path.exists())
        spec = importlib.util.spec_from_file_location('checklist', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.validate(module.ITEMS)
        self.assertEqual((ROOT / 'docs/ACCEPTANCE_CHECKLIST.md').read_text(encoding='utf-8'), module.render())
        self.assertEqual((SCRIPT.parent.parent / 'references/acceptance-checklist.md').read_text(encoding='utf-8'), module.render())
        for field in ('id', 'prerequisites', 'steps', 'evidence', 'stop', 'forbidden'):
            rows = copy.deepcopy(module.ITEMS); del rows[0][field]
            with self.assertRaises(ValueError): module.validate(rows)
        with self.assertRaises(ValueError): module.validate(module.ITEMS + [module.ITEMS[0]])

    def test_missing_evidence_and_fifty_limit_never_pass(self):
        self.assertTrue(hasattr(p, 'acceptance_report'))
        s = fixture()
        s['sidebar']['threads'] = [{'id': f'synthetic-{i}', 'kind': 'chatgpt'} for i in range(50)]
        s['sidebar']['sections'][4]['itemKeys'] = [f'chatgpt:conversation:synthetic-{i}' for i in range(50)]
        result = p.acceptance_report(s)
        self.assertEqual(result['verified'], [])
        self.assertIn('host.undo', result['unverified'])
        self.assertIn('host.upgrade', result['unverified'])
        self.assertFalse(result['coverage']['complete'])
        self.assertIsNone(result['coverage']['accountCompletionRate'])
        self.assertFalse(result['uiVisible']); self.assertFalse(result['deletionProven'])
        self.assertEqual(p.acceptance_report(s, receipt={'status': 'confirmed'})['verified'], [])

    def test_report_recomputes_receipt_and_blocks_changed_capabilities(self):
        self.assertTrue(hasattr(p, 'acceptance_report'))
        before = fixture(); plan = p.safe_plan(before); after = simulate(before, plan)
        ops = [{'operationId': t['operationId'], 'state': 'confirmed', 'sectionId': next(s['sectionId'] for s in after['sidebar']['sections'] if s['name'] == t['name'])} for t in plan['targets']]
        ops.extend({'operationId': m['operationId'], 'state': 'confirmed'} for m in plan['moves'])
        journal = {'schemaVersion': 2, 'operations': ops}
        receipt = p.reconcile_receipt(before, after, plan, journal)
        result = p.acceptance_report(after, before, plan, receipt, journal)
        self.assertEqual(result['verified'], ['run.metadata_readback'])
        receipt['confirmedMoves'] = []
        self.assertEqual(p.acceptance_report(after, before, plan, receipt, journal)['verified'], [])
        after['capabilities'] = {'adapter': 'future'}
        self.assertIn('host.move', p.acceptance_report(after)['blocked'])

    def test_acceptance_report_cli_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'snapshot.json', Path(tmp)/'report.json'
            source.write_text(json.dumps(fixture()), encoding='utf-8')
            cmd = [sys.executable, str(SCRIPT), 'acceptance-report', '--input', str(source), '--output', str(out)]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(json.loads(out.read_text())['verified'], [])
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 1)


if __name__ == '__main__': unittest.main()
