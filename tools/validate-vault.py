#!/usr/bin/env python3
"""
Validate a HomeVault vault folder against STORAGE_SCHEMA.md.

    python scripts/validate-vault.py <vault-folder> [--quiet]

Exits 0 when the vault is sound, 1 when it is not.

**This is written from the schema, not from the app.** That is the point of it.
Every other check on this project reads the app's own writes back through the
app's own code, which cannot detect a bug where HomeVault is consistently wrong
in both directions -- it would write a dangling reference and read it back
without complaint, twice, and call that agreement. A reader that has only ever
seen STORAGE_SCHEMA.md is the only independent evidence available.

So: no imports from HomeVault.Core, no shared constants, and field names typed
out from the document rather than copied from a model. If this disagrees with
the app, that is a finding, not a bug to paper over -- decide which one the
schema actually says is right.

Ships alongside STORAGE_SCHEMA.md in the public homevault_storage repository,
because anyone implementing against the format needs it more than we do.

## What it cannot see

Attachments are listed in `items/{uuid}.secret.json`, which is encrypted when
the vault is. Without the passphrase there is no way to know which attachment
files should exist, so those checks are skipped and reported as skipped rather
than passed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SUPPORTED_SCHEMA_VERSION = 1
MIN_KDF_ITERATIONS = 200_000

# A record's filename must be its id. Loose on the format -- the schema says
# "UUID", but a vault written by another tool is not wrong for using a different
# flavour, and the check that matters is that name and id agree.
STEM = re.compile(r"^[0-9a-fA-F-]{8,}$")

RECORD_DIRS = {
    "rooms": "rooms",
    "items": "items",
    "tasks": "tasks",
    "checklists": "checklists",
}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.skipped: list[str] = []
        self.notes: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def skip(self, msg: str) -> None:
        self.skipped.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def load_json(path: Path, report: Report):
    """Parsed JSON, or None with an error recorded."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        report.error(f"missing: {path.name}")
    except json.JSONDecodeError as exc:
        report.error(f"unparseable JSON: {path.name} — {exc}")
    except OSError as exc:
        report.error(f"unreadable: {path.name} — {exc}")
    return None


def read_records(vault: Path, folder: str, report: Report) -> dict[str, dict]:
    """
    Every record in one folder, keyed by id.

    A file whose stem does not match the id inside it is an error on its own:
    the app addresses records by path, so the two disagreeing means one of them
    is unreachable.
    """
    out: dict[str, dict] = {}
    directory = vault / folder
    if not directory.is_dir():
        return out

    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".secret.json"):
            continue

        record = load_json(path, report)
        if record is None:
            continue

        rid = record.get("id")
        if not rid:
            report.error(f"{folder}/{path.name}: no id field")
            continue

        if path.stem != rid:
            report.error(
                f"{folder}/{path.name}: filename does not match id {rid!r} — "
                "one of the two is unreachable")

        if rid in out:
            report.error(f"{folder}: duplicate id {rid!r}")
        out[rid] = record

    return out


def check_meta(vault: Path, report: Report) -> dict:
    meta = load_json(vault / "vault.meta.json", report)
    if meta is None:
        return {}

    version = meta.get("schemaVersion")
    if version is None:
        report.error("vault.meta.json: no schemaVersion")
    elif not isinstance(version, int):
        report.error(f"vault.meta.json: schemaVersion is {version!r}, expected an integer")
    elif version > SUPPORTED_SCHEMA_VERSION:
        report.error(
            f"vault.meta.json: schemaVersion {version} is newer than this "
            f"validator understands ({SUPPORTED_SCHEMA_VERSION})")

    if meta.get("encryptionEnabled"):
        if not meta.get("kdfSalt"):
            report.error("vault.meta.json: encryption is on but kdfSalt is null")
        iterations = meta.get("kdfIterations", 0)
        if not isinstance(iterations, int) or iterations < MIN_KDF_ITERATIONS:
            report.error(
                f"vault.meta.json: kdfIterations is {iterations!r}, below the "
                f"{MIN_KDF_ITERATIONS:,} floor — offline brute force becomes cheap")
    else:
        if meta.get("kdfSalt") is not None:
            report.warn("vault.meta.json: encryption is off but kdfSalt is set")

    return meta


def check_index(vault: Path, records: dict[str, dict[str, dict]], report: Report) -> None:
    """
    index.json against the record files it summarises.

    Both directions matter and they fail differently. An index entry with no
    file behind it is a list screen offering a record that cannot be opened; a
    file absent from the index is a record the app will never show, which is
    what "deleted" looks like from the inside.
    """
    index = load_json(vault / "index.json", report)
    if index is None:
        return

    for key, folder in RECORD_DIRS.items():
        listed = index.get(key)
        if listed is None:
            report.error(f"index.json: no {key!r} array")
            continue
        if not isinstance(listed, list):
            report.error(f"index.json: {key!r} is {type(listed).__name__}, expected a list")
            continue

        on_disk = records[folder]
        listed_ids = set()

        for entry in listed:
            eid = entry.get("id")
            if not eid:
                report.error(f"index.json {key}: entry with no id")
                continue
            listed_ids.add(eid)
            if eid not in on_disk:
                report.error(
                    f"index.json {key}: {eid} has no file at {folder}/{eid}.json")

        for rid in on_disk:
            if rid not in listed_ids:
                report.error(
                    f"{folder}/{rid}.json is absent from index.json — "
                    "the app will not show it")

    # Derived counts. Wrong ones are cosmetic, so they are warnings: the app
    # recomputes them on write and Rebuild Index repairs them.
    items = records["items"]
    for entry in index.get("rooms") or []:
        rid = entry.get("id")
        if rid is None:
            continue
        actual = sum(1 for i in items.values() if i.get("roomId") == rid)
        stated = entry.get("itemCount")
        if stated is not None and stated != actual:
            report.warn(
                f"index.json rooms: {rid} says itemCount {stated}, found {actual}")

    checklists = records["checklists"]
    for entry in index.get("checklists") or []:
        cid = entry.get("id")
        record = checklists.get(cid)
        if record is None:
            continue
        actual = len(record.get("taskIds") or [])
        stated = entry.get("taskCount")
        if stated is not None and stated != actual:
            report.warn(
                f"index.json checklists: {cid} says taskCount {stated}, found {actual}")


def check_references(records: dict[str, dict[str, dict]], report: Report) -> None:
    """
    Every id one record holds about another.

    Nothing in the app checks these. A task pointing at a deleted item is
    handled at read time by the UI, but a room id pointing at nothing simply
    makes an item disappear from the only screen that lists it.
    """
    rooms, items = records["rooms"], records["items"]
    tasks, checklists = records["tasks"], records["checklists"]

    for iid, item in items.items():
        room_id = item.get("roomId")
        if room_id is not None and room_id not in rooms:
            report.error(f"items/{iid}.json: roomId {room_id} does not exist")

    for tid, task in tasks.items():
        linked = task.get("linkedItemId")
        if linked is not None and linked not in items:
            report.error(f"tasks/{tid}.json: linkedItemId {linked} does not exist")

        checklist_id = task.get("checklistId")
        if checklist_id is not None and checklist_id not in checklists:
            report.error(f"tasks/{tid}.json: checklistId {checklist_id} does not exist")

    for cid, checklist in checklists.items():
        for tid in checklist.get("taskIds") or []:
            if tid not in tasks:
                report.error(f"checklists/{cid}.json: taskIds names {tid}, which does not exist")
            elif tasks[tid].get("checklistId") != cid:
                report.warn(
                    f"checklists/{cid}.json claims task {tid}, but that task's "
                    f"checklistId is {tasks[tid].get('checklistId')!r} — the link is one-way")


def check_secrets_and_attachments(
    vault: Path, records: dict[str, dict[str, dict]], encrypted: bool, report: Report
) -> None:
    items = records["items"]

    for path in sorted((vault / "items").glob("*.secret.json")):
        item_id = path.name[: -len(".secret.json")]
        if item_id not in items:
            report.error(f"items/{path.name}: no item {item_id} to own it")

    # An item claiming secrets with no sidecar loses whatever was in it.
    for iid, item in items.items():
        if item.get("hasSecrets") and not (vault / "items" / f"{iid}.secret.json").exists():
            report.error(f"items/{iid}.json: hasSecrets is true but no sidecar exists")

    attachments_dir = vault / "attachments"
    on_disk = {p.name for p in attachments_dir.glob("*") if p.is_file()} \
        if attachments_dir.is_dir() else set()

    if encrypted:
        report.skip(
            f"attachment cross-check: filenames live in the encrypted sidecars "
            f"({len(on_disk)} file(s) on disk, unverifiable without the passphrase)")
        return

    referenced: set[str] = set()
    for path in sorted((vault / "items").glob("*.secret.json")):
        secrets = load_json(path, report)
        if secrets is None:
            continue
        for attachment in secrets.get("attachments") or []:
            filename = attachment.get("filename")
            if not filename:
                report.warn(f"items/{path.name}: an attachment has no filename")
                continue
            referenced.add(filename)
            if filename not in on_disk:
                report.error(
                    f"items/{path.name}: attachment {filename!r} is referenced "
                    "but not present in attachments/")

    for orphan in sorted(on_disk - referenced):
        report.warn(f"attachments/{orphan} is not referenced by any item")


def check_trash(vault: Path, records: dict[str, dict[str, dict]], report: Report) -> None:
    """
    Trash is a parallel tree, and its records must NOT be in the index — that
    absence is exactly what makes list screens correct for free.
    """
    trash = vault / "trash"
    if not trash.is_dir():
        return

    manifest = trash / "manifest.json"
    if not manifest.exists():
        report.warn("trash/ exists but has no manifest.json")
        return

    entries = load_json(manifest, report)
    if entries is None:
        return

    live_ids = {rid for folder in records.values() for rid in folder}
    rows = entries if isinstance(entries, list) else entries.get("entries") or []

    for row in rows:
        rid = row.get("id") if isinstance(row, dict) else None
        if rid and rid in live_ids:
            report.error(
                f"trash/manifest.json: {rid} is listed as deleted but is also a live record")

    report.note(f"trash: {len(rows)} record(s) awaiting purge or restore")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("vault", type=Path, help="the vault folder")
    parser.add_argument("--quiet", action="store_true", help="only print problems")
    args = parser.parse_args()

    vault: Path = args.vault
    if not vault.is_dir():
        print(f"not a directory: {vault}", file=sys.stderr)
        return 1

    report = Report()

    meta = check_meta(vault, report)
    records = {folder: read_records(vault, folder, report)
               for folder in RECORD_DIRS.values()}

    check_index(vault, records, report)
    check_references(records, report)
    check_secrets_and_attachments(
        vault, records, bool(meta.get("encryptionEnabled")), report)
    check_trash(vault, records, report)

    if not args.quiet:
        counts = ", ".join(f"{len(records[f])} {k}" for k, f in RECORD_DIRS.items())
        print(f"{vault}")
        print(f"  schema v{meta.get('schemaVersion', '?')}, "
              f"encryption {'on' if meta.get('encryptionEnabled') else 'off'}")
        print(f"  {counts}")
        for note in report.notes:
            print(f"  {note}")
        print()

    for msg in report.skipped:
        print(f"  SKIP  {msg}")
    for msg in report.warnings:
        print(f"  WARN  {msg}")
    for msg in report.errors:
        print(f"  ERROR {msg}")

    if report.errors:
        print(f"\n{len(report.errors)} error(s), {len(report.warnings)} warning(s) — vault is not sound")
        return 1

    print(f"\nvault is sound"
          + (f" ({len(report.warnings)} warning(s))" if report.warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
