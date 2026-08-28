---
name: lk-api-spec
description: Fetch the current LK Systems API OpenAPI spec (Authentication, Device Control, Device Service, Messaging) from its Azure APIM developer portal and cache it for this session. Use whenever a task needs to know the real shape of an LK Systems endpoint — request/response fields, parameters, status codes — such as reviewing or extending pylksystems, debugging an API call, or checking whether the real API has drifted from what pylksystems assumes.
---

# LK Systems API spec

`custom_components/lksystems/pylksystems/__init__.py` calls an LK Systems API
that is documented on an Azure APIM developer portal
(https://lk-home-assistant-prod.developer.azure-api.net/, linked from the
project README). The portal's own "download API definition" button omits
operations for unauthenticated visitors — the export comes back with
`paths: {}`. `fetch_spec.py` (in this skill's directory) works around that by
walking the portal's public per-operation documentation endpoints directly
and reassembling a complete OpenAPI 3 document per API.

## Usage

Run it with the output directory set to this session's scratchpad — the spec
only needs to live for the session, not the repo:

```bash
python3 .claude/skills/lk-api-spec/fetch_spec.py --out-dir <scratchpad>/lk-api-spec
```

This writes one file per API: `auth.openapi.json`, `lk-device-control.openapi.json`,
`lk-device-service.openapi.json`, `messagingv2.openapi.json`. Takes about
20 seconds (~85 HTTP calls to the portal, across all four APIs). Pass
`--api <id>` (repeatable) to fetch only specific APIs when you already know
which one you need.

Read the resulting JSON file(s) to answer the task — e.g. grep `paths` for a
`urlTemplate`, or check a schema under `components.schemas` for a DTO's real
fields.

### Before trusting a spec already fetched earlier this session

The portal exposes no real version/revision signal to poll (`apiRevision` is
permanently `"1"`, and its ETag is a constant placeholder), so there's no
cheap "has this changed" field to read. Instead, before relying on a cached
spec for anything consequential — and definitely if meaningful time has
passed since it was fetched — run a cheap staleness check against the same
directory:

```bash
python3 .claude/skills/lk-api-spec/fetch_spec.py --out-dir <scratchpad>/lk-api-spec --check
```

This re-fetches only each API's operation list and schemas (a few seconds,
not ~20), hashes them, and compares against the fingerprint stored in the
cached file. It prints `up to date` or `CHANGED` per API and exits nonzero if
anything changed. On `CHANGED`, re-run the plain (non-`--check`) fetch for
that API before using it. Note the check can miss a change confined to one
operation's description or status codes with no schema impact — it's a fast
smoke test, not a guarantee.

If the script fails with `CERTIFICATE_VERIFY_FAILED`, the Python running it
lacks a populated system CA bundle (seen with some pyenv builds on macOS);
the script already falls back to `certifi`'s bundle when that package is
importable, so `pip install certifi` into the active environment fixes it.
