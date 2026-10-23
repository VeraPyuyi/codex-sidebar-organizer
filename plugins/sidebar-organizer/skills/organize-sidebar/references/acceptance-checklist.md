# Acceptance checklist / 验收清单

Generated from `scripts/acceptance_checklist.py`; do not edit copies independently.

Offline verified means synthetic regression coverage only. All host items remain unverified until separately executed with authorization. Metadata cannot prove UI visibility or deletion.

## offline.doctor

- **scope**: offline_verified
- **prerequisites**: Synthetic fixtures only; Python 3.10+; repository tests available.
- **steps**: Run CompatibilityTests and SafeProtocolTests doctor cases.
- **evidence**: Known schemas accepted; unknown tools, arguments, returns and missing hostId block moves.
- **stop**: Stop on any failed assertion or schema mismatch; retain the diagnostic and do not execute moves.
- **forbidden**: Do not access real chats, run the client, or mutate a sidebar during offline validation.

## offline.safe-plan

- **scope**: offline_verified
- **prerequisites**: Synthetic fixtures only; Python 3.10+; repository tests available.
- **steps**: Run safe protocol determinism/protection/config tests on synthetic snapshots.
- **evidence**: Deterministic v4 preview, stable operation IDs, pins and manual groups preserved.
- **stop**: Stop on any failed assertion or schema mismatch; retain the diagnostic and do not execute moves.
- **forbidden**: Do not access real chats, run the client, or mutate a sidebar during offline validation.

## offline.receipt

- **scope**: offline_verified
- **prerequisites**: Synthetic fixtures only; Python 3.10+; repository tests available.
- **steps**: Simulate confirmed and interrupted operations; reconcile before/after and journal.
- **evidence**: Only matching IDs and fresh readback confirm moves; unknown outcomes remain unverified.
- **stop**: Stop on any failed assertion or schema mismatch; retain the diagnostic and do not execute moves.
- **forbidden**: Do not access real chats, run the client, or mutate a sidebar during offline validation.

## offline.undo-plan

- **scope**: offline_verified
- **prerequisites**: Synthetic fixtures only; Python 3.10+; repository tests available.
- **steps**: Run synthetic undo conflict, host and cloud evidence tests.
- **evidence**: Only confirmed supported reverse moves appear; conflicts skipped; no section deletion.
- **stop**: Stop on any failed assertion or schema mismatch; retain the diagnostic and do not execute moves.
- **forbidden**: Do not access real chats, run the client, or mutate a sidebar during offline validation.

## offline.budget

- **scope**: offline_verified
- **prerequisites**: Synthetic fixtures only; Python 3.10+; repository tests available.
- **steps**: Run 20/50 record and actual budget exhaustion tests.
- **evidence**: Budget shortfalls remain unverified; coverage never claims full history.
- **stop**: Stop on any failed assertion or schema mismatch; retain the diagnostic and do not execute moves.
- **forbidden**: Do not access real chats, run the client, or mutate a sidebar during offline validation.

## offline.config

- **scope**: offline_verified
- **prerequisites**: Synthetic fixtures only; Python 3.10+; repository tests available.
- **steps**: Run invalid version, scope, labels and sorting configuration tests.
- **evidence**: Unknown fields rejected; protection remains enabled; sorting change is a preview.
- **stop**: Stop on any failed assertion or schema mismatch; retain the diagnostic and do not execute moves.
- **forbidden**: Do not access real chats, run the client, or mutate a sidebar during offline validation.

## host.group

- **scope**: host_required
- **prerequisites**: Separate explicit host authorization; disposable test records; current client version and schemas; private evidence directory.
- **steps**: Discover live schemas; doctor; approve a disposable test group; record returned sectionId and fresh list.
- **evidence**: Created ID and exact membership readback plus separately recorded UI observation.
- **stop**: Stop on missing capability, ambiguous identity, unknown write outcome, budget exhaustion or changed user placement; read back before any retry.
- **forbidden**: Never infer UI visibility or deletion from metadata; never bulk-delete, overwrite client state, bypass pins/manual groups or automatically retry unknown writes.

## host.move

- **scope**: host_required
- **prerequisites**: Separate explicit host authorization; disposable test records; current client version and schemas; private evidence directory.
- **steps**: Approve a scoped safe-plan for disposable records; journal each write; stop at first unknown result.
- **evidence**: Exact thread/project, source, host and destination IDs; pins/manual groups unchanged.
- **stop**: Stop on missing capability, ambiguous identity, unknown write outcome, budget exhaustion or changed user placement; read back before any retry.
- **forbidden**: Never infer UI visibility or deletion from metadata; never bulk-delete, overwrite client state, bypass pins/manual groups or automatically retry unknown writes.

## host.readback

- **scope**: host_required
- **prerequisites**: Separate explicit host authorization; disposable test records; current client version and schemas; private evidence directory.
- **steps**: Collect fresh before/after snapshots and journal; run receipt and acceptance-report.
- **evidence**: Recomputed confirmed receipt for scoped metadata; separate UI observation required.
- **stop**: Stop on missing capability, ambiguous identity, unknown write outcome, budget exhaustion or changed user placement; read back before any retry.
- **forbidden**: Never infer UI visibility or deletion from metadata; never bulk-delete, overwrite client state, bypass pins/manual groups or automatically retry unknown writes.

## host.undo

- **scope**: host_required
- **prerequisites**: Separate explicit host authorization; disposable test records; current client version and schemas; private evidence directory.
- **steps**: Confirm host supports original-section moves; request undo-plan; review and approve individual reversals.
- **evidence**: Fresh reverse-placement readback; concurrent user edits preserved; repeat preview empty.
- **stop**: Stop on missing capability, ambiguous identity, unknown write outcome, budget exhaustion or changed user placement; read back before any retry.
- **forbidden**: Never infer UI visibility or deletion from metadata; never bulk-delete, overwrite client state, bypass pins/manual groups or automatically retry unknown writes.

## host.upgrade

- **scope**: host_required
- **prerequisites**: Separate explicit host authorization; disposable test records; current client version and schemas; private evidence directory.
- **steps**: In an isolated test installation record version and manifest; upgrade; start fresh session; rediscover tools and rerun doctor.
- **evidence**: Single installation, expected build SHA/digests, compatible schemas and repeat scoped acceptance.
- **stop**: Stop on missing capability, ambiguous identity, unknown write outcome, budget exhaustion or changed user placement; read back before any retry.
- **forbidden**: Never infer UI visibility or deletion from metadata; never bulk-delete, overwrite client state, bypass pins/manual groups or automatically retry unknown writes.

## host.deletion-sync

- **scope**: host_required
- **prerequisites**: Separate explicit host authorization; disposable test records; current client version and schemas; private evidence directory.
- **steps**: Use only an explicitly authorized disposable record; independently observe deletion on each supported surface and refresh.
- **evidence**: Independent host deletion evidence; list absence alone is insufficient; unsupported refresh remains blocked.
- **stop**: Stop on missing capability, ambiguous identity, unknown write outcome, budget exhaustion or changed user placement; read back before any retry.
- **forbidden**: Never infer UI visibility or deletion from metadata; never bulk-delete, overwrite client state, bypass pins/manual groups or automatically retry unknown writes.

## host.ui

- **scope**: host_required
- **prerequisites**: Separate explicit host authorization; disposable test records; current client version and schemas; private evidence directory.
- **steps**: Inspect intended sidebar surface after readback; record client version, surface and visible grouping/order.
- **evidence**: Direct UI observation; metadata confirmation is not UI visibility.
- **stop**: Stop on missing capability, ambiguous identity, unknown write outcome, budget exhaustion or changed user placement; read back before any retry.
- **forbidden**: Never infer UI visibility or deletion from metadata; never bulk-delete, overwrite client state, bypass pins/manual groups or automatically retry unknown writes.

