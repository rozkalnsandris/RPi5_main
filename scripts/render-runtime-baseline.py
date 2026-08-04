#!/usr/bin/env python3
"""Render only verified V02B evidence into the tracked runtime baseline."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile


def fail(message: str) -> None:
    raise SystemExit(f"render-runtime-baseline: {message}")


def read_tsv(path: pathlib.Path, fields: int) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = line.split("\t")
        if len(row) != fields:
            fail("malformed verified section")
        rows.append(row)
    return rows


def checked_output_path(repo_root: pathlib.Path, value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    absolute = path if path.is_absolute() else (pathlib.Path.cwd() / path)
    absolute = absolute.resolve(strict=False)
    try:
        absolute.relative_to(repo_root)
    except ValueError:
        fail("output path must remain below repository root")
    cursor = pathlib.Path("/")
    for part in absolute.parts[1:-1]:
        cursor /= part
        if cursor.is_symlink():
            fail("output path contains a symlink")
    if absolute.exists() and absolute.is_symlink():
        fail("output file cannot be a symlink")
    return absolute


def write_atomic(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".v02b-render-", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    arguments = parser.parse_args()

    script_dir = pathlib.Path(__file__).resolve().parent
    repo_root = script_dir.parent
    source = pathlib.Path(arguments.input).resolve(strict=True)
    verifier = script_dir / "verify-runtime-baseline.sh"
    checked = subprocess.run([str(verifier), str(source)], cwd=repo_root, capture_output=True, text=True)
    if checked.returncode != 0:
        fail("input evidence did not pass verification")

    json_out = checked_output_path(repo_root, arguments.json_out)
    markdown_out = checked_output_path(repo_root, arguments.markdown_out)
    if json_out == markdown_out:
        fail("output paths must differ")

    summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    manifest_digest = hashlib.sha256((source / "SHA256SUMS").read_bytes()).hexdigest()
    sections = source / "sections"
    statuses: dict[str, dict[str, str]] = {}
    with (source / "section-status.tsv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            statuses[row["section"]] = row

    def version(name: str) -> str | None:
        rows = read_tsv(sections / f"{name}.txt", 2)
        return rows[0][1] if rows else None

    containers = [
        {"name": row[0], "image": row[1], "state": row[2], "health": row[3]}
        for row in read_tsv(sections / "docker_containers.txt", 4)
    ]
    compose_projects = [{"name": row[0], "status": row[1]} for row in read_tsv(sections / "docker_compose_projects.txt", 2)]
    networks = [{"name": row[0], "driver": row[1], "scope": row[2]} for row in read_tsv(sections / "docker_networks.txt", 3)]
    state_rows = read_tsv(sections / "systemd_system_state.txt", 2)
    system_state = state_rows[0][1] if state_rows else None
    enabled = [{"name": row[0], "state": row[1]} for row in read_tsv(sections / "systemd_enabled_units.txt", 2)]
    failed = [
        {"name": row[0], "load": row[1], "active": row[2], "sub": row[3]}
        for row in read_tsv(sections / "systemd_failed_units.txt", 4)
    ]
    timers = [
        {"id": row[0], "load": row[1], "active": row[2], "sub": row[3], "activates": row[4], "next": row[5], "last": row[6]}
        for row in read_tsv(sections / "systemd_timers.txt", 7)
    ]
    sockets = [{"protocol": row[0], "address_scope": row[1], "port": int(row[2])} for row in read_tsv(sections / "listening_sockets.txt", 3)]
    interfaces = []
    for row in read_tsv(sections / "network_interfaces.txt", 7):
        scope_counts = {key: int(value) for key, value in (field.split("=", 1) for field in row[6].split(","))}
        interfaces.append({"name": row[0], "operstate": row[1], "link_type": row[2], "loopback": row[3] == "true", "ipv4_count": int(row[4]), "ipv6_count": int(row[5]), "scope_counts": scope_counts})

    def ordered(items: list[dict], *keys: str) -> list[dict]:
        unique = {tuple(item[key] if not isinstance(item[key], dict) else tuple(sorted(item[key].items())) for key in keys): item for item in items}
        return [unique[key] for key in sorted(unique)]

    limitations = [
        f"{name}: {row['classification']}" for name, row in sorted(statuses.items())
        if row["classification"] not in {"success"}
    ]
    payload = {
        "metadata": {
            "schema_version": "v02b.0.0",
            "collection_utc": summary["collected_at_utc"],
            "source_commit": summary["git_commit"],
            "evidence_manifest_sha256": manifest_digest,
            "context": summary["context"],
        },
        "docker": {
            "engine_version": version("docker_engine_version"),
            "compose_version": version("docker_compose_version"),
            "containers": ordered(containers, "name", "image", "state", "health"),
            "compose_projects": ordered(compose_projects, "name", "status"),
            "networks": ordered(networks, "name", "driver", "scope"),
        },
        "systemd": {
            "system_state": system_state,
            "enabled_units": ordered(enabled, "name", "state"),
            "failed_units": ordered(failed, "name", "load", "active", "sub"),
            "timers": ordered(timers, "id", "load", "active", "sub", "activates", "next", "last"),
        },
        "sockets": ordered(sockets, "protocol", "address_scope", "port"),
        "interfaces": ordered(interfaces, "name", "operstate", "link_type", "loopback", "ipv4_count", "ipv6_count", "scope_counts"),
        "limitations": limitations,
    }
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"

    lines = [
        "# Current runtime baseline",
        "",
        "This is a verified, read-only runtime snapshot, not deployment configuration.",
        "",
        "## Evidence binding",
        "",
        f"- Collection UTC: `{payload['metadata']['collection_utc']}`",
        f"- Source commit: `{payload['metadata']['source_commit']}`",
        f"- Evidence manifest SHA-256: `{manifest_digest}`",
        f"- Collection context: `{payload['metadata']['context']}`",
        "",
        "## Docker",
        "",
        f"- Engine version: `{payload['docker']['engine_version'] or 'unavailable'}`",
        f"- Compose version: `{payload['docker']['compose_version'] or 'unavailable'}`",
        f"- Containers: {len(containers)}; Compose projects: {len(compose_projects)}; networks: {len(networks)}.",
    ]
    for item in payload["docker"]["containers"]:
        lines.append(f"- Container `{item['name']}`: image `{item['image']}`, state `{item['state']}`, health `{item['health']}`.")
    for item in payload["docker"]["compose_projects"]:
        lines.append(f"- Compose project `{item['name']}`: status `{item['status']}`.")
    for item in payload["docker"]["networks"]:
        lines.append(f"- Network `{item['name']}`: driver `{item['driver']}`, scope `{item['scope']}`.")
    lines += ["", "## systemd", "", f"- System state: `{system_state or 'unavailable'}`.", f"- Enabled units: {len(enabled)}; failed units: {len(failed)}; timers: {len(timers)}."]
    for item in payload["systemd"]["enabled_units"]:
        lines.append(f"- Enabled `{item['name']}`: `{item['state']}`.")
    for item in payload["systemd"]["failed_units"]:
        lines.append(f"- Failed `{item['name']}`: load `{item['load']}`, active `{item['active']}`, sub `{item['sub']}`.")
    for item in payload["systemd"]["timers"]:
        lines.append(f"- Timer `{item['id']}`: load `{item['load']}`, active `{item['active']}`, sub `{item['sub']}`, activates `{item['activates']}`, next `{item['next']}`, last `{item['last']}`.")
    lines += ["", "## Listening ports", ""]
    lines.extend(f"- `{item['protocol']}` `{item['address_scope']}` port `{item['port']}`." for item in payload["sockets"])
    lines += ["", "## Interfaces", ""]
    for item in payload["interfaces"]:
        scopes = ", ".join(f"{key}={value}" for key, value in sorted(item["scope_counts"].items()))
        lines.append(f"- `{item['name']}`: operstate `{item['operstate']}`, link type `{item['link_type']}`, loopback `{str(item['loopback']).lower()}`, IPv4={item['ipv4_count']}, IPv6={item['ipv6_count']}; scopes {scopes}.")
    lines += ["", "## Limitations and interpretation", "", "The entries above are direct, sanitized observations. They do not establish causation or serve as deployment configuration."]
    if limitations:
        lines.append("Unavailable or informational sections:")
        lines.extend(f"- `{item}`." for item in limitations)
    else:
        lines.append("- No command-capability limitations were recorded.")
    markdown = "\n".join(lines) + "\n"
    write_atomic(json_out, content)
    write_atomic(markdown_out, markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
