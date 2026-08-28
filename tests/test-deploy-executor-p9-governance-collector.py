#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import p9_governance_collector as collector
from deploy_executor import p9_producer as producer

NOW = datetime(2026, 8, 28, 21, 0, tzinfo=timezone.utc)
SYNTHETIC_COMMIT = "a" * 40


def source_blobs(files: dict[str, str | bytes]) -> tuple[collector.SourceBlob, ...]:
    blobs = []
    for path, content in files.items():
        raw = content if isinstance(content, bytes) else content.encode("utf-8")
        blobs.append(collector.SourceBlob(path=path, mode="100644", content=raw))
    return tuple(blobs)


def fixture(
    *,
    workflow_text: str | None = None,
    script_text: str = "print('safe')\n",
):
    if workflow_text is None:
        workflow_text = (
            "name: synthetic\n"
            "on: push\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs: {}\n"
        )
    files = {
        ".github/workflows/a.yml": workflow_text,
        "scripts/tool.py": script_text,
    }
    blobs = source_blobs(files)
    index = collector._source_blob_index(blobs)
    tree_sha = collector._git_tree_sha(index)
    workflow_blob = index[".github/workflows/a.yml"][1]
    source = collector.AuthorizationSourceSnapshot(
        repository=producer.AUTHORIZATION_REPOSITORY,
        repository_id=producer.AUTHORIZATION_REPOSITORY_ID,
        owner_type="User",
        owner_id=collector.AUTHORIZATION_OWNER_ID,
        commit_sha=SYNTHETIC_COMMIT,
        tree_sha=tree_sha,
        tree_complete=True,
        blobs=blobs,
    )
    collaborators = collector.CollaboratorSurface(
        complete=True,
        provenance=collector.COLLABORATOR_PROVENANCE,
        entries=(
            collector.CollaboratorAccess(
                user_id=collector.AUTHORIZATION_OWNER_ID,
                login="owner",
                permission="admin",
            ),
            collector.CollaboratorAccess(
                user_id=200,
                login="reader",
                permission="read",
            ),
            collector.CollaboratorAccess(
                user_id=300,
                login="writer",
                permission="push",
            ),
        ),
    )
    teams = collector.TeamSurface(
        complete=True,
        provenance=collector.TEAM_PROVENANCE,
        entries=(),
    )
    apps = collector.InstalledAppSurface(
        complete=True,
        provenance=collector.APP_INTEGRATION_PROVENANCE,
        entries=(
            collector.InstalledIntegrationAccess(
                integration_type="github-app",
                integration_id=10,
                slug="reader-app",
                issues_permission="read",
            ),
            collector.InstalledIntegrationAccess(
                integration_type="github-app",
                integration_id=11,
                slug="writer-app",
                issues_permission="write",
            ),
        ),
    )
    return source, collaborators, teams, apps, tree_sha, workflow_blob


def collect(
    *,
    source=None,
    collaborators=None,
    teams=None,
    apps=None,
    workflow_text: str | None = None,
    script_text: str = "print('safe')\n",
):
    base_source, base_collaborators, base_teams, base_apps, tree_sha, workflow_blob = fixture(
        workflow_text=workflow_text,
        script_text=script_text,
    )
    source = base_source if source is None else source
    collaborators = base_collaborators if collaborators is None else collaborators
    teams = base_teams if teams is None else teams
    apps = base_apps if apps is None else apps
    with mock.patch.object(
        collector, "PINNED_AUTHORIZATION_SOURCE_SHA", SYNTHETIC_COMMIT
    ), mock.patch.object(
        collector, "PINNED_AUTHORIZATION_SOURCE_TREE_SHA", tree_sha
    ), mock.patch.object(
        collector,
        "PINNED_WORKFLOW_BLOBS",
        {".github/workflows/a.yml": workflow_blob},
    ):
        return collector.collect_governance_writer_surface(
            collector.GovernanceCollectionInput(
                observed_at=NOW,
                source=source,
                collaborators=collaborators,
                teams=teams,
                installed_apps=apps,
            )
        )


def expect_error(func, contains: str) -> None:
    try:
        func()
    except collector.P9GovernanceCollectorError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(
            f"expected P9GovernanceCollectorError containing {contains!r}"
        )


def test_git_object_hashes_match_known_git_values() -> None:
    assert collector._git_blob_sha(b"test\n") == "9daeafb9864cf43055ae93beb0afd6c7d144bfa4"
    blobs = (
        collector.SourceBlob("a.txt", "100644", b"hello\n"),
        collector.SourceBlob("foo/bar", "100755", b"x"),
        collector.SourceBlob("foo.baz", "100644", b"z"),
    )
    assert (
        collector._git_tree_sha(collector._source_blob_index(blobs))
        == "fb6d40be8071c3000d9831bc8f0380ae772a74e6"
    )


def test_valid_collection_normalizes_only_effective_writers() -> None:
    observation = collect()
    assert observation.covered_surfaces == producer._REQUIRED_GOVERNANCE_SURFACES
    assert observation.human_writers == (
        f"user:{collector.AUTHORIZATION_OWNER_ID}",
        "user:300",
    )
    assert observation.team_writers == ()
    assert observation.app_writers == ("app:11",)
    assert observation.workflow_writers == ()
    assert observation.token_writers == ()
    assert observation.unknown_writers == ()
    digest = producer.governance_writer_set_sha256(observation)
    assert len(digest) == 64


def test_source_commit_pin_drift_is_rejected() -> None:
    source, collaborators, teams, apps, _, _ = fixture()
    expect_error(
        lambda: collect(
            source=replace(source, commit_sha="b" * 40),
            collaborators=collaborators,
            teams=teams,
            apps=apps,
        ),
        "source-pinned",
    )


def test_incomplete_or_tampered_source_tree_is_rejected() -> None:
    source, collaborators, teams, apps, _, _ = fixture()
    expect_error(
        lambda: collect(
            source=replace(source, tree_complete=False),
            collaborators=collaborators,
            teams=teams,
            apps=apps,
        ),
        "incomplete",
    )
    tampered = replace(
        source,
        blobs=source.blobs
        + (collector.SourceBlob("extra.txt", "100644", b"unexpected\n"),),
    )
    expect_error(
        lambda: collect(
            source=tampered,
            collaborators=collaborators,
            teams=teams,
            apps=apps,
        ),
        "tree content mismatch",
    )


def test_non_utf8_source_is_rejected_as_uninspectable() -> None:
    source, collaborators, teams, apps, _, _ = fixture()
    bad = replace(
        source,
        blobs=(
            collector.SourceBlob(
                ".github/workflows/a.yml",
                "100644",
                b"name: bad\npermissions:\n  contents: read\n\xff",
            ),
            source.blobs[1],
        ),
    )
    expect_error(
        lambda: collect(
            source=bad,
            collaborators=collaborators,
            teams=teams,
            apps=apps,
        ),
        "non-UTF-8",
    )


def test_workflow_requires_explicit_top_level_permissions() -> None:
    expect_error(
        lambda: collect(workflow_text="name: unsafe\non: push\njobs: {}\n"),
        "explicit top-level permissions",
    )


def test_job_level_issues_write_is_collected_as_workflow_writer() -> None:
    observation = collect(
        workflow_text=(
            "name: writer\n"
            "on: push\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  writer:\n"
            "    permissions:\n"
            "      issues: write\n"
        )
    )
    assert len(observation.workflow_writers) == 1
    assert observation.workflow_writers[0].startswith("workflow:.github/workflows/a.yml@")


def test_write_all_is_collected_as_workflow_writer() -> None:
    observation = collect(
        workflow_text=(
            "name: writer\n"
            "on: push\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  writer:\n"
            "    permissions: write-all\n"
        )
    )
    assert len(observation.workflow_writers) == 1


def test_issue_mutation_source_is_collected_as_token_writer() -> None:
    observation = collect(
        script_text=(
            "import subprocess\n"
            "subprocess.run(['gh', 'issue', 'comment', '1', '--body', 'x'])\n"
        )
    )
    assert len(observation.token_writers) == 1
    assert observation.token_writers[0].startswith("token-source:scripts/tool.py@")


def test_collaborator_surface_must_be_complete_and_include_owner() -> None:
    source, collaborators, teams, apps, _, _ = fixture()
    expect_error(
        lambda: collect(
            source=source,
            collaborators=replace(collaborators, complete=False),
            teams=teams,
            apps=apps,
        ),
        "collaborator writer surface is incomplete",
    )
    expect_error(
        lambda: collect(
            source=source,
            collaborators=replace(
                collaborators,
                entries=tuple(
                    entry
                    for entry in collaborators.entries
                    if entry.user_id != collector.AUTHORIZATION_OWNER_ID
                ),
            ),
            teams=teams,
            apps=apps,
        ),
        "owner is missing",
    )


def test_user_owned_authorization_repo_requires_empty_team_surface() -> None:
    source, collaborators, teams, apps, _, _ = fixture()
    expect_error(
        lambda: collect(
            source=source,
            collaborators=collaborators,
            teams=replace(
                teams,
                entries=(collector.TeamAccess(1, "unexpected", "write"),),
            ),
            apps=apps,
        ),
        "team writer surface must be empty",
    )


def test_installed_app_surface_must_be_complete() -> None:
    source, collaborators, teams, apps, _, _ = fixture()
    expect_error(
        lambda: collect(
            source=source,
            collaborators=collaborators,
            teams=teams,
            apps=replace(apps, complete=False),
        ),
        "App/integration writer surface is incomplete",
    )


def test_unknown_integration_type_or_permission_fails_closed() -> None:
    source, collaborators, teams, apps, _, _ = fixture()
    expect_error(
        lambda: collect(
            source=source,
            collaborators=collaborators,
            teams=teams,
            apps=replace(
                apps,
                entries=(
                    collector.InstalledIntegrationAccess(
                        "mystery", 99, "unknown", "write"
                    ),
                ),
            ),
        ),
        "integration type is unknown",
    )
    expect_error(
        lambda: collect(
            source=source,
            collaborators=collaborators,
            teams=teams,
            apps=replace(
                apps,
                entries=(
                    collector.InstalledIntegrationAccess(
                        "github-app", 99, "unknown", "admin"
                    ),
                ),
            ),
        ),
        "Issues permission is unknown",
    )


def test_oauth_or_other_integration_writer_identity_is_distinct() -> None:
    source, collaborators, teams, apps, _, _ = fixture()
    alternate = replace(
        apps,
        entries=(
            collector.InstalledIntegrationAccess(
                "oauth-app", 77, "oauth-writer", "write"
            ),
            collector.InstalledIntegrationAccess(
                "integration", 88, "integration-writer", "write"
            ),
        ),
    )
    observation = collect(
        source=source,
        collaborators=collaborators,
        teams=teams,
        apps=alternate,
    )
    assert observation.app_writers == ("integration:88", "oauth-app:77")


def main() -> None:
    tests = [
        value
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    for test in sorted(tests, key=lambda fn: fn.__name__):
        test()
    print(f"P9_GOVERNANCE_COLLECTOR_TESTS=PASS count={len(tests)}")


if __name__ == "__main__":
    main()
