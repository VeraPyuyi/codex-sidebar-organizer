#!/usr/bin/env python3
"""Read-only sidebar planner/verifier. Python 3.10+, standard library only."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys

DEFAULTS = {"threads", "chats", "projects", "orbit", "agents"}
NON_HOSTS = {"durable", "cloud", "unknown"}
CLOUD_LABELS = {"zh": "Codex 云端 · 聊天", "en": "Codex Cloud · Chats"}
LABELS = {
    "zh": ["本机 · 项目", "ChatGPT 云端 · 项目", "本机 · 聊天", "ChatGPT 云端 · 聊天", "来源待确认"],
    "en": ["Local · Projects", "ChatGPT Cloud · Projects", "Local · Chats", "ChatGPT Cloud · Chats", "Source Unconfirmed"],
}


def stable(value):
    return isinstance(value, str) and bool(value.strip())


def fingerprint(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def native_snapshot(snapshot):
    return {k: v for k, v in snapshot.items() if k not in {"identityEvidence", "cloudEvidence"}}


def chat_key(row):
    if not stable(row.get("id")):
        return None
    if row.get("kind") == "chatgpt":
        return "chatgpt:conversation:" + row["id"]
    if row.get("kind") == "codex" and stable(row.get("hostId")):
        return f"codex:thread:{row['hostId']}:{row['id']}"
    return None


def alias_host(key):
    match = re.fullmatch(r"codex:thread:([^:]+):client-new-thread:.+", key)
    return match.group(1) if match else None


def reconcile(snapshot, evidence=None):
    """Normalize only proven custom membership; never guess an alias-to-ID pair."""
    native = native_snapshot(snapshot)
    proof = evidence if evidence is not None else snapshot.get("identityEvidence")
    if proof is None:
        return snapshot, []
    if (not isinstance(proof, dict) or proof.get("source") != "local-sidebar-custom-sections-v3"
            or proof.get("nativeSnapshotSha256") != fingerprint(native)):
        raise ValueError("Identity evidence does not match this native snapshot")
    sidebar = native["sidebar"]
    sections = array(sidebar, "sections")
    custom = {s["sectionId"]: s for s in sections if s["sectionId"] not in DEFAULTS | {"pinned"}}
    saved_rows = array(proof, "sections")
    saved = {s["sectionId"]: s for s in saved_rows}
    if len(custom) != len([s for s in sections if s["sectionId"] in custom]) or len(saved) != len(saved_rows) or set(custom) != set(saved):
        raise ValueError("Identity evidence has a different custom section inventory")
    known = {chat_key(r) for r in array(sidebar, "threads") + array(sidebar, "pinnedThreads")}
    known.discard(None)
    resolved = []
    replacements = {}
    for sid, section in custom.items():
        stored = saved[sid]
        if section["name"] != stored.get("name"):
            raise ValueError("Identity evidence section name mismatch")
        original, canonical = array(section, "itemKeys"), array(stored, "itemKeys")
        if not all(stable(k) for k in original + canonical):
            raise ValueError("Identity evidence contains invalid item keys")
        if len(set(original)) != len(original) or len(set(canonical)) != len(canonical):
            raise ValueError("Identity evidence contains duplicate membership")
        aliases = [k for k in original if alias_host(k)]
        unchanged = set(original) - set(aliases)
        if any(alias_host(k) for k in canonical) or not unchanged.issubset(canonical):
            raise ValueError("Identity evidence disagrees on stable membership")
        added = set(canonical) - unchanged
        if len(added) != len(aliases):
            raise ValueError("Identity evidence has mismatched alias cardinality")
        hosts = []
        for key in sorted(added):
            match = re.fullmatch(r"codex:thread:([^:]+):(.+)", key)
            if not match or key not in known:
                raise ValueError("Canonical identity is not in the native chat list")
            host = match.group(1)
            # This adapter is for the current machine's persisted membership only.
            if host != "local" or host in NON_HOSTS:
                raise ValueError("Local identity evidence cannot resolve other hosts")
            hosts.append(host)
            other = [s["sectionId"] for s in sections if s["sectionId"] != sid and key in s["itemKeys"]]
            if len(other) > 1 or any(place not in DEFAULTS for place in other):
                raise ValueError("Canonical identity conflicts with another custom/pinned section")
            if any(chat_key(r) == key for r in sidebar["pinnedThreads"]):
                raise ValueError("Identity evidence conflicts with a pinned chat")
        if Counter(hosts) != Counter(alias_host(k) for k in aliases):
            raise ValueError("Identity evidence host mismatch")
        if aliases:
            replacements[sid] = canonical
            resolved.extend({"key": key, "sectionId": sid} for key in sorted(added))
    if not replacements:
        return snapshot, []
    all_keys = [k for row in saved_rows for k in row["itemKeys"]]
    if len(all_keys) != len(set(all_keys)):
        raise ValueError("Persisted membership occurs in multiple custom sections")
    normalized = json.loads(json.dumps(native))
    resolved_keys = {r["key"] for r in resolved}
    for section in normalized["sidebar"]["sections"]:
        if section["sectionId"] in replacements:
            section["itemKeys"] = list(replacements[section["sectionId"]])
        elif section["sectionId"] in DEFAULTS:
            section["itemKeys"] = [k for k in section["itemKeys"] if k not in resolved_keys]
    return normalized, resolved


def capture_identity(snapshot, state_path):
    """Read one local state file, export only matching section metadata, never write it."""
    native = native_snapshot(snapshot)
    sections = array(native["sidebar"], "sections")
    if not any(alias_host(k) for s in sections for k in s["itemKeys"]):
        return {k: v for k, v in snapshot.items() if k != "identityEvidence"}
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    buckets = state.get("electron-persisted-atom-state", {}).get("sidebar-custom-sections-v3")
    if not isinstance(buckets, dict):
        raise ValueError("Local sidebar state schema is unavailable; keep aliases unresolved")
    candidates = []
    for bucket in buckets.values():
        try:
            proof = {"source": "local-sidebar-custom-sections-v3", "nativeSnapshotSha256": fingerprint(native),
                     "sections": [{"sectionId": s["id"], "name": s["name"], "itemKeys": s["itemKeys"]}
                                  for s in array(bucket, "sections")]}
            _, resolved = reconcile(native, proof)
            if resolved:
                candidates.append(proof)
        except (KeyError, TypeError, ValueError):
            continue
    if len(candidates) != 1:
        raise ValueError("Need exactly one consistent local sidebar scope; refresh both reads")
    return {**snapshot, "identityEvidence": candidates[0]}


def reconcile_cloud(original, normalized):
    """Separate native sidebar storage keys from a verified durable routing host."""
    proof = original.get("cloudEvidence")
    if proof is None:
        return normalized, []
    if (not isinstance(proof, dict) or proof.get("source") != "native-read-thread"
            or proof.get("nativeSnapshotSha256") != fingerprint(native_snapshot(original))):
        raise ValueError("Cloud evidence does not match this native snapshot")
    reads = array(proof, "threads")
    sidebar = normalized["sidebar"]
    rows = array(sidebar, "threads") + array(sidebar, "pinnedThreads")
    sections = array(sidebar, "sections")
    seen, resolved = set(), []
    for read in reads:
        if (not isinstance(read, dict) or not stable(read.get("id"))
                or read["id"].startswith("client-new-thread:")
                or read.get("kind") != "codex" or read.get("hostId") != "durable"):
            raise ValueError("Cloud evidence requires a successful exact codex/durable thread read")
        ident = read["id"]
        if ident in seen:
            raise ValueError("Duplicate cloud evidence identity")
        seen.add(ident)
        matches = [r for r in rows if r.get("id") == ident]
        if not matches or any(r.get("kind") != "codex" or r.get("hostId") != "durable" for r in matches):
            raise ValueError("Cloud read conflicts with the native identity or another host")
        if len({r.get("projectId") for r in matches}) != 1:
            raise ValueError("Cloud read has conflicting project membership")
        if sum(r.get("id") == ident for r in sidebar["threads"]) > 1:
            raise ValueError("Duplicate native cloud identity")
        key = "codex:thread:durable:" + ident
        allowed = {key, "codex:thread:local:" + ident}
        places = [(s["sectionId"], k) for s in sections for k in s["itemKeys"]
                  if k.startswith("codex:thread:") and k.endswith(":" + ident)]
        if len(places) != 1 or places[0][1] not in allowed:
            raise ValueError("Cloud identity needs one unambiguous native section key")
        sid, native_key = places[0]
        resolved.append({"key": key, "nativeItemKey": native_key, "sectionId": sid})
    result = json.loads(json.dumps(normalized))
    replacements = {r["nativeItemKey"]: r["key"] for r in resolved}
    for section in result["sidebar"]["sections"]:
        section["itemKeys"] = [replacements.get(k, k) for k in section["itemKeys"]]
    return result, resolved


def capture_cloud(snapshot, reads):
    """Bind agent-collected native read metadata to this snapshot; no network calls."""
    proof = {"source": "native-read-thread", "nativeSnapshotSha256": fingerprint(native_snapshot(snapshot)),
             "threads": [{k: r.get(k) for k in ("id", "kind", "hostId")} for r in array(reads, "threads")]}
    result = {**snapshot, "cloudEvidence": proof}
    normalized, _ = reconcile(result)
    reconcile_cloud(result, normalized)
    return result


def availability(values, field):
    result = set()
    for value in values:
        ident = value if isinstance(value, str) else value.get(field) if isinstance(value, dict) else None
        if not stable(ident):
            return {"*"}  # Unknown availability representation: fail closed.
        result.add(ident)
    return result


def array(obj, field):
    if not isinstance(obj, dict) or not isinstance(obj.get(field), list):
        raise ValueError(f"Expected an explicit {field} array; check the live native schema")
    return obj[field]


def index(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot must be an object")
    original = snapshot
    snapshot, resolved = reconcile(snapshot)
    snapshot, cloud_resolved = reconcile_cloud(original, snapshot)
    project_rows = array(snapshot.get("projects"), "projects")
    sidebar = snapshot.get("sidebar")
    recent = array(sidebar, "threads")
    pins = array(sidebar, "pinnedThreads")
    sections = array(sidebar, "sections")
    hosts = availability(array(sidebar, "unavailableHosts"), "hostId")
    sources = availability(array(sidebar, "unavailableSources"), "source")
    if not isinstance(sidebar.get("sidebarPreferences"), dict):
        raise ValueError("Expected sidebarPreferences object")
    section_map, locations, names = {}, defaultdict(list), defaultdict(list)
    for section in sections:
        if not isinstance(section, dict) or not stable(section.get("sectionId")) or not stable(section.get("name")):
            raise ValueError("Section must have a stable sectionId and name")
        sid = section["sectionId"]
        if sid in section_map:
            raise ValueError("Duplicate sectionId")
        section_map[sid] = section
        if sid not in DEFAULTS and sid != "pinned":
            names[section["name"]].append(sid)
        for key in array(section, "itemKeys"):
            if not stable(key):
                raise ValueError("Invalid section itemKey")
            locations[key].append(sid)
    projects, chats, invalid = {}, {}, []
    duplicates = set()
    ids = Counter(r.get("projectId") for r in project_rows if isinstance(r, dict) and stable(r.get("projectId")))
    for position, row in enumerate(project_rows):
        if not isinstance(row, dict):
            raise ValueError("Project row must be an object")
        pid = row.get("projectId")
        if not stable(pid):
            invalid.append({"entity": "project", "position": position, "reason": "missing_stable_id"})
            continue
        # For unknown kinds require explicit native section evidence of the namespace.
        candidates = [f"{source}:project:{pid}" for source in ("codex", "chatgpt")]
        if row.get("projectKind") == "chatgpt":
            key = candidates[1]
        elif row.get("projectKind") in {"local", "remote"}:
            key = candidates[0]
        else:
            present = [k for k in candidates if k in locations]
            key = present[0] if len(present) == 1 else None
        if key is None:
            invalid.append({"entity": "project", "id": pid, "reason": "unknown_project_namespace"})
            continue
        projects[key] = row
        if ids[pid] != 1:
            duplicates.add(key)
    for position, row in enumerate(recent + pins):
        if not isinstance(row, dict):
            raise ValueError("Chat row must be an object")
        key = chat_key(row)
        if key is None:
            invalid.append({"entity": "chat", "position": position, "reason": "unroutable_identity"})
            continue
        if key in chats:
            fields = ("id", "kind", "hostId", "projectId")
            if any(chats[key].get(f) != row.get(f) for f in fields):
                duplicates.add(key)
        else:
            chats[key] = row
    recent_counts = Counter(chat_key(r) for r in recent)
    duplicates.update(k for k, count in recent_counts.items() if k and count > 1)
    pin_keys = [chat_key(r) for r in pins]
    duplicates.update(k for k, count in Counter(pin_keys).items() if k and count > 1)
    return dict(projects=projects, chats=chats, sections=section_map, locations=locations,
                names=names, pins=pin_keys, invalid=invalid, duplicates=duplicates,
                hosts=hosts, sources=sources, preferences=sidebar["sidebarPreferences"], recent=recent,
                resolved=resolved, cloud_resolved=cloud_resolved,
                alias_hosts={alias_host(k) for k in locations if alias_host(k)})


def blocked(source, host, data):
    return "*" in data["sources"] or source in data["sources"] or (
        source == "codex" and ("*" in data["hosts"] or host in data["hosts"]))


def build_plan(snapshot, language="zh"):
    labels = LABELS[language]
    data = index(snapshot)
    cloud_keys = {r["key"] for r in data["cloud_resolved"]}
    cloud_label = CLOUD_LABELS[language]
    cloud_needed = bool(data["names"].get(cloud_label)) or any(
        key not in data["pins"] and not data["chats"][key].get("projectId")
        and data["locations"].get(key, [None])[0] in DEFAULTS
        and not blocked("codex", "durable", data) for key in cloud_keys)
    remote = {}
    for key, row in data["projects"].items():
        host = row.get("hostId")
        if (key not in data["duplicates"] and row.get("projectKind") in {"local", "remote"}
                and stable(host) and host != "local" and host not in NON_HOSTS):
            remote[host] = row.get("hostDisplayName") or host
    remote_labels = {}
    for host in sorted(remote):
        prefix = "远程" if language == "zh" else "Remote"
        name = f"{prefix} {remote[host]} [{host}]"
        remote_labels[host] = [name + (" · 项目" if language == "zh" else " · Projects"),
                               name + (" · 聊天" if language == "zh" else " · Chats")]
    target_names = labels[:4] + ([cloud_label] if cloud_needed else []) + [name for pair in remote_labels.values() for name in pair] + labels[4:]
    targets = [{"name": name, "sectionId": data["names"][name][0] if len(data["names"][name]) == 1 else None,
                "state": "ambiguous" if len(data["names"][name]) > 1 else "reuse" if data["names"][name] else "create"}
               for name in target_names]
    moves, protected, skipped = [], [], list(data["invalid"])

    def consider(key, row, entity):
        places = data["locations"].get(key, [])
        item = {"key": key, "entity": entity}
        if key in data["pins"] or "pinned" in places:
            protected.append({**item, "reason": "pinned"})
            return
        if entity == "chat" and row.get("projectId"):
            protected.append({**item, "reason": "project_member"})
            return
        if key in data["duplicates"]:
            skipped.append({**item, "reason": "duplicate_or_conflicting_identity"})
            return
        if entity == "chat" and row.get("hostId") == "durable" and key not in cloud_keys:
            skipped.append({**item, "reason": "unverified_cloud_identity"})
            return
        if len(places) != 1:
            skipped.append({**item, "reason": "ambiguous_or_missing_section"})
            return
        if places[0] not in DEFAULTS:
            protected.append({**item, "reason": "already_filed"})
            return
        if entity == "chat" and row.get("kind") == "codex" and row.get("hostId") in data["alias_hosts"]:
            skipped.append({**item, "reason": "unresolved_client_alias"})
            return
        source = key.split(":", 1)[0]
        host = row.get("hostId")
        if blocked(source, host, data):
            skipped.append({**item, "reason": "source_or_host_unavailable"})
            return
        kind = row.get("projectKind") if entity == "project" else row.get("kind")
        offset = 0 if entity == "project" else 2
        if source == "chatgpt" and kind == "chatgpt":
            target = labels[offset + 1]
        elif entity == "chat" and key in cloud_keys:
            target = cloud_label
        elif source == "codex" and kind in {"local", "remote", "codex"} and host == "local":
            target = labels[offset]
        elif source == "codex" and host in remote_labels and kind in {"local", "remote", "codex"}:
            target = remote_labels[host][0 if entity == "project" else 1]
        elif entity == "project":
            target = labels[4]
        else:
            skipped.append({**item, "reason": "unverified_host"})
            return
        if len(data["names"][target]) > 1:
            skipped.append({**item, "reason": "duplicate_target_name", "targetName": target})
            return
        move = {**item, "fromSection": places[0], "targetName": target}
        if entity == "project":
            move["projectId"] = row["projectId"]
        else:
            move.update(threadId=row["id"], source=source)
            if source == "codex":
                move["hostId"] = host
        moves.append(move)

    for key, row in data["projects"].items():
        consider(key, row, "project")
    # Native recent array is newest first. Moves prepend, so apply oldest first.
    visited = set()
    for row in list(reversed(data["recent"])) + snapshot["sidebar"]["pinnedThreads"]:
        key = chat_key(row)
        if key and key not in visited:
            visited.add(key)
            consider(key, row, "chat")
    known = set(data["chats"])
    unlisted = [k for k in data["locations"] if (k.startswith("codex:thread:") or k.startswith("chatgpt:conversation:")) and k not in known]
    return {
        "schemaVersion": 3, "language": language, "snapshotSha256": fingerprint(snapshot),
        "identityReconciliation": {"resolvedMemberships": data["resolved"], "unresolvedAliasHosts": sorted(data["alias_hosts"])},
        "cloudReconciliation": data["cloud_resolved"],
        "targets": targets, "moves": moves, "protected": protected, "skipped": skipped,
        "sorting": {"chats": "updated_at"},
        "coverage": {"complete": False, "totalHistory": None, "listedProjects": len(data["projects"]),
                     "listedChats": len(data["chats"]), "visible_unlisted_chat_keys": len(unlisted),
                     "unavailableHosts": sorted(data["hosts"]), "unavailableSources": sorted(data["sources"]),
                     "note": "Recent snapshot only; older history, visible UI, opening, and collapse are unverified."},
    }


def verify(before, after, plan):
    if plan != build_plan(before, plan.get("language", "zh")):
        raise ValueError("Plan does not match the before snapshot; regenerate it")
    old, new = index(before), index(after)
    errors, unknown, confirmed = [], [], []
    if old["pins"] != new["pins"] or old["sections"].get("pinned", {}).get("itemKeys") != new["sections"].get("pinned", {}).get("itemKeys"):
        errors.append("pinned_order_or_membership_changed")
    if "pinned" in old["sections"] and ("pinned" not in new["sections"] or list(old["sections"]).index("pinned") != list(new["sections"]).index("pinned")):
        errors.append("pinned_section_position_changed")
    if plan["skipped"]:
        unknown.append("plan_contains_skipped_items")
    if old["alias_hosts"] or new["alias_hosts"]:
        unknown.append("unresolved_client_alias")
    if {r["key"] for r in old["cloud_resolved"]} - {r["key"] for r in new["cloud_resolved"]}:
        unknown.append("cloud_evidence_not_refreshed")
    if old["resolved"] and not new["resolved"]:
        old_resolved = {r["key"] for r in old["resolved"]}
        # A client can graduate to canonical IDs; no proof is needed once native IDs agree.
        if any(key not in new["locations"] for key in old_resolved):
            unknown.append("identity_evidence_not_refreshed")
    for entity, fields in (("projects", ("projectId", "projectKind", "hostId", "path")),
                            ("chats", ("id", "kind", "hostId", "projectId", "pinnedIndex"))):
        for key, row in old[entity].items():
            if key not in new[entity]:
                unknown.append(f"record_missing:{key}")
            elif any(row.get(field) != new[entity][key].get(field) for field in fields):
                errors.append(f"metadata_changed:{key}")
        for key in new[entity].keys() - old[entity].keys():
            unknown.append(f"new_record_outside_plan:{key}")
    for field in ("invalid", "duplicates"):
        if old[field] or new[field]:
            unknown.append(f"unresolved_{field}")
    if new["hosts"] or new["sources"]:
        unknown.append("after_snapshot_has_unavailable_sources_or_hosts")
    if any(len(places) > 1 for places in new["locations"].values()):
        unknown.append("duplicate_after_section_membership")
    moved = {m["key"] for m in plan["moves"]}
    for key, sections in old["locations"].items():
        if key not in moved and sections != new["locations"].get(key, []):
            errors.append(f"unplanned_placement_change:{key}")
    for sid, section in old["sections"].items():
        if sid not in new["sections"] or new["sections"][sid]["name"] != section["name"]:
            errors.append(f"existing_section_missing_or_renamed:{sid}")
    for move in plan["moves"]:
        ids = new["names"].get(move["targetName"], [])
        if len(ids) == 1 and new["locations"].get(move["key"]) == ids:
            confirmed.append(move["key"])
        else:
            errors.append(f"destination_not_verified:{move['key']}")
    # Changes outside chats recency sorting are never requested by this helper.
    prefs_before, prefs_after = json.loads(json.dumps(old["preferences"])), json.loads(json.dumps(new["preferences"]))
    for prefs in (prefs_before, prefs_after):
        prefs.setdefault("sorting", {}).pop("chats", None)
    if prefs_before != prefs_after:
        errors.append("unrequested_sidebar_preference_change")
    if new["preferences"].get("sorting", {}).get("chats") != "updated_at":
        unknown.append("recency_sorting_not_verified")
    target_names = {t["name"] for t in plan["targets"]}
    def unrelated(data):
        return [sid for sid, s in data["sections"].items() if sid not in DEFAULTS and sid != "pinned" and s["name"] not in target_names]
    if unrelated(old) != unrelated(new):
        errors.append("unrelated_section_order_changed")
    desired = [t["name"] for t in plan["targets"] if t["state"] != "ambiguous"]
    actual = [s["name"] for sid, s in new["sections"].items() if sid not in DEFAULTS and sid != "pinned" and s["name"] in desired]
    if actual != desired:
        unknown.append("managed_section_order_or_creation_not_verified")
    blocking_unknown = [item for item in unknown if item != "plan_contains_skipped_items"]
    return {"schemaVersion": 3, "status": "failed" if errors else "incomplete" if unknown else "metadata_verified",
            "operationChecksPassed": not errors and not blocking_unknown,
            "excludedItemCount": len(plan["skipped"]),
            "identityReconciliation": {"before": old["resolved"], "after": new["resolved"]},
            "cloudReconciliation": {"before": old["cloud_resolved"], "after": new["cloud_resolved"]},
            "confirmedMoves": confirmed, "errors": errors, "unverified": unknown,
            "historyComplete": False, "uiPlacement": "unverified", "collapse": "unverified", "opening": "unverified"}


def refresh_observation(snapshot):
    """Project native list metadata only; absence is never deletion evidence."""
    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot must be an object")
    sidebar = snapshot.get("sidebar")
    sources = availability(array(sidebar, "unavailableSources"), "source")
    available = not sources.intersection({"chatgpt", "*"})
    present = set()
    for field in ("threads", "pinnedThreads"):
        seen = set()
        for row in array(sidebar, field):
            if not isinstance(row, dict) or not stable(row.get("id")) or not stable(row.get("kind")):
                raise ValueError("Invalid native chat identity")
            if row["kind"] != "chatgpt":
                continue
            key = chat_key(row)
            if key in seen:
                raise ValueError("Duplicate native ChatGPT row")
            seen.add(key)
            present.add(key)
    sections, memberships = set(), set()
    for section in array(sidebar, "sections"):
        if not isinstance(section, dict) or not stable(section.get("sectionId")):
            raise ValueError("Invalid native section identity")
        sid = section["sectionId"]
        if sid in sections:
            raise ValueError("Duplicate native section")
        sections.add(sid)
        seen = set()
        for key in array(section, "itemKeys"):
            if not stable(key) or key in seen:
                raise ValueError("Invalid or duplicate native section key")
            seen.add(key)
            if key.startswith("chatgpt:conversation:"):
                if not stable(key.removeprefix("chatgpt:conversation:")):
                    raise ValueError("Empty ChatGPT conversation identity")
                memberships.add((sid, key))
    return {"sourceAvailable": available, "listedKeys": sorted(present),
            "memberships": [list(pair) for pair in sorted(memberships)]}


def refresh_check(snapshot, previous=None):
    current = refresh_observation(snapshot)
    prior = refresh_observation(previous) if previous is not None else None
    listed = set(current["listedKeys"])
    referenced = {key for _, key in current["memberships"]}
    unlisted = sorted(referenced - listed)
    comparable = prior is not None and prior["sourceAvailable"] and current["sourceAvailable"]
    old_memberships = {tuple(pair) for pair in prior["memberships"]} if comparable else set()
    current_memberships = {tuple(pair) for pair in current["memberships"]}
    old_unlisted = ({key for _, key in prior["memberships"]} - set(prior["listedKeys"])) if comparable else set()
    return {"schemaVersion": 1, "mode": "refresh_check",
            "status": "observed" if current["sourceAvailable"] else "source_unavailable",
            "observation": current,
            "changed": current != prior if prior is not None else None,
            "comparisonAvailable": comparable,
            "listedChatCount": len(listed), "referencedChatCount": len(referenced),
            "unlistedReferences": unlisted if current["sourceAvailable"] else [],
            "newUnlistedReferences": sorted(set(unlisted) - old_unlisted) if comparable else [],
            "removedReferences": [list(pair) for pair in sorted(old_memberships - current_memberships)],
            "actions": [], "confirmedDeletions": [],
            "forcedRefresh": "unavailable", "deletionSync": "unsupported",
            "serverFreshness": "unverified", "historyComplete": False,
            "notice": "List absence, missing reads, and removed memberships do not prove deletion. Native caching may apply; no application state was changed."}


RULE_VERSION = "source-protection-1"
CAPABILITY_VERSION = "native-v1"
CATEGORIES = ["local.projects", "chatgpt.projects", "local.chats", "chatgpt.chats", "unconfirmed"]
TOOL_FIELDS = {
    "list_threads": ["limit"], "list_projects": [],
    "create_sidebar_section": ["name"],
    "move_project_to_sidebar_section": ["projectId", "sectionId"],
    "move_thread_to_sidebar_section": ["threadId", "source", "hostId", "sectionId"],
}


def compatible_tool(spec, fields, reasons):
    """Explicit native-v1 input contract; never guess renamed routing arguments."""
    if isinstance(spec, list):
        reasons.append("deprecated:parameter_list")
        return all(isinstance(v, str) for v in spec) and set(fields).issubset(spec)
    if not isinstance(spec, dict) or set(spec) - {"inputSchema", "parameters"}:
        return False
    if "parameters" in spec:
        if "inputSchema" in spec:
            return False
        reasons.append("deprecated:parameters")
    schema = spec.get("inputSchema", spec.get("parameters"))
    if not isinstance(schema, dict) or set(schema) - {"type", "properties", "required", "additionalProperties"}:
        return False
    props, required = schema.get("properties"), schema.get("required", [])
    if schema.get("type") != "object" or not isinstance(props, dict) or not isinstance(required, list):
        return False
    if not all(isinstance(v, str) for v in required) or set(required) - set(fields):
        return False
    return all(props.get(key) == {"type": "integer" if key == "limit" else "string"} for key in fields)


def diagnose(snapshot):
    """Inspect supplied metadata only; unknown versions are never inferred."""
    reasons, blocking = [], []
    caps = snapshot.get("capabilities") if isinstance(snapshot, dict) else None
    if caps is None:
        reasons.append("legacy_snapshot")
    elif not isinstance(caps, dict):
        blocking.append("unknown_adapter")
        caps = {}
    else:
        if caps.get("adapter") != CAPABILITY_VERSION:
            blocking.append("unknown_adapter")
        defaults = caps.get("defaultSectionIds")
        if not isinstance(defaults, list) or not all(stable(v) for v in defaults) or set(defaults) != DEFAULTS:
            blocking.append("unknown_default_sections")
        tools = caps.get("tools", {})
        if not isinstance(tools, dict):
            tools = {}
        for name, fields in TOOL_FIELDS.items():
            if name not in tools:
                blocking.append("missing_tool:" + name)
            elif not compatible_tool(tools[name], fields, reasons):
                blocking.append("tool_schema_mismatch:" + name)
    try:
        data = index(snapshot)
        rows = data["recent"] + list(data["chats"].values())
        if any(r.get("kind") == "codex" and not stable(r.get("hostId")) for r in rows) or any(
                r.get("projectKind") in {"local", "remote"} and not stable(r.get("hostId")) for r in data["projects"].values()):
            blocking.append("missing_hostId")
        if snapshot.get("identityEvidence", {}).get("source") == "local-sidebar-custom-sections-v3":
            reasons.append("deprecated:local-sidebar-custom-sections-v3.id")
    except (ValueError, TypeError, KeyError):
        blocking.append("schema_mismatch")
    return {"schemaVersion": 1, "adapter": CAPABILITY_VERSION,
            "clientVersion": (caps or {}).get("clientVersion", "unknown"),
            "canPlanMoves": not blocking, "reasons": reasons + blocking,
            "status": "degraded" if blocking else "legacy" if caps is None else "ready"}


def parse_config(config):
    config = {} if config is None else config
    allowed = {"version", "sources", "hosts", "excludeIds", "labels", "createEmptyGroups", "sort"}
    if not isinstance(config, dict) or set(config) - allowed or config.get("version", 1) != 1:
        raise ValueError("Unsupported config fields/version")
    for field in ("sources", "hosts", "excludeIds"):
        if field in config and (not isinstance(config[field], list) or not all(stable(v) for v in config[field])):
            raise ValueError("Config scope must be explicit string arrays")
    if set(config.get("sources", [])) - {"codex", "chatgpt"}:
        raise ValueError("Unknown source")
    if type(config.get("createEmptyGroups", False)) is not bool:
        raise ValueError("createEmptyGroups must be boolean")
    if config.get("sort", "updated_at") not in {"updated_at", "manual"}:
        raise ValueError("Unsupported sorting")
    labels = config.get("labels", {})
    if not isinstance(labels, dict) or any(k not in CATEGORIES and k != "codex.cloud.chats" and not re.fullmatch(r"remote\.[^.]+\.(projects|chats)", k) for k in labels):
        raise ValueError("Unknown category label")
    if not all(stable(v) for v in labels.values()) or len(set(labels.values())) != len(labels):
        raise ValueError("Labels must be nonempty and distinct")
    return json.loads(json.dumps(config))


def category_for(name, language):
    if name in LABELS[language]:
        return CATEGORIES[LABELS[language].index(name)]
    if name == CLOUD_LABELS[language]:
        return "codex.cloud.chats"
    match = re.search(r"\[([^]]+)\] · (.+)$", name)
    if not match:
        raise ValueError("Unrecognized category")
    return "remote." + match.group(1) + (".projects" if match.group(2) in {"项目", "Projects"} else ".chats")


def safe_plan(snapshot, language="zh", mapping=None, config=None, budget=None):
    """v4 preview only. Mappings are trusted confirmed IDs, never inferred translations."""
    config = parse_config(config)
    if language not in LABELS:
        raise ValueError("Unknown language")
    mapping = {} if mapping is None else mapping
    if not isinstance(mapping, dict) or not all(stable(k) and stable(v) for k, v in mapping.items()):
        raise ValueError("Invalid confirmed category mapping")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("A section cannot represent multiple categories")
    if budget is not None and (type(budget) is not int or budget < 0):
        raise ValueError("Budget must be a nonnegative integer")
    doctor = diagnose(snapshot)
    options = {"mapping": mapping, "config": config, "budget": budget}
    base = build_plan(snapshot, language) if "schema_mismatch" not in doctor["reasons"] else {
        "targets": [], "moves": [], "protected": [], "skipped": [],
        "coverage": {"complete": False, "totalHistory": None}}
    data = index(snapshot) if "schema_mismatch" not in doctor["reasons"] else None
    targets, moves, skipped = [], [], list(base["skipped"])
    for target in base["targets"]:
        category = category_for(target["name"], language)
        display = config.get("labels", {}).get(category, target["name"])
        sid = mapping.get(category)
        if sid:
            state = "reuse" if sid in data["sections"] and sid not in DEFAULTS | {"pinned"} else "missing"
        else:
            ids = data["names"].get(display, [])
            sid = ids[0] if len(ids) == 1 else None
            state = "ambiguous" if len(ids) > 1 else "reuse" if ids else "create"
        targets.append({"name": data["sections"][sid]["name"] if state == "reuse" else display,
                        "displayLabel": display, "category": category, "sectionId": sid,
                        "state": state, "operationId": fingerprint([RULE_VERSION, fingerprint(snapshot), "create", category])})
    for m in base["moves"]:
        category = category_for(m["targetName"], language)
        target = next(t for t in targets if t["category"] == category)
        source = m["key"].split(":", 1)[0]
        excluded = (m.get("threadId", m.get("projectId")) in config.get("excludeIds", [])
                    or m["key"] in config.get("excludeIds", [])
                    or ("sources" in config and source not in config["sources"])
                    or ("hosts" in config and source == "codex" and m.get("hostId", data["projects"].get(m["key"], {}).get("hostId")) not in config["hosts"]))
        reason = "config_excluded" if excluded else "capability_degraded" if not doctor["canPlanMoves"] else "mapped_section_missing" if target["state"] == "missing" else "duplicate_target_name" if target["state"] == "ambiguous" else None
        if reason:
            skipped.append({"key": m["key"], "reason": reason})
        else:
            moves.append({**m, "targetName": target["name"], "category": category,
                          "expectedTargetId": target["sectionId"],
                          "operationId": fingerprint([RULE_VERSION, fingerprint(snapshot), "move", m["key"], m["fromSection"], category, target["sectionId"]])})
    needed = {m["category"] for m in moves}
    targets = [t for t in targets if t["state"] in {"reuse", "ambiguous", "missing"} or t["category"] in needed or config.get("createEmptyGroups", False)]
    if not doctor["canPlanMoves"]:
        targets = [t for t in targets if t["state"] != "create"]
    if len({t["name"] for t in targets}) != len(targets):
        raise ValueError("Labels collide across categories")
    cloud_count = sum(r.get("kind") == "codex" and r.get("hostId") == "durable" for r in snapshot.get("sidebar", {}).get("threads", []))
    estimate = 4 + cloud_count * 2 + len(moves) + sum(t["state"] == "create" for t in targets) + 2
    previous_sort = data["preferences"].get("sorting", {}).get("chats") if data else None
    sort = config.get("sort", "updated_at")
    return {**base, "schemaVersion": 4, "ruleVersion": RULE_VERSION,
            "capabilityVersion": CAPABILITY_VERSION, "language": language, "snapshotSha256": fingerprint(snapshot),
            "options": options, "doctor": doctor, "mappingMode": "confirmed_ids" if mapping else "legacy_exact_label",
            "targets": targets, "moves": moves, "skipped": skipped,
            "sorting": {"chats": sort}, "sortingPreview": {"before": previous_sort, "after": sort, "requiresApproval": previous_sort != sort},
            "budget": {"estimatedToolCalls": estimate, "cloudVerificationCalls": cloud_count * 2,
                       "limit": budget, "sufficient": budget is None or budget >= estimate},
            "coverage": {**base["coverage"], "proven": [], "protected": base["protected"],
                         "skipped": skipped, "unverified": [{"key": m["key"], "reason": "pending_readback"} for m in moves],
                         "scope": "recent_snapshot_only", "complete": False}}


def validate_safe_plan(before, plan):
    if plan.get("schemaVersion") != 4 or plan != safe_plan(before, plan.get("language", "zh"), **plan.get("options", {})):
        raise ValueError("Plan does not match the before snapshot; regenerate it")


def reconcile_receipt(before, current, plan, journal=None):
    """Re-read after timeout; never repeat unknown writes or trust names as returned IDs."""
    validate_safe_plan(before, plan)
    journal = journal or {"schemaVersion": 2, "operations": []}
    if journal.get("schemaVersion") not in {1, 2}:
        raise ValueError("Unknown journal schema")
    entries = array(journal, "operations")
    if any(r.get("state") not in {"pending", "confirmed", "unknown"} for r in entries):
        raise ValueError("Unknown operation state")
    if len({r.get("operationId") for r in entries}) != len(entries):
        raise ValueError("Duplicate journal operation")
    allowed_ids = {r["operationId"] for r in plan["targets"] + plan["moves"]}
    if any(r.get("operationId") not in allowed_ids for r in entries):
        raise ValueError("Journal contains an operation outside this plan")
    ledger = {r["operationId"]: r for r in entries}
    new, old = index(current), index(before)
    rows, destinations, retryable = [], {}, []
    for target in plan["targets"]:
        sid = target["sectionId"] if target["state"] == "reuse" else None
        entry = ledger.get(target["operationId"], {})
        if target["state"] == "create" and entry.get("state") == "confirmed":
            candidate = entry.get("sectionId")
            if candidate not in old["sections"] and candidate in new["sections"] and new["sections"][candidate]["name"] == target["name"]:
                sid = candidate
        if sid in new["sections"] and sid not in DEFAULTS | {"pinned"}:
            destinations[target["category"]] = sid
            state, reason = "confirmed", "id_readback"
        elif target["state"] == "create" and not entry and not new["names"].get(target["name"]):
            state, reason = "pending", "not_attempted"
            retryable.append(target["operationId"])
        else:
            state, reason = "unknown", "creation_or_target_unverified"
        rows.append({"operationId": target["operationId"], "state": state, "reason": reason, "sectionId": sid})
    # Multiple category receipts pointing at one section are not identity evidence.
    repeated = {sid for sid, count in Counter(destinations.values()).items() if count > 1}
    destinations = {k: v for k, v in destinations.items() if v not in repeated}
    confirmed = []
    for move in plan["moves"]:
        key, sid = move["key"], destinations.get(move["category"])
        places = new["locations"].get(key, [])
        row = new["chats" if move["entity"] == "chat" else "projects"].get(key)
        prior = old["chats" if move["entity"] == "chat" else "projects"].get(key)
        fields = ("id", "kind", "hostId", "projectId") if move["entity"] == "chat" else ("projectId", "projectKind", "hostId", "path")
        entry = ledger.get(move["operationId"], {})
        if key in new["pins"] or "pinned" in places or (move["entity"] == "chat" and row and row.get("projectId")):
            state, reason = "unknown", "new_protection"
        elif not row or key in new["duplicates"] or any(row.get(f) != prior.get(f) for f in fields):
            state, reason = "unknown", "identity_or_metadata_changed"
        elif (key in {r["key"] for r in old["cloud_resolved"]} and key not in {r["key"] for r in new["cloud_resolved"]}) or new["alias_hosts"] or blocked(key.split(":", 1)[0], row.get("hostId"), new):
            state, reason = "unknown", "fresh_identity_unavailable"
        elif sid and places == [sid] and entry:
            state, reason = "confirmed", "id_readback"
            confirmed.append({**move, "confirmedTargetId": sid})
        elif places != [move["fromSection"]]:
            state, reason = "unknown", "user_moved"
        elif entry:
            state, reason = "unknown", "write_outcome_unknown"
        elif move["expectedTargetId"] and not sid:
            state, reason = "unknown", "target_disappeared"
        else:
            state, reason = "pending", "not_attempted"
            if sid: retryable.append(move["operationId"])
        rows.append({"operationId": move["operationId"], "state": state, "reason": reason, "key": key, "sectionId": sid})
    # Legacy verifier still guards protected metadata, unrelated placements and preference changes.
    safety = verify(before, current, build_plan(before, plan["language"]))
    safety_errors = [e for e in safety["errors"] if not e.startswith("destination_not_verified:") and e != "unrelated_section_order_changed"]
    moved = {m["key"] for m in plan["moves"]}
    for key, places in old["locations"].items():
        error = f"unplanned_placement_change:{key}"
        if key not in moved and places != new["locations"].get(key, []) and error not in safety_errors:
            safety_errors.append(error)
    managed_ids = set(destinations.values())
    def unrelated_ids(data):
        return [sid for sid in data["sections"] if sid not in DEFAULTS | {"pinned"} and sid not in managed_ids]
    if unrelated_ids(old) != unrelated_ids(new):
        safety_errors.append("unrelated_section_order_changed")
    if new["preferences"].get("sorting", {}).get("chats") != plan["sorting"]["chats"]:
        safety_errors.append("requested_sort_not_verified")
    if not diagnose(current)["canPlanMoves"]:
        safety_errors.append("current_capability_degraded")
    actual = journal.get("actualToolCalls")
    if actual is not None and (type(actual) is not int or actual < 0):
        raise ValueError("Actual tool count must be a nonnegative integer")
    limit = plan["budget"]["limit"]
    budget_reason = None
    if limit is not None and actual is not None and actual > limit:
        budget_reason = "actual_tool_calls_exceed_budget"
    elif not plan["budget"]["sufficient"]:
        budget_reason = "estimated_tool_calls_exceed_budget"
    elif limit is not None and actual is None:
        budget_reason = "actual_tool_calls_unknown"
    sufficient = budget_reason is None
    blocking_unknown = [reason for reason in safety["unverified"] if reason not in {
        "plan_contains_skipped_items", "managed_section_order_or_creation_not_verified", "recency_sorting_not_verified"}]
    if not sufficient:
        blocking_unknown.append(budget_reason)
        confirmed = []
        rows = [{**r, "state": "unknown", "reason": budget_reason} if r["state"] == "confirmed" else r for r in rows]
    needed_categories = {m["category"] for m in plan["moves"]}
    required_targets = {t["operationId"] for t in plan["targets"]
                        if t["category"] in needed_categories or plan["options"]["config"].get("createEmptyGroups", False)}
    # Keep unrelated target diagnostics without making them prerequisites for this run.
    success = (bool(plan["moves"]) and len(confirmed) == len(plan["moves"])
               and all(r["state"] == "confirmed" for r in rows if r["operationId"] in required_targets)
               and not safety_errors and not blocking_unknown and sufficient)
    return {"schemaVersion": 2, "unverified": blocking_unknown, "planSha256": fingerprint(plan), "status": "confirmed" if success else "unverified",
            "operations": rows, "retryable": retryable if sufficient and not safety_errors else [],
            "confirmedMoves": confirmed if not safety_errors else [], "errors": safety_errors,
            "budget": {**plan["budget"], "actualToolCalls": actual, "sufficient": sufficient, "reason": budget_reason},
            "coverage": {**plan["coverage"], "proven": [m["key"] for m in confirmed] if not safety_errors else [],
                         "unverified": [r for r in rows if r["state"] != "confirmed"], "complete": False}}


def undo_plan(before, current, plan, receipt, can_move_back=False):
    validate_safe_plan(before, plan)
    if receipt.get("planSha256") != fingerprint(plan):
        raise ValueError("Receipt belongs to a different plan")
    if not can_move_back:
        return {"schemaVersion": 1, "status": "unsupported", "moves": [], "reason": "move_to_original_section_not_supported"}
    if not diagnose(current)["canPlanMoves"]:
        return {"schemaVersion": 1, "status": "unsupported", "moves": [], "reason": "current_capability_degraded"}
    new, old = index(current), index(before)
    planned = {m["operationId"]: m for m in plan["moves"]}
    moves, skipped = [], []
    for move in receipt.get("confirmedMoves", []):
        original = planned.get(move.get("operationId"))
        if not original or {k: move.get(k) for k in original} != original:
            raise ValueError("Receipt move differs from plan")
        key = move["key"]
        row = new["chats" if move["entity"] == "chat" else "projects"].get(key)
        prior = old["chats" if move["entity"] == "chat" else "projects"].get(key)
        places = new["locations"].get(key, [])
        if places == [move["fromSection"]]:
            skipped.append({"key": key, "reason": "already_undone"})
        elif (not row or row != prior or key in new["pins"] or "pinned" in places
              or key in new["duplicates"] or row.get("projectId") and move["entity"] == "chat"
              or places != [move.get("confirmedTargetId")] or move["fromSection"] not in new["sections"]):
            skipped.append({"key": key, "reason": "current_relation_or_protection_changed"})
        elif (blocked(key.split(":", 1)[0], row.get("hostId"), new) or new["alias_hosts"]
              or (row.get("kind") == "codex" and row.get("hostId") == "durable"
                  and key not in {r["key"] for r in new["cloud_resolved"]})):
            skipped.append({"key": key, "reason": "fresh_identity_unavailable"})
        else:
            moves.append({**original, "fromSection": move["confirmedTargetId"], "expectedTargetId": move["fromSection"],
                          "operationId": fingerprint(["undo", move["operationId"]])})
    return {"schemaVersion": 1, "status": "preview", "moves": moves, "skipped": skipped,
            "notice": "Limited reverse placement only; no section deletion or order restoration."}


def acceptance_report(snapshot, before=None, plan=None, receipt=None, journal=None):
    """Summarize supplied private evidence, never claim host UI/deletion acceptance."""
    doctor = diagnose(snapshot)
    host_items = ["host.group", "host.move", "host.readback", "host.undo", "host.upgrade", "host.deletion-sync", "host.ui"]
    verified, blocked = [], []
    reasons = list(doctor["reasons"])
    if not doctor["canPlanMoves"]:
        blocked = ["host.group", "host.move", "host.readback", "host.undo"]
    if all(value is not None for value in (before, plan, receipt, journal)):
        try:
            computed = reconcile_receipt(before, snapshot, plan, journal)
            if computed == receipt and computed["status"] == "confirmed" and computed["confirmedMoves"]:
                verified.append("run.metadata_readback")
            else:
                reasons.append("receipt_unverified_or_mismatch")
        except (ValueError, KeyError, TypeError):
            reasons.append("invalid_run_evidence")
    else:
        reasons.append("missing_run_evidence")
    return {"schemaVersion": 1, "status": "observed", "verified": verified,
            "unverified": [v for v in host_items if v not in blocked] + ([] if verified else ["run.metadata_readback"]),
            "blocked": blocked, "reasons": reasons, "doctor": doctor,
            "coverage": {"scope": "supplied_recent_snapshot_only", "complete": False, "accountCompletionRate": None},
            "uiVisible": False, "deletionProven": False,
            "notice": "Verified means supplied scoped metadata only. Metadata cannot prove UI visibility or deletion. Undo and upgrade require separate host acceptance; evidence provenance is the collector's responsibility."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    planner = sub.add_parser("plan", help="Generate a read-only plan")
    planner.add_argument("--input", required=True, type=Path)
    planner.add_argument("--language", choices=LABELS, default="zh")
    capture = sub.add_parser("capture-identity", help="Add read-only local membership evidence for temporary IDs")
    capture.add_argument("--input", required=True, type=Path)
    capture.add_argument("--state", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / ".codex-global-state.json")
    cloud = sub.add_parser("capture-cloud", help="Bind fresh native read_thread metadata for durable identities")
    cloud.add_argument("--input", required=True, type=Path)
    cloud.add_argument("--reads", required=True, type=Path)
    refresh = sub.add_parser("refresh-check", help="Observe ChatGPT sidebar references; never infer deletion or mutate state")
    refresh.add_argument("--input", required=True, type=Path)
    refresh.add_argument("--previous", type=Path)
    checker = sub.add_parser("verify", help="Verify observed metadata against a plan")
    for name in ("before", "after", "plan"):
        checker.add_argument("--" + name, required=True, type=Path)
    for command in (planner, checker, capture, cloud, refresh):
        command.add_argument("--output", required=True, type=Path)
    doctor_cli = sub.add_parser("doctor", help="Diagnose supplied schemas without accessing a client")
    safe_cli = sub.add_parser("safe-plan", help="Generate a v4 preview")
    for command in (doctor_cli, safe_cli):
        command.add_argument("--input", required=True, type=Path)
        command.add_argument("--output", required=True, type=Path)
    safe_cli.add_argument("--language", choices=LABELS, default="zh")
    safe_cli.add_argument("--config", type=Path)
    safe_cli.add_argument("--mapping", type=Path)
    safe_cli.add_argument("--budget", type=int)
    receipt_cli = sub.add_parser("receipt", help="Reconcile current metadata with confirmed write IDs")
    undo_cli = sub.add_parser("undo-plan", help="Preview limited confirmed reverse placements")
    for command in (receipt_cli, undo_cli):
        for name in ("before", "after", "plan", "output"):
            command.add_argument("--" + name, required=True, type=Path)
    receipt_cli.add_argument("--journal", type=Path)
    undo_cli.add_argument("--receipt", required=True, type=Path)
    undo_cli.add_argument("--can-move-back", action="store_true")
    report_cli = sub.add_parser("acceptance-report", help="Summarize supplied evidence without inferring UI or deletion")
    report_cli.add_argument("--input", required=True, type=Path)
    report_cli.add_argument("--output", required=True, type=Path)
    for name in ("before", "plan", "receipt", "journal"):
        report_cli.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8-sig"))
    try:
        if args.command in {"doctor", "safe-plan", "receipt", "undo-plan", "acceptance-report"}:
            inputs = [value for key, value in vars(args).items() if key != "output" and isinstance(value, Path)]
        elif args.command == "refresh-check":
            inputs = [args.input] + ([args.previous] if args.previous else [])
        else:
            inputs = [args.input, args.state] if args.command == "capture-identity" else [args.input, args.reads] if args.command == "capture-cloud" else [args.input] if args.command == "plan" else [args.before, args.after, args.plan]
        if args.output.resolve() in {path.resolve() for path in inputs}:
            raise ValueError("Output must not overwrite an input snapshot")
        if args.command == "acceptance-report":
            result = acceptance_report(read(args.input), **{name: read(getattr(args, name)) if getattr(args, name) else None
                                       for name in ("before", "plan", "receipt", "journal")})
        elif args.command == "doctor":
            result = diagnose(read(args.input))
        elif args.command == "safe-plan":
            result = safe_plan(read(args.input), args.language,
                               mapping=read(args.mapping) if args.mapping else None,
                               config=read(args.config) if args.config else None, budget=args.budget)
        elif args.command == "receipt":
            result = reconcile_receipt(read(args.before), read(args.after), read(args.plan), read(args.journal) if args.journal else None)
        elif args.command == "undo-plan":
            result = undo_plan(read(args.before), read(args.after), read(args.plan), read(args.receipt), args.can_move_back)
        elif args.command == "refresh-check":
            result = refresh_check(read(args.input), read(args.previous) if args.previous else None)
        elif args.command == "capture-identity":
            result = capture_identity(read(args.input), args.state)
        elif args.command == "capture-cloud":
            result = capture_cloud(read(args.input), read(args.reads))
        elif args.command == "plan":
            result = build_plan(read(args.input), args.language)
        else:
            result = verify(read(args.before), read(args.after), read(args.plan))
        # Exclusive creation avoids accidental overwrites of a previous private receipt.
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(json.dumps({"reportWritten": True, "status": result.get("status", "planned"),
                          "moves": len(result.get("moves", result.get("confirmedMoves", [])))}, ensure_ascii=False))
        return 0 if result.get("status", "planned") in {"planned", "metadata_verified", "observed", "confirmed", "ready", "legacy", "preview"} else 2
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Cannot produce report: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
