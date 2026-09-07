# HomeVault storage format

A HomeVault vault is a folder of UTF-8 JSON files. No database, no server, no
API. If you can read a folder, you can read the vault.

This repository is the specification and the tools to work with it. It exists so
that HomeVault is not the only thing that can read a HomeVault vault — including
after HomeVault stops existing.

| | |
|---|---|
| [`STORAGE_SCHEMA.md`](STORAGE_SCHEMA.md) | The authoritative format. Every file, every field. |
| [`DISPLAY_CONVENTIONS.md`](DISPLAY_CONVENTIONS.md) | How dates, warranty states and due dates are meant to read. |
| [`tools/validate-vault.py`](tools/validate-vault.py) | Checks a vault against the schema. No dependencies. |
| [`viewer.html`](viewer.html) | A standalone reader. One file, opens locally, uploads nothing. |
| [`demo-vault/`](demo-vault/) | A complete example vault to read, validate and experiment on. |

## Try it

```bash
python tools/validate-vault.py demo-vault
```

```
demo-vault
  schema v1, encryption off
  5 rooms, 10 items, 7 tasks, 2 checklists

vault is sound
```

Point it at your own vault the same way. It reports structural problems —
records missing from the index, an index entry with no file behind it, a task
linked to an item that no longer exists, attachments nothing references, and
files a sync client forked.

## Why the validator does not import the app

It shares no code with HomeVault, deliberately. Field names are typed out from
`STORAGE_SCHEMA.md` rather than copied from the app's models.

Every other check on the app reads its own writes back through its own code,
which cannot detect a bug where it is consistently wrong in both directions — it
writes a broken reference, reads it back without complaint, and calls that
agreement. The first time this validator was pointed at a real vault it found a
checklist claiming eight tasks while all eight tasks reported belonging to no
checklist. The app had written one half of the link and read the same half back,
so from the inside everything looked correct. The user found out because their
phone sent eight notifications where one was intended.

If this tool and the app ever disagree, that is a finding. The schema is the
authority, not either implementation.

## What you can do with a vault that is just a folder

Because there is no API to be granted access to, the vault is open to anything
you already own: a script, a spreadsheet, a backup tool, another app, a language
model you point at the folder.

That last one is not a HomeVault feature and never will be. HomeVault sends your
data nowhere. What it does is decline to stand between you and your own records,
so that handing them to something else is your decision to make rather than ours
to permit.

**If you do point an agent at a vault, give it read access first.** There is no
permissions model here, no audit trail and no undo beyond the app's trash and
whatever version history your cloud provider keeps. The openness that lets a
tool repair your vault lets it damage the vault just as easily.

## Encryption

The sensitive tier — serial numbers, purchase prices, receipts, attachments —
can be encrypted per record with AES-256-GCM under a key derived from a
passphrase (PBKDF2-SHA256). Names, rooms, categories and warranty dates stay
plaintext so lists and search work without the key.

An encrypted vault stays readable to this validator for everything structural.
It cannot check attachments, because their filenames live inside the encrypted
sidecars, and it says so rather than reporting a pass it did not earn.

## Stability

Schema version 1. A vault written by a newer schema than a reader understands
must be refused rather than read and re-saved, which would silently discard
whatever the reader did not know about.

## Licence

See [LICENSE](LICENSE).
