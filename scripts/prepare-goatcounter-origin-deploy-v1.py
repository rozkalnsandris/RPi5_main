#!/usr/bin/env python3
"""Offline preparation only: validate reviewed public evidence and emit a bundle.

No network, subprocess, Docker, runtime reads, installed-file writes or activation.
Input SHA is an independently reviewed byte binding, not a signature substitute.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib/deploy_executor"))
import simple_deploy_v1 as sd


class Refusal(ValueError):
    pass


def require(ok: bool) -> None:
    if not ok:
        raise Refusal("ORIGIN_PREPARATION_REFUSED")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def validate_provenance(statement, profile):
    require(type(statement) is dict)
    statement_type = statement.get("_type")
    require(statement_type in {
        "https://in-toto.io/Statement/v0.1",
        "https://in-toto.io/Statement/v1",
    })
    require(statement.get("predicateType") == "https://slsa.dev/provenance/v0.2")
    subjects = statement.get("subject")
    require(type(subjects) is list and len(subjects) == 1)
    require(type(subjects[0]) is dict and subjects[0].get("digest") == {"sha256": profile["derivative_digest"][7:]})
    require(type(subjects[0].get("name")) is str and unquote(subjects[0]["name"]).startswith("pkg:docker/ghcr.io/rozkalnsandris/coloring-pages-origin@"))
    require(unquote(subjects[0]["name"]).endswith("?platform=linux/arm64"))
    predicate = statement.get("predicate")
    require(type(predicate) is dict and predicate.get("buildType") == "https://mobyproject.org/buildkit@v1")
    invocation = predicate.get("invocation")
    require(type(invocation) is dict)
    source = invocation.get("configSource")
    require(type(source) is dict)
    require(source.get("uri") == "https://github.com/rozkalnsandris/coloring-pages.git#" + profile["recipe_source_sha"])
    require(source.get("digest") == {"sha1": profile["recipe_source_sha"]})
    require(source.get("entryPoint") == "deploy/Dockerfile.origin-counting")
    parameters = invocation.get("parameters")
    require(type(parameters) is dict and type(parameters.get("args")) is dict)
    require(parameters["args"].get("build-arg:APPLICATION_IMAGE") == f"ghcr.io/{sd.ORIGIN_REPOSITORY}@{profile['base_digest']}")
    materials = predicate.get("materials")
    require(type(materials) is list)
    if statement_type == "https://in-toto.io/Statement/v0.1":
        # Preserve the accepted legacy platform-manifest material contract.
        base = [m for m in materials if type(m) is dict and type(m.get("uri")) is str and unquote(m["uri"]) ==
                "pkg:docker/ghcr.io/rozkalnsandris/coloring-pages@" + profile["base_digest"] + "?platform=linux/arm64"]
        require(len(base) == 1 and base[0].get("digest") == {"sha256": profile["base_platform_digest"][7:]})
    else:
        # Observed BuildKit Statement/v1 + SLSA v0.2: the material binds the
        # OCI base index. prepare() independently verifies its unique ARM64
        # descriptor against the profile's base_platform_digest.
        require(len(materials) == 2 and all(type(m) is dict and set(m) == {"uri", "digest"} for m in materials))
        expected_base = ("pkg:docker/ghcr.io/rozkalnsandris/coloring-pages?digest=" +
                         profile["base_digest"] + "&platform=linux%2Farm64")
        expected_recipe = ("https://github.com/rozkalnsandris/coloring-pages.git#" +
                           profile["recipe_source_sha"])
        base = [m for m in materials if m["uri"] == expected_base]
        recipe = [m for m in materials if m["uri"] == expected_recipe]
        require(len(base) == 1 and base[0]["digest"] == {"sha256": profile["base_digest"][7:]})
        require(len(recipe) == 1 and recipe[0]["digest"] == {"sha1": profile["recipe_source_sha"]})
    require(digest(statement) == profile["provenance_sha256"])


def validate_peer(peer, profile, now):
    keys = {"schema", "host", "observed_at", "image_ref", "container_uid", "container_primary_gid",
            "host_peer_uid", "host_peer_gid", "collector_allowed_uid", "collector_allowed_gid",
            "container_socket_group", "host_socket_gid", "mapped_socket_gid"}
    require(type(peer) is dict and set(peer) == keys)
    require(peer["schema"] == "rozkalns.origin-peer-evidence.v1" and peer["host"] == "rpi5")
    require(peer["image_ref"] == f"{sd.ORIGIN_IMAGE}@{profile['derivative_digest']}")
    require(peer["container_uid"] == 101 and type(peer["container_uid"]) is int)
    require(peer["container_socket_group"] == profile["socket_group"])
    for key in ("container_primary_gid", "host_peer_uid", "host_peer_gid", "collector_allowed_uid",
                "collector_allowed_gid", "host_socket_gid", "mapped_socket_gid"):
        require(type(peer[key]) is int and 1 <= peer[key] <= 4294967294)
    require(peer["host_peer_uid"] == peer["collector_allowed_uid"])
    require(peer["host_peer_gid"] == peer["collector_allowed_gid"])
    require(peer["mapped_socket_gid"] == peer["host_socket_gid"])
    require(type(peer["observed_at"]) is str and len(peer["observed_at"]) == 20)
    observed = datetime.strptime(peer["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    require(0 <= (now - observed).total_seconds() <= 86400)
    require(digest(peer) == profile["peer_evidence_sha256"])


def prepare(request, registry_bytes, base_compose_bytes, *, source_sha, now):
    require(type(request) is dict and set(request) == {
        "schema", "rpi_source_sha", "registry_sha256", "profile", "base_config",
        "derivative_config", "provenance", "peer_evidence", "base_manifest_raw"})
    require(type(source_sha) is str and sd.SHA1_RE.fullmatch(source_sha) is not None)
    require(request["schema"] == "rozkalns.origin-preparation.v1" and request["rpi_source_sha"] == source_sha)
    require(hashlib.sha256(registry_bytes).hexdigest() == request["registry_sha256"])
    require(hashlib.sha256(base_compose_bytes).hexdigest() == sd.ORIGIN_BASE_COMPOSE_SHA256)
    registry = json.loads(registry_bytes, object_pairs_hook=unique_object)
    require(type(registry) is dict and set(registry) == sd.ROOT_KEYS)
    require(registry["schema"] == sd.REGISTRY_SCHEMA and type(registry["schema_version"]) is int and registry["schema_version"] == 1)
    require(type(registry["execution_enabled"]) is bool and type(registry["targets"]) is list)
    parsed = [sd._parse_target(t, i) for i, t in enumerate(registry["targets"])]
    require(len({t.target_alias for t in parsed}) == len(parsed))
    require(len({t.image for t in parsed}) == len(parsed))
    profile = sd.validate_origin_profile(request["profile"])
    indexes = [i for i, t in enumerate(parsed) if t.target_alias == sd.ORIGIN_TARGET]
    require(len(indexes) == 1)
    index = indexes[0]
    target = registry["targets"][index]
    # This command accepts canonical source, never an installed registry snapshot
    # or an in-place profile replacement. A next pair is rendered from source too.
    require("origin_counting" not in target)
    require(target["compose"]["file"] == "coloring-pages-public.yml")
    require(target["compose"]["file_sha256"] == sd.ORIGIN_BASE_COMPOSE_SHA256)
    sd.validate_origin_metadata(request["base_config"], profile, target["shared_workflow_sha"], derivative=False)
    sd.validate_origin_metadata(request["derivative_config"], profile, target["shared_workflow_sha"], derivative=True)
    raw_manifest = request["base_manifest_raw"]
    require(type(raw_manifest) is str)
    require("sha256:" + hashlib.sha256(raw_manifest.encode()).hexdigest() == profile["base_digest"])
    manifest = json.loads(raw_manifest, object_pairs_hook=unique_object)
    require(type(manifest) is dict and manifest.get("schemaVersion") == 2)
    if manifest.get("mediaType") in {"application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json"}:
        require(type(manifest.get("manifests")) is list)
        matches = [m for m in manifest["manifests"] if type(m) is dict and type(m.get("platform")) is dict
                   and m["platform"].get("os") == "linux" and m["platform"].get("architecture") == "arm64"
                   and m["platform"].get("variant", "v8") == "v8"]
        require(len(matches) == 1 and matches[0].get("digest") == profile["base_platform_digest"])
    else:
        require(manifest.get("mediaType") in {"application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"})
        require(profile["base_platform_digest"] == profile["base_digest"])
    validate_provenance(request["provenance"], profile)
    validate_peer(request["peer_evidence"], profile, now)
    compose = sd.render_origin_compose(profile)
    prepared = copy.deepcopy(registry)
    changed = prepared["targets"][index]
    changed["origin_counting"] = profile
    changed["compose"]["file"] = "coloring-pages-origin.json.yml"
    changed["compose"]["file_sha256"] = hashlib.sha256(compose).hexdigest()
    sd._parse_target(changed, index)
    return {
        "schema": "rozkalns.origin-prepared-bundle.v1", "rpi_source_sha": source_sha,
        "runtime_authority": False, "activation": "NOT_PERFORMED",
        "profile_sha256": sd.origin_profile_sha256(profile),
        "registry": prepared, "compose": compose.decode(),
        "compose_sha256": changed["compose"]["file_sha256"],
    }


def read_request(path, expected_sha):
    require(type(expected_sha) is str and sd.re.fullmatch(r"[0-9a-f]{64}", expected_sha) is not None)
    # No symlink, FIFO/device or unbounded reads. No source output overwrites.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= 262144)
        data = handle.read(262145)
    require(len(data) <= 262144 and hashlib.sha256(data).hexdigest() == expected_sha)
    return json.loads(data, object_pairs_hook=unique_object)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    try:
        require(os.geteuid() != 0)
        request = read_request(args.request, args.request_sha256)
        result = prepare(request,
            (ROOT / "ops/deploy/simple-deploy-targets-v1.json").read_bytes(),
            (ROOT / "ops/deploy/simple-deploy-compose/coloring-pages-public.yml").read_bytes(),
            source_sha=args.source_sha, now=datetime.now(timezone.utc))
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, sd.SimpleDeployError):
        print("ORIGIN_PREPARATION_REFUSED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
