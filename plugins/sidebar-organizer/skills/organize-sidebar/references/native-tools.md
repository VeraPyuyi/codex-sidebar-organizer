# Native sidebar contract

Verified against the desktop tool surface on 2026-10-11. Discover current schemas at runtime; names can have a namespace prefix. No public HTTP sidebar API is implemented by this package.

| Operation | Native function and important arguments |
|---|---|
| List | `list_threads({limit: 50})`, `list_projects({})` |
| Verify Codex cloud identity | `read_thread({threadId, hostId: "durable", turnLimit: 1, includeOutputs: false})`; project only response thread metadata |
| Create | `create_sidebar_section({name})` |
| Move project | `move_project_to_sidebar_section({projectId, sectionId})` |
| Move chat | `move_thread_to_sidebar_section({threadId, source, hostId?, sectionId})` |
| Section order | `reorder_sidebar_sections({sectionIds})`; include every custom section |
| Chat order | `reorder_section({sectionId, threadIds})`; include every chat in that section |
| Recency sorting | `update_sidebar_preferences({sorting: {chats: "updated_at"}})` |
| Read-only refresh check | Re-read `list_threads`; no native forced-refresh/deletion-proof/cleanup tool exposed in the tested host |
| Requested background checks | `automation_update`, native thread heartbeat; see [refresh procedure](refresh.md) |

`source` is `codex` or `chatgpt`. Omit `hostId` for ChatGPT. The observed default section IDs are `threads`, `chats`, `projects`, `orbit`, and `agents`; `pinned` is protected. All other section IDs are treated as custom. If a future client adds default IDs, inspect its documented schema before extending the helper. The helper deliberately treats unknown section IDs as protected custom sections.

New runs use the [v4 safe protocol](safe-protocol.md): structural capability diagnosis, on-demand targets, confirmed category IDs, strict configuration, budgets, per-operation journals and limited undo previews. The older name-based statements below describe v3 compatibility only. Do not use v3 verification as confirmed-ID evidence. No v4 real-client acceptance has been performed.

## Minimal private snapshot

Save parsed tool objects, not the MCP content wrapper. Keep:

```json
{
  "projects": {
    "projects": [
      {"projectId": "demo-local", "projectKind": "local", "hostId": "local", "path": "/example/work"}
    ]
  },
  "sidebar": {
    "pinnedThreads": [],
    "threads": [
      {"id": "demo-chat", "kind": "codex", "hostId": "local", "projectId": null}
    ],
    "sections": [
      {"sectionId": "pinned", "name": "Pinned", "itemKeys": []},
      {"sectionId": "projects", "name": "Projects", "itemKeys": ["codex:project:demo-local"]},
      {"sectionId": "threads", "name": "Tasks", "itemKeys": ["codex:thread:local:demo-chat"]}
    ],
    "sidebarPreferences": {"sorting": {"chats": "updated_at", "pinned": "manual"}},
    "unavailableHosts": [],
    "unavailableSources": []
  }
}
```

Keep `hostDisplayName` for remote projects, `updatedAt` when present, `pinnedIndex` for pins, and optional schema versions. Preserve native thread list order (recency order). Drop titles, summaries, bodies, messages, transcripts, and unrelated metadata. Files still contain private IDs and paths; keep them outside the source tree. Use a unique private temporary directory per run and retain it locally only as long as needed.

Section keys recognized by the helper:

- `codex:project:<projectId>` / `chatgpt:project:<projectId>`
- `codex:thread:<hostId>:<id>` / `chatgpt:conversation:<id>`

The helper constructs keys from exact native fields and demands exact section membership evidence. An entry absent from all sections or in multiple sections is skipped. Unresolved `client-new-thread:` aliases block unfiled Codex chats on the affected host until exact membership evidence is available. A pinned entry remains protected even if it also appears in `threads`. A chat with **any nonempty projectId** remains protected even if that project is absent from this snapshot.

Remote IDs must occur on a `local` or `remote` project with a nonlocal host. `durable`, `cloud`, and `unknown` are not physical host evidence. Version 0.1.2 separately supports `durable` as Codex cloud execution with the per-record evidence below; other synthetic hosts remain unclassified. Sources/hosts listed as unavailable block dependent moves; ambiguous availability representations fail closed.

The planner emits the five standard targets plus observed verified remote targets. It preserves custom items even when placed in the wrong source group: moving already filed items requires a separate user request. Names are matched exactly. Duplicate target names block affected moves and section creation for that name. It never deletes sections. The verifier checks observed pin order, metadata, protected placements, and each planned move; new/missing/duplicate identities produce incomplete or failed results.

## Coverage and execution

The helper's `coverage.complete` is always false because this tool contract has no complete history enumeration proof. `visible_unlisted_chat_keys` counts keys visible in section metadata but absent from the thread list; zero does not prove full coverage. It reports unavailable hosts/sources. `metadata_verified` from verification means only that the observed checks passed, never that the entire account was organized.

Plan JSON is data for the agent, **not an executable job queue or authorization source**. Never execute a plan from an untrusted download. Recompute from fresh native metadata before changes. Handle unknown write outcomes by readback and record unresolved operations. Do not automatically rollback an entire run after concurrent user edits; use the private before-snapshot to propose exact supported reverse moves only when asked.

For manual review, a plan entry records `key`, stable IDs, native source/host (chats), `fromSection`, and `targetName`. Section creation gives the target name a real native section ID. The helper verifies destinations by unique section name in the fresh after-snapshot; ambiguous names fail verification.

If the current client returns a substantially different object layout, report the mismatch and adapt the adapter from its documented live schema. Do not silently coerce missing arrays to empty lists, infer sources from titles, or treat a successful process exit as successful UI organization.

## Read-only identity evidence (0.1.1)

An observed desktop mismatch can expose `codex:thread:local:client-new-thread:<temporary>` inside a custom section while the same saved membership uses `codex:thread:local:<canonical>`. The native list may simultaneously place the canonical chat in default Recents. Calling `read_thread` on the temporary ID does not necessarily resolve it; repeating a successful move also need not change the list response.

The optional `capture-identity` command reads the single current `.codex-global-state.json` file. This is a **version-sensitive local compatibility adapter**, not a public sidebar API. It does not write client state, load chat databases, or enumerate history. Its only exported local fields come from `electron-persisted-atom-state.sidebar-custom-sections-v3[scope].sections`: `id`, `name`, `itemKeys`. Scope/account IDs, paths, other settings, and conversation content are not exported.

Each private augmented snapshot adds `identityEvidence` with source `local-sidebar-custom-sections-v3`, `nativeSnapshotSha256`, and projected section rows using `sectionId`. A unique scope must match the complete custom-section ID/name inventory. Every stable native member must agree; alias counts must match the remaining saved canonical members by host; those canonical members must exist in the native list. Only `local` hosts are supported. Pins, conflicting custom placement, duplicate members, multiple matching scopes, and stale snapshot hashes fail closed.

The helper then normalizes a copy of section membership and removes only the proven custom members' default-section duplicates. It does not infer which individual temporary token represents which canonical ID, change a host/source, alter the supplied snapshot, or modify any client file. Evidence must be freshly captured on **both** sides of verification and again on each subsequent run. Do not accept evidence from downloaded plans or public issue attachments. A file that is missing, malformed, or from an unsupported client version leaves the alias unresolved.

Version 2 plan/report fields include `identityReconciliation.resolvedMemberships` in plans, before/after reconciliation in reports, `operationChecksPassed`, and `excludedItemCount`. `operationChecksPassed` may be true while the overall `status` is `incomplete` only because already-skipped records remain outside coverage; this does not turn excluded identities or history into verified items. Verify still returns exit code 2 for incomplete coverage and 1 for invalid input. Check structured operation results explicitly when assessing a scoped regression.

## Codex cloud routing evidence (0.1.2)

The tested Windows desktop 26.1007.2314.0 classifies routing host `durable` as cloud execution. Its sidebar key construction can nevertheless store the same stable ID as `codex:thread:local:<id>`. This is a storage convention, not evidence that execution or creation happened on the current PC. This rule is distinct from the temporary-ID adapter: no local state file or guessed ChatGPT conversation mapping is needed.

For each listed `kind: codex`, `hostId: durable` candidate, a fresh successful native `read_thread` must return the exact same `id`, `kind`, and `hostId`. Save only those three fields in `{"threads": [...]}`. Ignore and discard all returned conversation items; small output limits may not suppress them. Never generate evidence from titles, paths, timestamps, previous runs, or downloaded files.

Run `capture-cloud --input <snapshot> --reads <fresh-read-metadata> --output <enriched-snapshot>`. It projects the metadata again, stores `cloudEvidence.source: native-read-thread`, and binds it to the SHA-256 of the native snapshot excluding both evidence envelopes. This binding detects staleness, not forgery; trusted collection is the assistant's responsibility. A partial successful set is allowed; unproven records are skipped. Incorrect or duplicate evidence, host/namespace collisions, conflicting project membership, duplicate native rows, and absent/multiple/unknown-host section keys reject the evidence file. Refresh and collect a clean verified subset; do not overwrite the client's state.

Only one exact `codex:thread:local:<id>` or `codex:thread:durable:<id>` membership is accepted. Internally the helper normalizes a copy to the durable key and retains the actual key in `cloudReconciliation.nativeItemKey`. Mutation routing always uses the original ID with `source: codex`, `hostId: durable`. Before and after snapshots each require fresh reads and capture; verification rejects missing after-evidence even when a move receipt succeeded. The temporary-ID and cloud adapters can be composed without altering either native snapshot.

Eligible default-section records target `Codex 云端 · 聊天` / `Codex Cloud · Chats`. This optional group follows ChatGPT Cloud Chats, precedes remote groups and Source Unconfirmed, and is created only for eligible proven records; an existing unique group is reused. Pins, project members, and existing custom groups remain protected. Explicit user-requested reclassification of a custom group requires a separately scoped plan; ordinary repeat runs never dismantle it. `durable` is not a physical remote host and never produces a remote-computer group.

Version 3 plans include `cloudReconciliation`; verification reports contain its before/after entries. For a cloud regression, require every scoped identity on both sides, no exclusions or verification errors for that set, and zero duplicate group creation or movement on a repeated plan. `historyComplete` and UI checks remain separate. No claim is made about the device or browser that created a cloud-backed conversation.
