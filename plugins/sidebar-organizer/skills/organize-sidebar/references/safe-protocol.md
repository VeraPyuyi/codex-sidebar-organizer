# Offline v4 planning and receipts

All commands consume explicit JSON files and exclusively create an output file. They do not call a host or network. Use a private temporary directory. Plan data, mappings, journals and receipts are not authorization or authenticated evidence. Collect them through the current trusted native session. No identity evidence may be reused across observation rounds.

## Diagnosis

`python scripts/sidebar_plan.py doctor --input snapshot.json --output doctor.json`

Optional snapshot `capabilities`:

```json
{"adapter":"native-v1","clientVersion":"unknown","defaultSectionIds":["threads","chats","projects","orbit","agents"],"tools":{"list_threads":["limit"],"list_projects":[],"create_sidebar_section":["name"],"move_project_to_sidebar_section":["projectId","sectionId"],"move_thread_to_sidebar_section":["threadId","source","sectionId"]}}
```

The tools object contains schema parameter names discovered in the current session. Namespace stripping is the collector's responsibility. Unknown adapters/default partitions, missing tools, renamed required fields and invalid snapshot layout disable moves. Tool discovery is structural, not a guarantee of native behavior. Missing client version stays `unknown`. Old snapshots remain readable with an explicit `legacy_snapshot` warning; add discovered capabilities before actual use. Unknown custom sections remain protected. Optional read/reorder/preferences tools must be checked separately before those actions.

## Preview

`python scripts/sidebar_plan.py safe-plan --input before.json --language zh --mapping mapping.json --config config.json --budget 100 --output plan.json`

Mapping/config/budget options are optional. v4 includes rule/capability versions, deterministic operation IDs, original section, logical category and expected destination ID. Categories: `local.projects`, `chatgpt.projects`, `local.chats`, `chatgpt.chats`, `codex.cloud.chats`, `unconfirmed`, `remote.<host>.projects`, `remote.<host>.chats`.

Mapping JSON is a category-to-confirmed-section-ID object, for example `{"local.chats":"synthetic-section"}`. Preserve this non-identity mapping across language changes; refresh its existence against every inventory. A renamed section retains its ID and is reused without renaming. Missing mapped sections block dependent moves until fresh evidence resolves the mapping; do not recreate or move to an old ID. Without mappings the explicitly reported legacy exact-label fallback cannot recognize translated names. Duplicate names remain ambiguous. v4 creates only targets needed by eligible moves unless configured otherwise; empty inventory creates nothing. v3 `plan` and `verify` remain compatibility-only, with eager standard targets and name-based limited verification. Never interpret their result as v4 ID confirmation.

Config version 1 allows only `version`, `sources` (codex/chatgpt string array), `hosts` (string array), `excludeIds` (raw IDs or canonical keys), `labels` (category/display-label object), `createEmptyGroups` (boolean, default false), `sort` (updated_at/manual). Unknown fields/versions, invalid types and colliding labels fail. Source/host scopes and exclusions only narrow eligibility. Pins, project membership, identity and existing custom placements cannot be disabled. `sortingPreview` displays before/after and whether the preference change needs approval within the user's authorized request. Labels are independent of confirmed mapping IDs.

## Journal, timeout and readback

Immediately journal a write as pending, then confirmed with its exact returned ID, or unknown on timeout. Persist before moving on. Example (synthetic):

```json
{"schemaVersion":2,"actualToolCalls":12,"operations":[{"operationId":"operation-id-from-plan","state":"confirmed","sectionId":"exact-returned-section-id"}]}
```

v1 journals with the same operations shape remain readable. States are pending/confirmed/unknown; duplicate or foreign operation IDs fail. Actual call count is supplied by the trusted collector and stays null when unavailable. It is not measured by the pure helper.

`python scripts/sidebar_plan.py receipt --before before.json --after fresh-after.json --plan plan.json --journal journal.json --output receipt.json`

Recomputation of all v4 fields rejects altered plans. Confirmed creation IDs must be new to the before snapshot, present with the expected label on fresh readback, and distinct across categories. A unique matching label alone never confirms a created ID. Unknown creations are never retryable, even when absent from a cached list; resolve using the original response/correlated host evidence or stop. Unknown moves are never automatically retried: new readback may confirm an exact ID relationship. User placement changes, new pins/project membership, disappearing targets and identity changes remain unknown. The retryable list is informational and never executes actions. Re-read and check protection immediately before each authorized write.

Only per-move `state: confirmed`/`confirmedMoves` can be reported successful. Overall `confirmed` additionally needs all planned moves, invariant checks, requested sort and adequate budget. Zero moves does not produce full success. `coverage` separates proven placements, protected, skipped and unverified entries; complete history is always false, including a 50-entry recent window. Budget estimate = four list calls (projects/threads before/after) + twice the listed durable count + planned moves + needed creates + two preference/order allowances. Thus 20 cloud candidates reserve 40 verification calls, 50 reserve 100. This is a preview estimate, not measured cost; unavailable pagination and extra re-reads can require more. Budget exhaustion leaves status unverified and no retryable writes.

## Limited undo

`python scripts/sidebar_plan.py undo-plan --before before.json --after current.json --plan plan.json --receipt receipt.json --can-move-back --output undo.json`

Use only a locally trusted receipt generated for this plan. The flag is permitted only after discovering that original default-section destinations are supported by native move tools. Without it the result is unsupported. Undo previews only this run's confirmed moves whose current relation and record metadata are unchanged. Pins/new project membership and concurrent edits are excluded; already-restored relations yield no move on repeat. No whole-run rollback, group deletion, order restoration or host mutation is implemented. The helper does not cryptographically authenticate receipts.

## Release and installation

Both ZIPs contain BUILD_MANIFEST.json: source HEAD SHA, dirty-source flag, Python version and SHA-256 of every other archive file. The manifest excludes itself. Archive integrity/manifest checks and extracted synthetic CLI smoke run during build. Use `scripts/build_release.py`'s `installation_inventory(explicit_root)` only on the chosen installation tree; it reports duplicate plugin/standalone copies and file hashes without starting Codex. Upgrade/rollback fixtures are isolated file-copy simulations, not a real native plugin-manager test. Real sidebar behavior, collapse/opening, deletion sync and cross-device behavior remain pending/unsupported as stated in VALIDATION.md.
