# Offline v4 planning and receipts

All commands consume explicit JSON files and exclusively create an output file. They do not call a host or network. Use a private temporary directory. Plan data, mappings, journals and receipts are not authorization or authenticated evidence. Collect them through the current trusted native session. No identity evidence may be reused across observation rounds.

## Diagnosis

`python scripts/sidebar_plan.py doctor --input snapshot.json --output doctor.json`

Optional snapshot `capabilities`:

```json
{"adapter":"native-v1","clientVersion":"unknown","defaultSectionIds":["threads","chats","projects","orbit","agents"],"tools":{"list_threads":["limit"],"list_projects":[],"create_sidebar_section":["name"],"move_project_to_sidebar_section":["projectId","sectionId"],"move_thread_to_sidebar_section":["threadId","source","hostId","sectionId"]}}
```

The tools object contains schema parameter names discovered in the current session, including `hostId` for Codex chat routing. Its presence in the schema is required even though ChatGPT calls omit that argument. Namespace stripping is the collector's responsibility. Unknown adapters/default partitions, missing tools, renamed required fields and invalid snapshot layout disable moves. Tool discovery is structural, not a guarantee of native behavior. Missing client version stays `unknown`. Old snapshots remain readable with an explicit `legacy_snapshot` warning; add discovered capabilities before actual use. Unknown custom sections remain protected. Optional read/reorder/preferences tools must be checked separately before those actions.

## Compatibility and acceptance

See the [acceptance checklist](acceptance-checklist.md). `python scripts/acceptance_checklist.py` emits JSON; `--check references/acceptance-checklist.md` validates structure and exact document content.

Each tool may use `{"inputSchema":{"type":"object","properties":{"limit":{"type":"integer"}},"required":["limit"]}}` (example: list_threads). Other known fields use string types. `parameters` is an explicit deprecated alias for `inputSchema`; supplying both is ambiguous and blocked. Legacy parameter-name lists remain usable with `deprecated:parameter_list`. The existing local-state `id` to `sectionId` evidence adapter records `deprecated:local-sidebar-custom-sections-v3.id`. There is no guessed tool-name or routing-argument alias. Namespace stripping remains the collector's responsibility.

This conservative adapter rejects unknown schema keywords, outputSchema declarations, unknown arguments (including optional properties), and changed known-field types. Legacy parameter lists must contain exactly the known names without duplicates; no optional-extension allowlist is currently defined. Supplied return data must match the known snapshot layout. Diagnosis checks raw projects, recent threads and pinnedThreads before indexing can discard records. Every chat must explicitly contain projectId (null or a nonempty string); missing/renamed protection fields, invalid identities and missing Codex hostId degrade diagnosis and block v4 moves, with field locations reported. Preserve both explicit pin arrays and section membership. Fresh readback requires protection fields for previously observed chats; concurrent new chats remain outside the receipt's proven scope. Unsupported output schemas must be reviewed before extending the adapter; do not discard them to bypass diagnosis. Legacy snapshots remain offline-compatible, but actual use requires discovered capabilities. v3 is not a fallback for degraded diagnosis.

`python scripts/sidebar_plan.py acceptance-report --input after.json --before before.json --plan plan.json --receipt receipt.json --journal journal.json --output acceptance.json`

Only `--input` and `--output` are mandatory. Missing run evidence stays unverified. Full supplied evidence is reconciled again and compared to the receipt; confirmed scoped metadata appears as `run.metadata_readback`. This is not authenticated provenance or a host UI acceptance claim. Host checks remain unverified, or blocked by degraded capabilities. The report never asserts UI visibility, deletion or account-wide completion, including at the 50-item limit. Undo and upgrade need separate authorized host testing. Exit 0 means report generation succeeded, not that acceptance passed.

## Preview

`python scripts/sidebar_plan.py safe-plan --input before.json --language zh --mapping mapping.json --config config.json --budget 100 --output plan.json`

Mapping/config/budget options are optional. v4 includes rule/capability versions, deterministic operation IDs, original section, logical category and expected destination ID. Categories: `local.projects`, `chatgpt.projects`, `local.chats`, `chatgpt.chats`, `codex.cloud.chats`, `unconfirmed`, `remote.<host>.projects`, `remote.<host>.chats`.

Mapping JSON is a category-to-confirmed-section-ID object, for example `{"local.chats":"synthetic-section"}`. Preserve this non-identity mapping across language changes; refresh its existence against every inventory. A renamed section retains its ID and is reused without renaming. Missing mapped sections block dependent moves until fresh evidence resolves the mapping; do not recreate or move to an old ID. Without mappings the explicitly reported legacy exact-label fallback cannot recognize translated names. Duplicate names remain ambiguous. v4 creates only targets needed by eligible moves unless configured otherwise; empty inventory creates nothing. v3 `plan` and `verify` remain compatibility-only, with eager standard targets and name-based limited verification. Never interpret their result as v4 ID confirmation.

Config version 1 allows only `version`, `sources` (codex/chatgpt string array), `hosts` (string array), `excludeIds` (raw IDs or canonical keys), `labels` (category/display-label object), `createEmptyGroups` (boolean, default false), `sort` (updated_at/manual). Unknown fields/versions, invalid types and colliding labels fail. Source/host scopes and exclusions only narrow eligibility. Pins, project membership, identity and existing custom placements cannot be disabled. `sortingPreview` displays before/after and whether the preference change needs approval within the user's authorized request. Labels are independent of confirmed mapping IDs.

## Journal, timeout and readback

Journal each dispatched write as pending, then confirmed on a successful response, or unknown on timeout. Record the exact returned `sectionId` for creations and each move's own `operationId`; a creation entry does not record its dependent moves. Do not prepopulate the journal with undispatched plan entries. Persist before moving on. Example (synthetic):

```json
{"schemaVersion":2,"actualToolCalls":12,"operations":[{"operationId":"create-operation-id-from-plan","state":"confirmed","sectionId":"exact-returned-section-id"},{"operationId":"move-operation-id-from-plan","state":"confirmed"}]}
```

v1 journals with the same operations shape remain readable. States are pending/confirmed/unknown; duplicate or foreign operation IDs fail. Actual call count is supplied by the trusted collector and stays null when unavailable. It is not measured by the pure helper.

`python scripts/sidebar_plan.py receipt --before before.json --after fresh-after.json --plan plan.json --journal journal.json --output receipt.json`

Recomputation of all v4 fields rejects altered plans. Confirmed creation IDs must be new to the before snapshot, present with the expected label on fresh readback, and distinct across categories. A unique matching label alone never confirms a created ID. Pending or unknown journal entries are unresolved writes and never retryable, even when absent from a cached list. Resolve creations using the original response/correlated host evidence or stop. Fresh exact destination-ID readback can resolve a journaled move; placement without this run's move entry cannot establish success or undo eligibility. Only operations absent from the journal and verified as not attempted may appear in `retryable`; it is informational and never executes actions. User placement changes, new pins/project membership, disappearing targets and identity changes remain unknown. Every placement outside the actual v4 move set, including configured exclusions, must remain unchanged. Re-read and check protection immediately before each authorized write.

Report successful moves from `confirmedMoves` and `coverage.proven`; inspect `operations` for individual states and reasons. Overall `status: confirmed` additionally needs all planned moves and requested target operations (including empty-group creations) confirmed, invariant checks, requested sort and adequate budget. Zero moves does not produce full success. `coverage` separates proven placements, protected, skipped and unverified entries; `coverage.complete` is always false, including a 50-entry recent window. Budget estimate = four list calls (projects/threads before/after) + twice the listed durable count + planned moves + needed creates + two preference/order allowances. Thus 20 cloud candidates reserve 40 verification calls, 50 reserve 100. This is a preview estimate, not measured cost; unavailable pagination and extra re-reads can require more. A finite budget requires `actualToolCalls`. Missing actual calls, actual overruns or an insufficient estimate produce `status: unverified`, `budget.sufficient: false` and an explicit `budget.reason` also listed in `unverified`; confirmed operations become unknown and `confirmedMoves`, `coverage.proven` and `retryable` are empty.

## Limited undo

`python scripts/sidebar_plan.py undo-plan --before before.json --after current.json --plan plan.json --receipt receipt.json --can-move-back --output undo.json`

Use only a locally trusted receipt generated for this plan. The flag is permitted only after discovering that original default-section destinations are supported by native move tools. Without it the result is unsupported. Undo previews only this run's confirmed moves whose current relation and record metadata are unchanged. Recheck current source/host availability and unresolved identities before reversing any placement. Durable chats require fresh cloud evidence bound to the current snapshot, for both native durable keys and local-prefixed storage keys. Pins/new project membership and concurrent edits are excluded; already-restored relations yield no move on repeat. No whole-run rollback, group deletion, order restoration or host mutation is implemented. The helper does not cryptographically authenticate receipts.

## Release and installation

Both ZIPs contain BUILD_MANIFEST.json: source HEAD SHA, dirty-source flag, Python version and SHA-256 of every other archive file. The manifest excludes itself. Archive integrity/manifest checks and extracted synthetic CLI smoke run during build. Use `scripts/build_release.py`'s `installation_inventory(explicit_root)` only on the chosen installation tree; it reports duplicate plugin/standalone copies and file hashes without starting Codex. Upgrade/rollback fixtures are isolated file-copy simulations, not a real native plugin-manager test. Real sidebar behavior, collapse/opening, deletion sync and cross-device behavior remain pending/unsupported as stated in VALIDATION.md.
