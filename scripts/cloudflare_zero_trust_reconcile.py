#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_API_BASE = "https://api.cloudflare.com/client/v4"
EXPECTED_TUNNEL_NAME = "rpi5-tunnel"
ACCOUNT_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
TUNNEL_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
APP_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
ALLOWED_TRUST_CLASSES = {"PUBLIC", "FAMILY_PRIVATE", "ADMIN"}
ALLOWED_ROUTE_EXPECTATIONS = {"present", "absent", "not-applicable"}
SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9._ /-]{1,96}$")


class AuditError(RuntimeError):
    """Fail-closed audit error with a public-safe reason code."""


@dataclass(frozen=True)
class RegistryHost:
    hostname: str
    delivery: str
    trust_class: str
    desired_origin_scope: str
    access_application_scope: str
    protect_with_access: str
    lan_break_glass: bool
    audit_route_presence: str


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class CloudflareGetClient:
    """Minimal Cloudflare API client whose only operation is HTTP GET."""

    def __init__(self, api_token: str, api_base: str = DEFAULT_API_BASE, timeout: int = 20) -> None:
        if len(api_token) < 20 or any(ch.isspace() for ch in api_token):
            raise AuditError("missing_or_invalid_api_token")
        parsed = urllib.parse.urlparse(api_base)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise AuditError("invalid_api_base")
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
            raise AuditError("non_https_api_base_forbidden")
        self._api_token = api_token
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout
        self._opener = urllib.request.build_opener(NoRedirect)

    def get(self, path: str, query: dict[str, str | int] | None = None) -> dict[str, Any]:
        if not path.startswith("/") or "://" in path:
            raise AuditError("invalid_api_path")
        url = f"{self._api_base}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_token}",
                "User-Agent": "rpi5-main-cloudflare-p0-179",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise AuditError(f"cloudflare_api_http_{exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AuditError("cloudflare_api_request_failed") from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise AuditError("cloudflare_api_unsuccessful")
        return payload


def _parse_scalar(raw: str) -> str | bool:
    value = raw.strip()
    if value in {"true", "false"}:
        return value == "true"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_registry(path: Path) -> dict[str, RegistryHost]:
    """Parse only the deliberately small hostnames list from our canonical YAML.

    This is intentionally not a general YAML parser, avoiding a runtime PyYAML dependency.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AuditError("registry_read_failed") from exc

    in_hostnames = False
    current: dict[str, str | bool] | None = None
    rows: list[dict[str, str | bool]] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw_line == "hostnames:":
            in_hostnames = True
            continue
        if not in_hostnames:
            continue
        if not raw_line.startswith(" "):
            break
        if raw_line.startswith("  - hostname:"):
            if current is not None:
                rows.append(current)
            current = {"hostname": _parse_scalar(raw_line.split(":", 1)[1])}
            continue
        if current is None:
            continue
        match = re.match(r"^    ([a-zA-Z0-9_]+):\s*(.*?)\s*$", raw_line)
        if match:
            current[match.group(1)] = _parse_scalar(match.group(2))
    if current is not None:
        rows.append(current)

    if not rows:
        raise AuditError("registry_hostnames_missing")

    required = {
        "hostname",
        "delivery",
        "trust_class",
        "desired_origin_scope",
        "access_application_scope",
        "protect_with_access",
        "lan_break_glass",
        "audit_route_presence",
    }
    result: dict[str, RegistryHost] = {}
    for row in rows:
        missing = required - row.keys()
        if missing:
            raise AuditError("registry_host_field_missing")
        hostname = str(row["hostname"]).lower()
        if not re.fullmatch(r"(?:\*\.)?[a-z0-9.-]+", hostname):
            raise AuditError("registry_hostname_invalid")
        if hostname in result:
            raise AuditError("registry_hostname_duplicate")
        trust_class = str(row["trust_class"])
        if trust_class not in ALLOWED_TRUST_CLASSES:
            raise AuditError("registry_trust_class_invalid")
        route_presence = str(row["audit_route_presence"])
        if route_presence not in ALLOWED_ROUTE_EXPECTATIONS:
            raise AuditError("registry_route_presence_invalid")
        protect = str(row["protect_with_access"]).lower()
        if protect not in {"true", "false", "not-applicable"}:
            raise AuditError("registry_protect_with_access_invalid")
        lan_break_glass = row["lan_break_glass"]
        if not isinstance(lan_break_glass, bool):
            raise AuditError("registry_lan_break_glass_invalid")
        result[hostname] = RegistryHost(
            hostname=hostname,
            delivery=str(row["delivery"]),
            trust_class=trust_class,
            desired_origin_scope=str(row["desired_origin_scope"]),
            access_application_scope=str(row["access_application_scope"]),
            protect_with_access=protect,
            lan_break_glass=lan_break_glass,
            audit_route_presence=route_presence,
        )
    return result


def _unwrap_dict(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AuditError(reason)
    return result


def _list_all(client: CloudflareGetClient, path: str) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while page <= 100:
        payload = client.get(path, {"page": page, "per_page": 100})
        result = payload.get("result")
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise AuditError("cloudflare_list_shape_invalid")
        items.extend(result)
        result_info = payload.get("result_info")
        total_pages = result_info.get("total_pages") if isinstance(result_info, dict) else None
        if isinstance(total_pages, int):
            if page >= total_pages:
                return items
        elif len(result) < 100:
            return items
        page += 1
    raise AuditError("cloudflare_pagination_limit_exceeded")


def collect_state(
    client: CloudflareGetClient,
    account_id: str,
    tunnel_id: str,
) -> dict[str, Any]:
    token = _unwrap_dict(client.get("/user/tokens/verify"), "token_verify_shape_invalid")
    if token.get("status") != "active":
        raise AuditError("api_token_not_active")

    organization = _unwrap_dict(
        client.get(f"/accounts/{account_id}/access/organizations"),
        "organization_shape_invalid",
    )

    apps = _list_all(client, f"/accounts/{account_id}/access/apps")
    policies: dict[str, list[dict[str, Any]]] = {}
    for app in apps:
        app_id = app.get("id")
        if not isinstance(app_id, str) or not APP_ID_RE.fullmatch(app_id):
            raise AuditError("access_application_id_invalid")
        policies[app_id] = _list_all(
            client, f"/accounts/{account_id}/access/apps/{app_id}/policies"
        )

    tunnel = _unwrap_dict(
        client.get(f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}"),
        "tunnel_shape_invalid",
    )
    if tunnel.get("name") != EXPECTED_TUNNEL_NAME:
        raise AuditError("tunnel_name_mismatch")
    if tunnel.get("config_src") != "cloudflare":
        raise AuditError("tunnel_not_remotely_managed")

    configuration = _unwrap_dict(
        client.get(f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"),
        "tunnel_configuration_shape_invalid",
    )
    config = configuration.get("config")
    if not isinstance(config, dict):
        raise AuditError("tunnel_config_missing")

    return {
        "organization": organization,
        "apps": apps,
        "policies": policies,
        "tunnel": tunnel,
        "config": config,
    }


def _application_domains(app: dict[str, Any]) -> list[str]:
    values: list[str] = []
    domain = app.get("domain")
    if isinstance(domain, str) and domain.strip():
        values.append(domain.strip())
    destinations = app.get("destinations")
    if isinstance(destinations, list):
        for item in destinations:
            if isinstance(item, dict):
                uri = item.get("uri")
                if isinstance(uri, str) and uri.strip():
                    values.append(uri.strip())
    return list(dict.fromkeys(values))


def _split_app_domain(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urllib.parse.urlparse(candidate)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    return host, path


def _host_pattern_matches(pattern: str, hostname: str) -> bool:
    if not pattern:
        return False
    labels = pattern.split(".")
    regex_labels = []
    for label in labels:
        regex_labels.append(re.escape(label).replace(r"\*", r"[^.]*"))
    regex = r"^" + r"\.".join(regex_labels) + r"$"
    return re.fullmatch(regex, hostname, flags=re.IGNORECASE) is not None


def _root_path_matches(path: str) -> bool:
    return path in {"", "/", "/*"}


def _domain_specificity(domain: str, hostname: str) -> tuple[int, int, int] | None:
    pattern, path = _split_app_domain(domain)
    if not _root_path_matches(path) or not _host_pattern_matches(pattern, hostname):
        return None
    exact = 1 if "*" not in pattern else 0
    literal_chars = len(pattern.replace("*", ""))
    labels = pattern.count(".") + 1
    return exact, literal_chars, labels


def resolve_application(apps: list[dict[str, Any]], hostname: str) -> dict[str, Any]:
    matches: list[tuple[tuple[int, int, int], dict[str, Any], str]] = []
    for app in apps:
        for domain in _application_domains(app):
            score = _domain_specificity(domain, hostname)
            if score is not None:
                matches.append((score, app, domain))
    if not matches:
        return {"status": "none", "selected": None, "matching_domains": []}

    best_score = max(score for score, _, _ in matches)
    best = [(app, domain) for score, app, domain in matches if score == best_score]
    unique_ids = {str(app.get("id")) for app, _ in best}
    if len(unique_ids) != 1:
        return {
            "status": "ambiguous",
            "selected": None,
            "matching_domains": sorted({domain for _, domain in best}),
        }
    selected_app = best[0][0]
    selected_domains = [domain for app, domain in best if app is selected_app]
    selected_domain = max(
        selected_domains,
        key=lambda d: _domain_specificity(d, hostname) or (0, 0, 0),
    )
    pattern, _ = _split_app_domain(selected_domain)
    return {
        "status": "exact" if "*" not in pattern else "wildcard",
        "selected": selected_app,
        "selected_domain": selected_domain,
        "matching_domains": sorted({domain for _, _, domain in matches}),
    }


def _selector_summary(policy: dict[str, Any]) -> dict[str, Any]:
    selector_types: set[str] = set()
    counts: dict[str, int] = {}
    phases: dict[str, list[str]] = {}
    for phase in ("include", "require", "exclude"):
        rules = policy.get(phase)
        phase_types: set[str] = set()
        if isinstance(rules, list):
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                for key in rule.keys():
                    selector_types.add(key)
                    phase_types.add(key)
                    counts[key] = counts.get(key, 0) + 1
        phases[phase] = sorted(phase_types)
    return {
        "types": sorted(selector_types),
        "counts": {key: counts[key] for key in sorted(counts)},
        "phases": phases,
    }


def sanitize_policy(policy: dict[str, Any]) -> dict[str, Any]:
    action = policy.get("decision", policy.get("action"))
    if not isinstance(action, str):
        action = "unknown"
    precedence = policy.get("precedence")
    return {
        "action": action.lower(),
        "precedence": precedence if isinstance(precedence, int) else None,
        "selectors": _selector_summary(policy),
    }


def _safe_app_name(app: dict[str, Any]) -> str | None:
    name = app.get("name")
    if isinstance(name, str) and "@" not in name and SAFE_LABEL_RE.fullmatch(name):
        return name
    return None


def sanitize_application(
    app: dict[str, Any],
    policies: list[dict[str, Any]],
) -> dict[str, Any]:
    domains = []
    for domain in _application_domains(app):
        host, path = _split_app_domain(domain)
        if host:
            domains.append(host + path)
    return {
        "name": _safe_app_name(app),
        "type": app.get("type") if isinstance(app.get("type"), str) else "unknown",
        "domains": sorted(set(domains)),
        "session_duration": (
            app.get("session_duration") if isinstance(app.get("session_duration"), str) else None
        ),
        "allow_authenticate_via_warp": (
            app.get("allow_authenticate_via_warp")
            if isinstance(app.get("allow_authenticate_via_warp"), bool)
            else None
        ),
        "aud_present": bool(app.get("aud")),
        "policies": [sanitize_policy(policy) for policy in policies],
    }


def _private_ip_class(host: str) -> str:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "hostname"
    if ip.is_loopback:
        return "loopback"
    if ip.is_private:
        return "private-lan"
    return "public-ip"


def classify_service(service: Any) -> str:
    if not isinstance(service, str):
        return "invalid"
    if service.startswith("http_status:"):
        return "http-status"
    parsed = urllib.parse.urlparse(service)
    if parsed.scheme in {"http", "https", "tcp", "ssh", "rdp", "smb"}:
        host = (parsed.hostname or "").lower()
        if host == "localhost":
            return "loopback"
        return _private_ip_class(host)
    if parsed.scheme in {"unix", "unix+tls"}:
        return "unix-socket"
    return "other"


def _origin_access(config: dict[str, Any], ingress: dict[str, Any]) -> dict[str, Any]:
    access: dict[str, Any] | None = None
    local_origin = ingress.get("originRequest")
    if isinstance(local_origin, dict) and isinstance(local_origin.get("access"), dict):
        access = local_origin["access"]
    if access is None:
        global_origin = config.get("originRequest")
        if isinstance(global_origin, dict) and isinstance(global_origin.get("access"), dict):
            access = global_origin["access"]
    if access is None:
        return {
            "present": False,
            "required": False,
            "aud_tag_count": 0,
            "team_name_present": False,
        }
    aud = access.get("audTag")
    team_name = access.get("teamName")
    return {
        "present": True,
        "required": access.get("required") is True,
        "aud_tag_count": len(aud) if isinstance(aud, list) else 0,
        "team_name_present": isinstance(team_name, str) and bool(team_name),
        "_team_name": team_name if isinstance(team_name, str) else None,
    }


def _build_route_inventory(
    config: dict[str, Any],
    registry: dict[str, RegistryHost],
    organization: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    ingress = config.get("ingress")
    if not isinstance(ingress, list) or not ingress:
        raise AuditError("tunnel_ingress_missing")
    routes: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    catchalls: list[tuple[int, dict[str, Any]]] = []
    auth_domain = organization.get("auth_domain")
    expected_team = None
    if isinstance(auth_domain, str) and auth_domain:
        expected_team = auth_domain.split(".", 1)[0]

    for index, item in enumerate(ingress):
        if not isinstance(item, dict):
            raise AuditError("tunnel_ingress_entry_invalid")
        hostname = item.get("hostname")
        if hostname is None:
            catchalls.append((index, item))
            continue
        if not isinstance(hostname, str):
            raise AuditError("tunnel_ingress_hostname_invalid")
        hostname = hostname.lower()
        if hostname in routes:
            blockers.append(f"duplicate_tunnel_route:{hostname}")
            continue
        access = _origin_access(config, item)
        team_name = access.pop("_team_name", None)
        access["team_name_matches_organization"] = (
            bool(expected_team)
            and isinstance(team_name, str)
            and team_name == expected_team
        ) if access["present"] else None
        routes[hostname] = {
            "origin_class": classify_service(item.get("service")),
            "protect_with_access": access,
        }
        if hostname not in registry:
            blockers.append(f"unclassified_tunnel_hostname:{hostname}")

    if len(catchalls) != 1:
        blockers.append("tunnel_catchall_count_mismatch")
    else:
        index, item = catchalls[0]
        if index != len(ingress) - 1 or item.get("service") != "http_status:404":
            blockers.append("tunnel_catchall_contract_mismatch")
    return routes, blockers


def _policy_actions(policies: Iterable[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for policy in policies:
        action = policy.get("decision", policy.get("action"))
        if isinstance(action, str):
            result.add(action.lower())
    return result


def _selector_types_for_action(
    policies: Iterable[dict[str, Any]], action: str, phase: str | None = None
) -> set[str]:
    result: set[str] = set()
    for policy in policies:
        current = policy.get("decision", policy.get("action"))
        if not isinstance(current, str) or current.lower() != action:
            continue
        summary = _selector_summary(policy)
        if phase is None:
            result.update(summary["types"])
        else:
            result.update(summary["phases"].get(phase, []))
    return result


def _exact_email_selector_count(policies: Iterable[dict[str, Any]]) -> int:
    count = 0
    for policy in policies:
        current = policy.get("decision", policy.get("action"))
        if not isinstance(current, str) or current.lower() != "allow":
            continue
        include = policy.get("include")
        if not isinstance(include, list):
            continue
        for rule in include:
            if isinstance(rule, dict) and "email" in rule:
                count += 1
    return count


def build_report(
    registry: dict[str, RegistryHost],
    state: dict[str, Any],
) -> dict[str, Any]:
    organization = state["organization"]
    apps = state["apps"]
    policies_by_app = state["policies"]
    tunnel = state["tunnel"]
    config = state["config"]

    routes, blockers = _build_route_inventory(config, registry, organization)
    drift: list[str] = []
    host_reports: list[dict[str, Any]] = []

    for hostname, desired in sorted(registry.items()):
        resolved = resolve_application(apps, hostname)
        selected = resolved.get("selected")
        selected_policies: list[dict[str, Any]] = []
        if isinstance(selected, dict):
            app_id = selected.get("id")
            if isinstance(app_id, str):
                selected_policies = policies_by_app.get(app_id, [])

        observed_access: dict[str, Any] = {
            "resolution": resolved["status"],
            "selected_domain": resolved.get("selected_domain"),
            "matching_domain_count": len(resolved["matching_domains"]),
            "selected_application": (
                sanitize_application(selected, selected_policies)
                if isinstance(selected, dict)
                else None
            ),
        }

        if resolved["status"] == "ambiguous":
            blockers.append(f"ambiguous_access_application:{hostname}")

        scope = desired.access_application_scope
        if scope == "none":
            if resolved["status"] != "none":
                blockers.append(f"public_hostname_has_access_application:{hostname}")
        else:
            if resolved["status"] == "none":
                blockers.append(f"access_application_missing:{hostname}")
            elif scope == "exact-owner" and resolved["status"] != "exact":
                blockers.append(f"exact_access_application_missing:{hostname}")

        if selected_policies:
            actions = _policy_actions(selected_policies)
            if desired.trust_class in {"ADMIN", "FAMILY_PRIVATE"} and "bypass" in actions:
                blockers.append(f"matching_access_application_has_bypass:{hostname}")
            if scope == "exact-owner" and "service_auth" in actions:
                blockers.append(f"human_exact_app_has_service_auth:{hostname}")
            allow_selectors = _selector_types_for_action(selected_policies, "allow")
            allow_include_selectors = _selector_types_for_action(
                selected_policies, "allow", "include"
            )
            allow_require_selectors = _selector_types_for_action(
                selected_policies, "allow", "require"
            )
            if "everyone" in allow_include_selectors:
                blockers.append(f"allow_everyone_selector:{hostname}")
            if "login_method" in allow_include_selectors:
                blockers.append(f"broad_login_method_allow:{hostname}")
            if scope == "exact-owner":
                if _exact_email_selector_count(selected_policies) != 1:
                    blockers.append(f"exact_owner_email_selector_count_mismatch:{hostname}")
                if "email_domain" in allow_selectors:
                    blockers.append(f"exact_owner_email_domain_forbidden:{hostname}")
                if "device_posture" not in allow_require_selectors:
                    drift.append(f"owner_phone_posture_not_present:{hostname}")

        route = routes.get(hostname)
        route_observed: dict[str, Any] | None = route
        if desired.delivery == "shared_rpi5_tunnel":
            if desired.audit_route_presence == "present" and route is None:
                blockers.append(f"expected_tunnel_route_missing:{hostname}")
            elif desired.audit_route_presence == "absent" and route is not None:
                blockers.append(f"unexpected_tunnel_route_present:{hostname}")
        elif route is not None:
            blockers.append(f"non_tunnel_delivery_has_tunnel_route:{hostname}")

        if route is not None:
            origin_class = route["origin_class"]
            if desired.desired_origin_scope == "loopback" and origin_class != "loopback":
                blockers.append(f"origin_not_loopback:{hostname}")
            if (
                desired.desired_origin_scope == "explicit-lan-break-glass"
                and origin_class != "private-lan"
            ):
                blockers.append(f"break_glass_origin_not_private_lan:{hostname}")

            protect = route["protect_with_access"]
            if desired.protect_with_access == "true":
                if not (
                    protect.get("present") is True
                    and protect.get("required") is True
                    and protect.get("aud_tag_count", 0) >= 1
                    and protect.get("team_name_present") is True
                    and protect.get("team_name_matches_organization") is True
                ):
                    blockers.append(f"protect_with_access_not_proven:{hostname}")
            elif desired.protect_with_access == "false" and protect.get("required") is True:
                blockers.append(f"public_route_unexpectedly_requires_access:{hostname}")

        host_reports.append(
            {
                "hostname": hostname,
                "trust_class": desired.trust_class,
                "delivery": desired.delivery,
                "desired_origin_scope": desired.desired_origin_scope,
                "desired_access_application_scope": desired.access_application_scope,
                "audit_route_presence": desired.audit_route_presence,
                "access": observed_access,
                "route": route_observed,
            }
        )

    safe_apps = []
    for app in apps:
        app_id = app.get("id")
        safe_apps.append(
            sanitize_application(
                app,
                policies_by_app.get(app_id, []) if isinstance(app_id, str) else [],
            )
        )

    connections = tunnel.get("connections")
    report = {
        "schema_version": 1,
        "audit": "cloudflare-p0-readonly-reconciliation",
        "canonical_issue": 179,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result": "BLOCKED" if blockers else "PASS",
        "mutation_performed": False,
        "token": {"status": "active"},
        "organization": {
            "auth_domain_present": isinstance(organization.get("auth_domain"), str)
            and bool(organization.get("auth_domain")),
            "allow_authenticate_via_warp": (
                organization.get("allow_authenticate_via_warp")
                if isinstance(organization.get("allow_authenticate_via_warp"), bool)
                else None
            ),
            "session_duration": (
                organization.get("session_duration")
                if isinstance(organization.get("session_duration"), str)
                else None
            ),
        },
        "tunnel": {
            "name_matches": tunnel.get("name") == EXPECTED_TUNNEL_NAME,
            "config_src": tunnel.get("config_src"),
            "status": tunnel.get("status") if isinstance(tunnel.get("status"), str) else None,
            "connection_count": len(connections) if isinstance(connections, list) else None,
        },
        "applications": sorted(
            safe_apps,
            key=lambda app: (",".join(app["domains"]), app["name"] or ""),
        ),
        "hostnames": host_reports,
        "blockers": sorted(set(blockers)),
        "drift": sorted(set(drift)),
    }
    return report


def require_bindings() -> tuple[str, str, str]:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    tunnel_id = os.environ.get("CLOUDFLARE_TUNNEL_ID", "")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        raise AuditError("missing_or_invalid_account_id")
    if not TUNNEL_ID_RE.fullmatch(tunnel_id):
        raise AuditError("missing_or_invalid_tunnel_id")
    if len(api_token) < 20 or any(ch.isspace() for ch in api_token):
        raise AuditError("missing_or_invalid_api_token")
    return account_id, tunnel_id, api_token


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GET-only Cloudflare Zero Trust/Tunnel reconciliation for RPi5_main #179"
    )
    parser.add_argument(
        "--registry",
        default="ops/contracts/cloudflare-hostname-policy.yaml",
        help="Canonical public-safe hostname policy registry",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("CLOUDFLARE_API_BASE", DEFAULT_API_BASE),
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        account_id, tunnel_id, api_token = require_bindings()
        registry = load_registry(Path(args.registry))
        client = CloudflareGetClient(api_token, args.api_base)
        state = collect_state(client, account_id, tunnel_id)
        report = build_report(registry, state)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 3
    except AuditError as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "audit": "cloudflare-p0-readonly-reconciliation",
                    "canonical_issue": 179,
                    "result": "BLOCKED",
                    "mutation_performed": False,
                    "reason": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
