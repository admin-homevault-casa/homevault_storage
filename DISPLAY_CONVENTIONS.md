# HomeVault — Display Conventions

The on-disk format (see `STORAGE_SCHEMA.md`) records facts: a warranty expiry date, a task due date, an integer interval. **This document defines how those facts are mapped to colour, label, and tier in the UI.**

The MAUI app and the standalone HTML viewer must agree on these rules. The single source of truth for the implementations is:

- C# / MAUI: `HomeVault.Core/Services/WarrantyHelper.cs`, `DueDateHelper.cs`
- JavaScript / viewer: `homevault-site/viewer.html` (`warrantyStatus`, `dueDisplay`)

Any change to the thresholds below must be reflected in **both** implementations and in the conformance tests.

---

## Warranty status

Computed from `HouseholdItem.warrantyExpiryDate` and "today."

| Tier | When | Colour token | Label |
|---|---|---|---|
| No warranty | `expiryDate` is null | muted | "no warranty" |
| Expired | `daysLeft < 0` | red | "expired" |
| Expiring soon | `0 ≤ daysLeft ≤ expiringSoonThreshold` | amber | "Nd left" |
| Active | `daysLeft > expiringSoonThreshold` | green | "Nmo left" |

**Default threshold:** 60 days. Configurable per user in Settings (MAUI app). The viewer hardcodes the default because it has no preferences store.

The same enum (`WarrantyStatus`) drives both the badge colour and the notification scheduling — see `NotificationOrchestrator`.

---

## Due date status

Computed from `MaintenanceTask.dueDate` / `Checklist.dueDate` and "today."

| Tier | When | Colour token | Label |
|---|---|---|---|
| None | `dueDate` is null | muted | "no due date" |
| Overdue | `daysLeft < 0` | red | "Nd overdue" |
| Due today | `daysLeft == 0` | amber | "due today" |
| Due soon | `0 < daysLeft ≤ 7` | amber | "in Nd" |
| Upcoming | `7 < daysLeft ≤ 30` | accent (yellow) | "in Nd" |
| Future | `daysLeft > 30` | green | "in Nmo" |

Default thresholds:
- Warning ≤ 7 days
- Upcoming ≤ 30 days

These are constants in `DueDateHelper`. They are NOT user-configurable today; if that changes, both implementations must pick up the new value from a shared source.

---

## Colour tokens

The tokens come from the dark/amber design system (homevault.casa). Hex values are the source of truth in `homevault-site/css/style.css` and mirrored in MAUI XAML resources.

| Token | Hex | Purpose |
|---|---|---|
| `--red`    | `#c0645a` | overdue / expired |
| `--amber`  | `#d4924a` | due-soon / expiring-soon / warning |
| `--accent` | `#c8a96e` | upcoming (yellow ochre) |
| `--green`  | `#6ab187` | future / healthy |
| `--muted`  | `#888880` | no value / disabled |

Badges always carry **both** the colour and a text label — never colour alone. This is an accessibility requirement, not a stylistic preference.

---

## Why not put thresholds in `vault.meta.json`?

Display thresholds are presentation, not data. They never change what's stored, only how it's rendered. A user who switches between the MAUI app and the viewer will see the same facts and the same colour interpretations because both implementations honour the defaults above. If the user customises their warranty threshold in MAUI Settings, the viewer continues to use the default — the difference is a display preference, not a data conflict.
