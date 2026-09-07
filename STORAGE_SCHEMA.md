# HomeVault Storage Schema

**Schema version: 1**

This document is the authoritative specification for the HomeVault vault file format. It is intentionally implementation-agnostic — any tool or library that can read UTF-8 JSON and perform AES-256-GCM decryption can read a HomeVault vault.

---

## Table of Contents

1. [Overview](#overview)
2. [Directory Layout](#directory-layout)
3. [Data Tiers](#data-tiers)
4. [File Formats](#file-formats)
   - [vault.meta.json](#vaultmetajson)
   - [index.json](#indexjson)
   - [rooms/{id}.json](#roomsidjson)
   - [items/{id}.json](#itemsidjson)
   - [items/{id}.secret.json](#itemsidsecretjson)
   - [tasks/{id}.json](#tasksidjson)
   - [checklists/{id}.json](#checklistsidjson)
   - [attachments/](#attachments)
5. [Shared Types](#shared-types)
   - [Schedule](#schedule)
   - [CompletionEntry](#completionentry)
   - [ChecklistCompletionEntry](#checklistcompletionentry)
   - [RepairEntry](#repairentry)
   - [Attachment](#attachment)
6. [Encryption](#encryption)
   - [EncryptedBlob](#encryptedblob)
   - [Key Derivation](#key-derivation)
7. [Enums](#enums)
8. [Conventions](#conventions)
9. [Versioning](#versioning)

---

## Overview

A HomeVault vault is a folder on disk. Every record is a UTF-8 JSON file. The vault has two tiers of data:

- **Plaintext tier** — always readable, contains no sensitive fields.
- **Sensitive tier** — optionally encrypted with AES-256-GCM. A missing or wrong passphrase makes sensitive fields unavailable, but the plaintext tier (including warranty dates) always loads.

The top-level index file (`index.json`) contains lightweight summaries of every record and is always plaintext. Apps read it once on launch to populate list screens without opening every individual file.

---

## Directory Layout

```
<vault-root>/
├── vault.meta.json          # Schema version, encryption settings
├── index.json               # Flat summaries of all records (always plaintext)
├── rooms/
│   └── <uuid>.json          # One file per room
├── items/
│   ├── <uuid>.json          # Plaintext tier — name, category, warranty date, etc.
│   └── <uuid>.secret.json   # Sensitive tier — serial number, price, receipts, etc.
├── tasks/
│   └── <uuid>.json          # Maintenance task with schedule and completion history
├── checklists/
│   └── <uuid>.json          # Named group of tasks with its own schedule
├── attachments/
│   └── <uuid>.<ext>         # Raw attachment files (receipts, manuals, photos)
└── trash/                   # Deleted records, awaiting purge or restore
    ├── manifest.json        # What was deleted, when, by whom, and from where
    ├── items/<uuid>.json
    ├── items/<uuid>.secret.json
    ├── rooms/<uuid>.json
    ├── tasks/<uuid>.json
    ├── checklists/<uuid>.json
    └── attachments/<uuid>.<ext>
```

All IDs are lowercase UUIDs (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).

---

## Data Tiers

| Tier | Files | Encryption |
|---|---|---|
| Plaintext | `vault.meta.json`, `index.json`, `rooms/`, `items/*.json`, `tasks/`, `checklists/` | Never encrypted |
| Sensitive | `items/*.secret.json` | Encrypted when `encryptionEnabled = true` |

**Design rationale:** If a user forgets their passphrase they lose sensitive details (purchase price, serial number, receipts) but retain full visibility into what they own and when warranties expire.

---

## File Formats

### vault.meta.json

Always present. Always plaintext. Read first by any tool opening a vault.

```json
{
  "schemaVersion": 1,
  "encryptionEnabled": false,
  "kdfSalt": null,
  "kdfIterations": 200000
}
```

| Field | Type | Description |
|---|---|---|
| `schemaVersion` | `integer` | Increments on breaking data-model changes. Current version: **1**. |
| `encryptionEnabled` | `boolean` | Whether `*.secret.json` sidecars are encrypted. |
| `kdfSalt` | `string \| null` | Base64-encoded random 32-byte salt for PBKDF2. `null` when encryption is disabled. |
| `kdfIterations` | `integer` | PBKDF2 iteration count. Minimum **200,000**. Default: **200,000**. |

---

### index.json

Always present. Always plaintext. Contains lightweight summaries of every record — designed to be read once on startup to populate list screens.

**Important:** This file must never contain sensitive fields (serial numbers, prices, etc.).

```json
{
  "rooms": [
    { "id": "uuid", "name": "kitchen", "itemCount": 3 }
  ],
  "items": [
    {
      "id": "uuid",
      "name": "Dishwasher",
      "category": "appliances_large",
      "roomId": "uuid",
      "brand": "Bosch",
      "model": "SHPM88Z75N",
      "primaryPhotoId": "uuid",
      "primaryPhotoFilename": "uuid.jpg.enc",
      "warrantyExpiryDate": "2027-06-15",
      "hasSecrets": true
    }
  ],
  "tasks": [
    {
      "id": "uuid",
      "title": "Replace water filter",
      "linkedItemId": "uuid",
      "checklistId": null,
      "dueDate": "2026-09-01",
      "scheduleType": "recurring"
    }
  ],
  "checklists": [
    {
      "id": "uuid",
      "name": "Annual HVAC service",
      "dueDate": "2026-11-01",
      "taskCount": 4
    }
  ],
  "lastUpdated": "2026-05-30T14:23:00Z"
}
```

**RoomSummary fields:**

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID |
| `name` | `string` | Display name |
| `itemCount` | `integer` | Derived count — number of items with this `roomId` |

**ItemSummary fields:**

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID |
| `name` | `string` | Display name |
| `category` | `string` | Catalog key or free text — see [Catalog values](#catalog-values--rooms-and-categories) |
| `roomId` | `string \| null` | UUID of the containing room |
| `brand` | `string \| null` | Manufacturer name |
| `model` | `string \| null` | Model name or number |
| `primaryPhotoId` | `string \| null` | UUID of the primary photo attachment |
| `primaryPhotoFilename` | `string \| null` | On-disk filename of that attachment, e.g. `"a3f1….jpg.enc"`. Denormalised out of the sensitive tier so a list built from the plaintext index can show a thumbnail without opening a sidecar per row. Maintained by `VaultService` on save and backfilled by Rebuild Index — nothing else should write it. |
| `warrantyExpiryDate` | `string \| null` | `YYYY-MM-DD`. `null` = no warranty recorded |
| `hasSecrets` | `boolean` | Whether a `*.secret.json` sidecar exists |

**TaskSummary fields:**

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID |
| `title` | `string` | Display title |
| `linkedItemId` | `string \| null` | UUID of the linked item |
| `checklistId` | `string \| null` | UUID of the parent checklist |
| `dueDate` | `string \| null` | `YYYY-MM-DD`. **`null` means exactly one thing: a completed one-off.** An outstanding task always has a date — see the invariant below. |
| `scheduleType` | `"oneOff" \| "recurring"` | See [Enums](#enums) |

**ChecklistSummary fields:**

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID |
| `name` | `string` | Display name |
| `dueDate` | `string \| null` | `YYYY-MM-DD` |
| `taskCount` | `integer` | Number of member tasks |

---

## trash/

Deleting a record moves it here instead of destroying it (spec 17). Records keep
their original folder structure and filenames underneath `trash/`, so the folder
they are in is the only thing that changed and a third-party tool can still read
them.

Deleting an item takes its `.secret.json` sidecar and its attachments with it.

**A trashed record is absent from `index.json`.** That is what makes the trash
invisible to everything that is not looking for it: every list, count and
reminder reads the index, so they all behave exactly as they would if the record
had been destroyed.

**No `schemaVersion` bump.** An older build ignores a folder it does not know
about, and the record is already gone from the index, so it sees precisely what
it should. Restoring later is an ordinary write it will pick up.

### trash/manifest.json

The files under `trash/` do not record where they came from, and reading them to
build a list would mean decrypting every sidecar. The manifest holds both.

```json
{
  "entries": [
    {
      "id": "uuid",
      "type": "Item",
      "originalPaths": [
        "items/uuid.json",
        "items/uuid.secret.json",
        "attachments/uuid.jpg"
      ],
      "deletedAt": "2026-08-21T14:02:00Z",
      "displayName": "Dishwasher",
      "deletedBy": "Me",
      "attachmentsUnresolved": false
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `string` | The record's own UUID |
| `type` | `"Item" \| "Room" \| "Task" \| "Checklist"` | What kind of record |
| `originalPaths` | `string[]` | Every file that moved, as its path *before* deletion. Restore puts each one back exactly here. |
| `deletedAt` | `string` | ISO 8601 UTC |
| `displayName` | `string` | What to show in the trash list, so it renders without opening — or decrypting — each record. For a room this is the stored value, which may be a catalog key. |
| `deletedBy` | `string` | Who deleted it. The trash is shared, so one household member can restore what another deleted. |
| `attachmentsUnresolved` | `boolean` | True when an item's attachments could not be identified at delete time — see below |

### Retention

Entries older than the retention window are purged when the app comes to the
foreground. The default is 30 days; "keep until I delete it" is available. The
setting is per-device (it lives in preferences, not in the vault), because it is
a preference about behaviour rather than a fact about the records.

### Attachments and locked vaults

Attachment filenames are random UUIDs. The only thing linking one to an item is
the item's secrets sidecar — which cannot be read while the vault is locked.

Deleting an item from a locked vault therefore moves the record and the sidecar,
leaves the attachments in `attachments/`, and sets `attachmentsUnresolved`.
Restore is unaffected: the files never moved, so the item comes back whole. What
it costs is purging — permanently deleting that entry can only find the
attachments if the vault has been unlocked by then. If it has not, they are left
in place. An orphaned attachment is wasteful, not dangerous, and the alternative
is refusing to empty the trash until someone remembers a passphrase.

---

## Catalog values — rooms and categories

`Room.name` and `HouseholdItem.category` hold one of two things, and a reader
must handle both:

| What the user did | What is stored | Example |
|---|---|---|
| Picked from a HomeVault list | a stable lowercase key | `kitchen`, `appliances_large` |
| Typed their own | exactly what they typed | `Utility Room`, `Smart Home` |

**Reading:** look the value up in the table below. If it is not there, display it
as-is. That single fallback covers user-typed values, keys added by a newer
build, and any vault written before this scheme existed — no special cases and
no version check.

**Writing:** if what the user entered matches one of these labels, store the key.
Otherwise store their text verbatim.

The point of the keys is that the vault does not change meaning when the reader
changes language. A Spanish user's vault holds `kitchen`, not `Cocina`, so an
English reader — or a script, or a different app — sees the same value the
Spanish user does.

Rooms and categories are separate namespaces because they are separate fields;
both legitimately contain `other`.

### Room keys

| Key | English label |
|---|---|
| `kitchen` | Kitchen |
| `living_room` | Living Room |
| `master_bedroom` | Master Bedroom |
| `bedroom` | Bedroom |
| `bathroom` | Bathroom |
| `garage` | Garage |
| `basement` | Basement |
| `attic` | Attic |
| `laundry` | Laundry |
| `office` | Office |
| `outdoor` | Outdoor |
| `other` | Other |

### Category keys

| Key | English label |
|---|---|
| `appliances_large` | Appliances (large) |
| `appliances_small` | Appliances (small) |
| `electronics` | Electronics |
| `computing` | Computing |
| `audio_video` | Audio / Video |
| `phones_tablets` | Phones & Tablets |
| `tools_garden` | Tools & Garden |
| `furniture` | Furniture |
| `other` | Other |

Keys are append-only. A key that has ever been written to a vault is never
renamed or repurposed, because doing so silently changes what existing records
mean — and the fallback above would then render it as a raw key rather than
raise an error.

Implementations:

- C# — `HomeVault.Core/Localisation/CatalogKeys.cs` and `Catalog.cs`
- JavaScript — `homevault-site/viewer.html` (`CATALOG`, `catalogLabel`)

---

### rooms/{id}.json

```json
{
  "id": "uuid",
  "name": "kitchen",
  "notes": "Renovated 2023",
  "createdAt": "2026-01-10T09:00:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID |
| `name` | `string` | Catalog key or free text — see [Catalog values](#catalog-values--rooms-and-categories) |
| `notes` | `string \| null` | Free-form notes |
| `createdAt` | `string` | ISO 8601 UTC timestamp |

---

### items/{id}.json

Plaintext tier. Always readable without a passphrase.

```json
{
  "id": "uuid",
  "name": "Dishwasher",
  "category": "appliances_large",
  "roomId": "uuid",
  "brand": "Bosch",
  "model": "SHPM88Z75N",
  "primaryPhotoId": "uuid",
  "primaryPhotoFilename": "uuid.jpg.enc",
  "warrantyExpiryDate": "2027-06-15",
  "notes": "Installed by HomeDepot",
  "hasSecrets": true,
  "createdAt": "2026-01-10T09:00:00Z",
  "updatedAt": "2026-05-30T14:23:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID |
| `name` | `string` | Display name |
| `category` | `string` | Catalog key or free text — see [Catalog values](#catalog-values--rooms-and-categories) |
| `roomId` | `string \| null` | UUID of the containing room |
| `brand` | `string \| null` | Manufacturer name |
| `model` | `string \| null` | Model name or number |
| `primaryPhotoId` | `string \| null` | UUID of the primary photo attachment |
| `primaryPhotoFilename` | `string \| null` | On-disk filename of that attachment, e.g. `"a3f1….jpg.enc"`. Denormalised out of the sensitive tier so a list built from the plaintext index can show a thumbnail without opening a sidecar per row. Maintained by `VaultService` on save and backfilled by Rebuild Index — nothing else should write it. |
| `warrantyExpiryDate` | `string \| null` | `YYYY-MM-DD` |
| `notes` | `string \| null` | Free-form notes |
| `hasSecrets` | `boolean` | Whether a sidecar exists. Set automatically by the writer. |
| `createdAt` | `string` | ISO 8601 UTC timestamp |
| `updatedAt` | `string` | ISO 8601 UTC timestamp |

---

### items/{id}.secret.json

Sensitive tier sidecar. Contains the same UUID as its companion `items/{id}.json`.

**When encryption is disabled** — raw JSON:

```json
{
  "itemId": "uuid",
  "serialNumber": "SN12345678",
  "purchaseDate": "2024-06-15",
  "purchasePrice": 849.99,
  "purchaseCurrency": "USD",
  "purchaseStore": "Home Depot",
  "warrantyClaimRef": "CLAIM-2024-001",
  "repairHistory": [
    {
      "date": "2025-03-10",
      "description": "Replaced door latch",
      "cost": 125.00,
      "technician": "Bob's Appliance Repair"
    }
  ],
  "attachments": [
    {
      "id": "uuid",
      "type": "receipt",
      "filename": "uuid.pdf",
      "addedDate": "2024-06-16"
    }
  ]
}
```

**When encryption is enabled** — an `EncryptedBlob` wrapper (see [Encryption](#encryption)):

```json
{
  "enc": "AES-256-GCM",
  "nonce": "<base64>",
  "ciphertext": "<base64>"
}
```

The `ciphertext` decrypts to the raw JSON shown above.

> **Why a filename is in the plaintext tier.** `primaryPhotoId` points at an
> `Attachment`, and attachments live in this sidecar — so the plaintext index
> cannot resolve a photo to a file, and opening every sidecar to do it is the
> exact cost `index.json` exists to avoid. `primaryPhotoFilename` closes that
> gap. It reveals the file extension and whether the blob is encrypted, neither
> of which is new: anyone who can list `attachments/` already sees both. It does
> **not** reveal the image — thumbnails live outside the vault and are encrypted
> when their source is (`docs/THUMBNAILS.md`).

**HouseholdItemSecrets fields:**

| Field | Type | Description |
|---|---|---|
| `itemId` | `string` | UUID — matches the companion `items/{id}.json` |
| `serialNumber` | `string \| null` | Manufacturer serial number |
| `purchaseDate` | `string \| null` | `YYYY-MM-DD` |
| `purchasePrice` | `number \| null` | Decimal amount |
| `purchaseCurrency` | `string \| null` | ISO 4217 currency code (e.g. `"USD"`). Only written alongside a `purchasePrice` — an amount-less currency says nothing, and the app's picker always has a selection, so writing it unconditionally would stamp one onto every record. |
| `purchaseStore` | `string \| null` | Retailer or vendor name |
| `warrantyClaimRef` | `string \| null` | Reference number for an active/past warranty claim |
| `repairHistory` | `RepairEntry[]` | See [RepairEntry](#repairentry). Appended to by the repair form and by completing a linked maintenance task from the item's detail screen. |
| `attachments` | `Attachment[]` | See [Attachment](#attachment) |

---

### tasks/{id}.json

Always plaintext.

```json
{
  "id": "uuid",
  "title": "Replace HVAC filter",
  "notes": "Filter size: 16x25x1",
  "linkedItemId": "uuid",
  "checklistId": null,
  "schedule": {
    "type": "recurring",
    "intervalDays": 90,
    "anchor": "lastCompleted"
  },
  "dueDate": "2026-09-01",
  "completionHistory": [
    {
      "date": "2026-06-03",
      "completedBy": "Me"
    }
  ],
  "createdAt": "2026-01-10T09:00:00Z",
  "updatedAt": "2026-06-03T18:00:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID |
| `title` | `string` | Display title |
| `notes` | `string \| null` | Free-form notes |
| `linkedItemId` | `string \| null` | UUID of the related household item |
| `checklistId` | `string \| null` | UUID of the parent checklist (if a member) |
| `schedule` | `Schedule` | See [Schedule](#schedule) |
| `dueDate` | `string \| null` | `YYYY-MM-DD`. Set at creation for **both** schedule types, and recalculated after each completion for recurring tasks. `null` only after a one-off task is completed. |
| `completionHistory` | `CompletionEntry[]` | See [CompletionEntry](#completionentry) |
| `createdAt` | `string` | ISO 8601 UTC timestamp |
| `updatedAt` | `string` | ISO 8601 UTC timestamp |

**Recurrence rule:** On completion of a recurring task, `dueDate = completionDate + schedule.intervalDays`. Being late never compresses the next interval — the clock always starts from the actual completion date.

**Due-date invariant:** an outstanding task always has a `dueDate`, whatever its
schedule type. `null` means the task is a completed one-off and nothing else.

This is not decoration — it is what every list in the app filters on, so a task
written with `dueDate: null` is not merely unsorted, it is *unreachable*: no
screen shows it, so it cannot be opened, edited, or completed.

A recurring task's first `dueDate` therefore comes from the writer, not from the
schedule. `ScheduleService.ComputeNextDueDate` derives a date from the previous
completion and has nothing to count from before the first one, so it returns
`null` for a task that has never been completed. `TaskService.CreateTaskAsync`
seeds `today + intervalDays` when a recurring task arrives without one.

Anything writing a task record — including a tool operating on the vault
directly — has to honour this. If you ever genuinely need "a task with no due
date", add a field to express it; do not reuse the `null`.

Detail and the bug that established this: `docs/TESTING-NOTES-2026-08-22.md`.

---

### checklists/{id}.json

Always plaintext.

```json
{
  "id": "uuid",
  "name": "Annual HVAC service",
  "description": "All tasks needed before heating season",
  "taskIds": ["uuid-1", "uuid-2", "uuid-3"],
  "schedule": {
    "type": "recurring",
    "intervalDays": 365,
    "anchor": "lastCompleted"
  },
  "dueDate": "2026-11-01",
  "completionHistory": [
    {
      "date": "2025-10-28",
      "completedBy": "Me",
      "trigger": "allTasksChecked"
    }
  ],
  "createdAt": "2025-01-01T00:00:00Z",
  "updatedAt": "2025-10-28T20:00:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID |
| `name` | `string` | Display name |
| `description` | `string \| null` | Free-form description |
| `taskIds` | `string[]` | Ordered list of member task UUIDs |
| `schedule` | `Schedule` | See [Schedule](#schedule) |
| `dueDate` | `string \| null` | `YYYY-MM-DD` |
| `completionHistory` | `ChecklistCompletionEntry[]` | See [ChecklistCompletionEntry](#checklistcompletionentry) |
| `createdAt` | `string` | ISO 8601 UTC timestamp |
| `updatedAt` | `string` | ISO 8601 UTC timestamp |

**Completion triggers:**
- `allTasksChecked` — every member task was individually completed; the checklist auto-fired.
- `manual` — user explicitly marked the whole checklist done (overrides individual task state).

On either trigger: `dueDate` advances, a `ChecklistCompletionEntry` is appended, and member tasks' completion state resets for the next cycle.

---

### attachments/

Raw or encrypted attachment files.

| Encryption | Filename                    | Contents                          |
|---|---|---|
| Disabled   | `attachments/{uuid}.{ext}`  | Raw bytes (e.g. PDF, JPEG, PNG)   |
| Enabled    | `attachments/{uuid}.{ext}.enc` | `EncryptedBlob` JSON wrapping the raw bytes — same envelope format as `*.secret.json` |

The `.enc` suffix is the on-disk signal that a file is encrypted; third-party tools may detect it without sniffing content. `Attachment.filename` in the containing item's secrets records the exact on-disk filename including the suffix when applicable.

Common base extensions: `.pdf` (receipts, manuals), `.jpg` / `.png` (photos), `.heic` / `.heif` (iOS photos).

When the vault is encrypted but the session key has not been supplied, a viewer must refuse to render the attachment (treat as locked) rather than presenting the raw `EncryptedBlob` JSON.

---

## Shared Types

### Schedule

Embedded in both `tasks/{id}.json` and `checklists/{id}.json`.

```json
{ "type": "oneOff" }

{ "type": "recurring", "intervalDays": 90, "anchor": "lastCompleted" }
```

| Field | Type | Required when | Description |
|---|---|---|---|
| `type` | `"oneOff" \| "recurring"` | Always | See [Enums](#enums) |
| `intervalDays` | `integer` | `type = recurring` | Number of days between completions. Minimum 1. |
| `anchor` | `"lastCompleted"` | `type = recurring` | How the next interval is calculated. Currently only `lastCompleted`. |

---

### CompletionEntry

One entry per task completion.

```json
{ "date": "2026-06-03", "completedBy": "Me" }
```

| Field | Type | Description |
|---|---|---|
| `date` | `string` | `YYYY-MM-DD` — the actual completion date |
| `completedBy` | `string` | Display name of the person who completed the task |

---

### ChecklistCompletionEntry

One entry per checklist completion.

```json
{ "date": "2025-10-28", "completedBy": "Me", "trigger": "allTasksChecked" }
```

| Field | Type | Description |
|---|---|---|
| `date` | `string` | `YYYY-MM-DD` |
| `completedBy` | `string` | Display name |
| `trigger` | `"manual" \| "allTasksChecked"` | See [Enums](#enums) |

---

### RepairEntry

One entry in an item's repair log. Part of the sensitive tier.

```json
{
  "date": "2025-03-10",
  "description": "Replaced door latch",
  "cost": 125.00,
  "technician": "Bob's Appliance Repair"
}
```

| Field | Type | Description |
|---|---|---|
| `date` | `string` | `YYYY-MM-DD` |
| `description` | `string` | What was done |
| `cost` | `number \| null` | Repair cost (same currency as `purchaseCurrency`) |
| `technician` | `string \| null` | Name of person or company |

---

### Attachment

A reference to a file in `attachments/`. Part of the sensitive tier.

```json
{
  "id": "uuid",
  "type": "receipt",
  "filename": "uuid.pdf",
  "addedDate": "2024-06-16"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID — matches the filename stem in `attachments/` |
| `type` | `"receipt" \| "manual" \| "photo"` | Attachment category |
| `filename` | `string` | Actual filename in `attachments/` (e.g. `"uuid.pdf"`) |
| `addedDate` | `string` | `YYYY-MM-DD` |

---

## Encryption

Encryption is opt-in. When disabled, `items/{id}.secret.json` files are raw JSON. When enabled, they are replaced with an `EncryptedBlob`.

### EncryptedBlob

```json
{
  "enc": "AES-256-GCM",
  "nonce": "aGVsbG8gd29ybGQ=",
  "ciphertext": "c2VjcmV0IGRhdGEgaGVyZQ=="
}
```

| Field | Type | Description |
|---|---|---|
| `enc` | `string` | Cipher identifier. Currently always `"AES-256-GCM"`. |
| `nonce` | `string` | Base64-encoded 12-byte nonce. Unique per file per write. |
| `ciphertext` | `string` | Base64-encoded AES-256-GCM ciphertext **including the 16-byte authentication tag** appended at the end. |

**To decrypt:**
1. Base64-decode `nonce` → 12 bytes.
2. Base64-decode `ciphertext` → `N` bytes; last 16 bytes are the GCM auth tag.
3. Derive the 32-byte key (see below).
4. Decrypt with AES-256-GCM using the nonce and key; verify the auth tag.
5. Parse the resulting bytes as UTF-8 JSON → `HouseholdItemSecrets`.

If decryption fails (wrong key, tampered data), the ciphertext must be treated as inaccessible. Do not surface partial data.

---

### Key Derivation

The encryption key is derived from the user's passphrase using **PBKDF2-SHA256**.

| Parameter | Value |
|---|---|
| Algorithm | PBKDF2 with HMAC-SHA256 |
| Key length | 32 bytes (256 bits) |
| Salt | 32 random bytes, stored as Base64 in `vault.meta.json` → `kdfSalt` |
| Iterations | Value from `vault.meta.json` → `kdfIterations` (minimum 200,000) |

The passphrase is never written to disk. The derived 256-bit key is stored in the OS secure-storage facility (iOS Keychain / Android Keystore / Windows Credential Manager) so the vault can unlock without re-prompting after the app restarts. The passphrase itself remains in memory only for the duration of the derivation call. Vaults whose `kdfIterations` is read as less than 200,000 must be clamped up to 200,000 before use — a corrupted or malicious `vault.meta.json` cannot weaken the KDF below this floor.

---

## Enums

All enums are serialised as **camelCase strings** in JSON.

### ScheduleType

Controls whether a task or checklist repeats.

| JSON value | Meaning |
|---|---|
| `"oneOff"` | Fixed due date. No recurrence after completion. |
| `"recurring"` | Due date advances by `intervalDays` from the actual completion date. |

### ScheduleAnchor

Determines what date the next recurrence interval is anchored to.

| JSON value | Meaning |
|---|---|
| `"lastCompleted"` | Next due date = actual completion date + intervalDays. Being late never compresses the interval. |

### CompletionTrigger

What caused a checklist to be marked complete.

| JSON value | Meaning |
|---|---|
| `"manual"` | User explicitly marked the whole checklist done. |
| `"allTasksChecked"` | Every member task was individually completed; checklist auto-fired. |

---

## Conventions

- **IDs** — all IDs are lowercase UUID v4 strings (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).
- **Dates** — calendar dates use `YYYY-MM-DD` (ISO 8601 date only, no time component).
- **Timestamps** — `createdAt` / `updatedAt` use ISO 8601 UTC (`2026-05-30T14:23:00Z`).
- **Encoding** — all JSON files are UTF-8, no BOM.
- **Null vs absent** — optional fields are included in the JSON with a `null` value rather than omitted entirely, to make schema evolution easier.
- **Index consistency** — `index.json` is a derived cache. It may be safely deleted and rebuilt from the individual record files at any time using a vault repair / rebuild operation. Implementations must not treat it as the source of truth.

---

## Versioning

`vault.meta.json` contains a `schemaVersion` integer starting at **1**.

A higher version number indicates a breaking change to the data model. Any tool that reads a vault with an unrecognised schema version **must refuse to read or write** that vault and **should display a warning** to the user recommending they upgrade the tool first. The MAUI app implements this as `UnsupportedSchemaVersionException` thrown from `VaultService.LoadMetaAsync`; the standalone viewer surfaces a banner and blocks any future write paths.

Additive changes (new optional fields) do not increment the schema version. Implementations must silently ignore unknown fields during deserialisation (`PropertyNameCaseInsensitive` / `additionalProperties`-permissive behaviour).

| Version | Changes |
|---|---|
| 1 | Initial release |
