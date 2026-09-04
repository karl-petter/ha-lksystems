#!/usr/bin/env python3
"""Reconstruct OpenAPI 3 specs for the LK Systems API from its Azure APIM
developer portal.

The portal's own "download API definition" export omits operations for
unauthenticated visitors (paths come back empty), but the per-operation
documentation endpoints the portal's UI calls to render its reference pages
are public and fully populated. This script walks those endpoints and
reassembles a self-contained OpenAPI 3 document per API.

Usage:
    python3 fetch_spec.py --out-dir /path/to/output [--api API_ID ...]
    python3 fetch_spec.py --out-dir /path/to/output --check [--api API_ID ...]

`--check` compares each cached spec's operation list and schemas against a
fresh (but cheap) fetch, without walking every operation's full detail, so it
costs a handful of requests instead of the ~20 per API that a full fetch
takes. It catches added/removed/renamed operations and any DTO/schema
change, but not a change confined to one operation's description or status
codes with no schema impact — treat it as a fast smoke test, not a
guarantee, and re-fetch outright when in doubt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PORTAL_BASE = "https://lk-home-assistant-prod.developer.azure-api.net"
API_VERSION = "2022-04-01-preview"
REQUEST_DELAY_SECONDS = 0.05


def _ssl_context() -> ssl.SSLContext:
    # Some Python builds (e.g. pyenv on macOS) ship without a populated
    # system CA path; prefer certifi's bundle when it's installed.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get(path: str, **query: str) -> Any:
    params = "&".join(f"{k}={v}" for k, v in {"api-version": API_VERSION, **query}.items())
    url = f"{PORTAL_BASE}{path}?{params}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
        body = json.load(response)
    time.sleep(REQUEST_DELAY_SECONDS)
    return body


def _get_all_pages(path: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_path = path
    while page_path:
        page = _get(page_path)
        items.extend(page["value"])
        next_link = page.get("nextLink")
        page_path = next_link[len(PORTAL_BASE):] if next_link else None
    return items


def list_apis() -> list[dict[str, Any]]:
    return _get_all_pages("/developer/apis")


def _openapi_parameter(name: str, location: str, param: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "in": location,
        "required": location == "path" or param.get("required", False),
        "schema": {"type": param.get("type", "string")},
    }


def _openapi_content(representations: list[dict[str, Any]]) -> dict[str, Any]:
    content: dict[str, Any] = {}
    for rep in representations:
        entry: dict[str, Any] = {}
        if rep.get("typeName"):
            entry["schema"] = {"$ref": f"#/components/schemas/{rep['typeName']}"}
        example = (rep.get("examples") or {}).get("default", {}).get("value")
        if example is not None:
            entry["example"] = example
        content[rep["contentType"]] = entry
    return content


def _openapi_operation(detail: dict[str, Any]) -> dict[str, Any]:
    parameters = [
        _openapi_parameter(p["name"], "path", p) for p in detail.get("templateParameters", [])
    ]
    parameters += [
        _openapi_parameter(p["name"], "query", p) for p in detail["request"]["queryParameters"]
    ]
    parameters += [
        _openapi_parameter(p["name"], "header", p) for p in detail["request"]["headers"]
    ]

    operation: dict[str, Any] = {"operationId": detail["id"], "parameters": parameters}
    if detail.get("description"):
        operation["description"] = detail["description"]

    representations = detail["request"]["representations"]
    if representations:
        operation["requestBody"] = {"content": _openapi_content(representations)}

    operation["responses"] = {
        str(resp["statusCode"]): {
            "description": resp.get("description") or "",
            **({"content": _openapi_content(resp["representations"])} if resp["representations"] else {}),
        }
        for resp in detail["responses"]
    }
    return operation


def _fetch_schemas(api_id: str) -> dict[str, Any]:
    schemas: dict[str, Any] = {}
    for schema_summary in _get_all_pages(f"/developer/apis/{api_id}/schemas"):
        schema_doc = _get(f"/developer/apis/{api_id}/schemas/{schema_summary['id']}")
        schemas.update(schema_doc.get("document", {}).get("components", {}).get("schemas", {}))
    return schemas


def _fingerprint(operations: list[dict[str, Any]], schemas: dict[str, Any]) -> str:
    material = {
        "operations": sorted((op["method"], op["urlTemplate"]) for op in operations),
        "schemas": schemas,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def build_openapi_document(api: dict[str, Any]) -> dict[str, Any]:
    api_id = api["id"]
    operations = _get_all_pages(f"/developer/apis/{api_id}/operations")

    paths: dict[str, Any] = {}
    for op_summary in operations:
        detail = _get(f"/developer/apis/{api_id}/operations/{op_summary['id']}")
        paths.setdefault(detail["urlTemplate"], {})[detail["method"].lower()] = _openapi_operation(detail)

    schemas = _fetch_schemas(api_id)

    return {
        "openapi": "3.0.1",
        "info": {"title": api["name"], "version": "1.0"},
        "servers": [{"url": f"https://link2.lk.nu/{api['path']}"}],
        "paths": paths,
        "components": {"schemas": schemas},
        "x-fingerprint": _fingerprint(operations, schemas),
    }


def fetch_fingerprint(api_id: str) -> str:
    """Cheaply recompute an API's fingerprint without walking every operation's full detail."""
    operations = _get_all_pages(f"/developer/apis/{api_id}/operations")
    schemas = _fetch_schemas(api_id)
    return _fingerprint(operations, schemas)


def run_fetch(out_dir: Path, api_ids: list[str] | None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        apis = list_apis()
    except urllib.error.URLError as exc:
        print(f"Failed to reach the developer portal: {exc}", file=sys.stderr)
        return 1

    if api_ids:
        apis = [a for a in apis if a["id"] in api_ids]

    for api in apis:
        print(f"Fetching {api['name']} ({api['id']})...", file=sys.stderr)
        document = build_openapi_document(api)
        out_file = out_dir / f"{api['id']}.openapi.json"
        out_file.write_text(json.dumps(document, indent=2, sort_keys=True))
        print(f"  -> {out_file} ({len(document['paths'])} paths)", file=sys.stderr)

    return 0


def run_check(spec_dir: Path, api_ids: list[str] | None) -> int:
    cached_files = {f.name.removesuffix(".openapi.json"): f for f in spec_dir.glob("*.openapi.json")}
    if api_ids:
        cached_files = {api_id: f for api_id, f in cached_files.items() if api_id in api_ids}

    if not cached_files:
        print(f"No cached specs found in {spec_dir}", file=sys.stderr)
        return 1

    stale_apis = []
    for api_id, cached_file in sorted(cached_files.items()):
        stored_fingerprint = json.loads(cached_file.read_text()).get("x-fingerprint")
        try:
            current_fingerprint = fetch_fingerprint(api_id)
        except urllib.error.URLError as exc:
            print(f"Failed to reach the developer portal: {exc}", file=sys.stderr)
            return 1

        if stored_fingerprint == current_fingerprint:
            print(f"{api_id}: up to date")
        else:
            print(f"{api_id}: CHANGED since last fetch - re-run without --check to refresh")
            stale_apis.append(api_id)

    return 1 if stale_apis else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory to write into (fetch mode) or read from (--check mode)")
    parser.add_argument("--api", action="append", dest="api_ids", help="Only fetch/check this API id (repeatable); default is all APIs on the portal")
    parser.add_argument("--check", action="store_true", help="Check cached specs for staleness instead of (re)fetching them")
    args = parser.parse_args()

    if args.check:
        return run_check(args.out_dir, args.api_ids)
    return run_fetch(args.out_dir, args.api_ids)


if __name__ == "__main__":
    raise SystemExit(main())
