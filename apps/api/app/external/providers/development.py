"""Development platform provider — deterministic mock GitHub (Phase 10, §69).

An in-process mock GitHub workspace exposing repo + issue + comment
capabilities. Deterministic for tests/CI/demos. No auto-merge and no PR
creation/merge tooling in Phase 10: those are irreversible deployment-adjacent
capabilities the spec keeps behind strong gates (Phase 12 simulation / Phase 11
provider hardening). ``create_issue`` → ``get_issue`` verify pattern is exactly
what the Development Operations demo (§69) exercises.
"""

from __future__ import annotations

from typing import Any

from app.db.models.external import (
    AuthMethod,
    IntegrationCategory,
    Reversibility,
    RiskLevel,
)
from app.external.types import (
    AuthContext,
    Capability,
    ExternalAuthFailure,
    ExternalIssue,
    ExternalNotFoundFailure,
    ExternalValidationFailure,
)

API_KEY_ENV_HINT = "INTEGRATION_DEVELOPMENT_API_KEY"

_REPOS: dict[str, list[dict[str, Any]]] = {}
_ISSUES: dict[str, dict[str, ExternalIssue]] = {}
_COMMENTS: dict[str, dict[str, list[dict[str, Any]]]] = {}


def _seed_development(slug: str) -> None:
    if slug in _REPOS:
        return
    _REPOS[slug] = [
        {"id": "repo-001", "name": "nexus-core", "visibility": "private", "issues_open": 3},
        {"id": "repo-002", "name": "marketing-site", "visibility": "public", "issues_open": 1},
        {"id": "repo-003", "name": "prospect-dashboard", "visibility": "private", "issues_open": 0},
    ]
    _ISSUES[slug] = {
        "issue-001": ExternalIssue(
            id="issue-001",
            title="Add rate limiting to external HTTP",
            state="open",
            repository="nexus-core",
            number=42,
            labels=["security"],
        ),
        "issue-002": ExternalIssue(
            id="issue-002",
            title="Homepage hero copy refresh",
            state="open",
            repository="marketing-site",
            number=7,
            labels=["marketing"],
        ),
    }
    _COMMENTS[slug] = {}


class DevelopmentProvider:
    """Deterministic development-platform adapter over a mock GitHub workspace."""

    slug = "development"
    name = "Development Platform"
    category = IntegrationCategory.DEVELOPMENT
    auth_type = AuthMethod.API_KEY
    description = "Deterministic development-platform adapter over a mock workspace (Phase 10)."

    def __init__(self) -> None:
        _seed_development(self.slug)

    def secrets_required(self) -> list[str]:
        return [API_KEY_ENV_HINT]

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="list_repositories",
                description="List repositories the connection can access.",
                capability_type="read",
                risk_level=RiskLevel.LOW,
                reversibility=Reversibility.REVERSIBLE,
            ),
            Capability(
                name="get_repository",
                description="Fetch repository metadata by id.",
                capability_type="read",
                risk_level=RiskLevel.LOW,
                input_schema={"type": "object", "properties": {"repo_id": {"type": "string"}}},
                reversibility=Reversibility.REVERSIBLE,
            ),
            Capability(
                name="list_issues",
                description="List issues in a repository.",
                capability_type="read",
                risk_level=RiskLevel.LOW,
                input_schema={
                    "type": "object",
                    "properties": {"repository": {"type": "string"}, "state": {"type": "string"}},
                },
                reversibility=Reversibility.REVERSIBLE,
            ),
            Capability(
                name="get_issue",
                description="Fetch a single issue by id.",
                capability_type="read",
                risk_level=RiskLevel.LOW,
                input_schema={"type": "object", "properties": {"issue_id": {"type": "string"}}},
                reversibility=Reversibility.REVERSIBLE,
            ),
            Capability(
                name="create_issue",
                description="Create a new issue in a repository.",
                capability_type="write",
                risk_level=RiskLevel.MEDIUM,
                input_schema={
                    "type": "object",
                    "properties": {
                        "repository": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["repository", "title"],
                },
                reversibility=Reversibility.REVERSIBLE,
                supports_idempotency=True,
                required_permissions=["dev:write"],
                required_scopes=["repo:write"],
            ),
            Capability(
                name="update_issue",
                description="Update issue state or labels.",
                capability_type="write",
                risk_level=RiskLevel.MEDIUM,
                input_schema={
                    "type": "object",
                    "properties": {
                        "issue_id": {"type": "string"},
                        "state": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["issue_id"],
                },
                reversibility=Reversibility.REVERSIBLE,
                required_permissions=["dev:write"],
                required_scopes=["repo:write"],
            ),
            Capability(
                name="create_comment",
                description="Comment on an issue.",
                capability_type="write",
                risk_level=RiskLevel.MEDIUM,
                input_schema={
                    "type": "object",
                    "properties": {
                        "issue_id": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["issue_id", "body"],
                },
                reversibility=Reversibility.PARTIALLY_REVERSIBLE,
                supports_idempotency=True,
                required_permissions=["dev:write"],
            ),
        ]

    def test(
        self, *, payload: dict[str, Any], auth: AuthContext, context: dict[str, Any]
    ) -> tuple[str, str]:
        if not auth.secrets.get("api_key"):
            raise ExternalAuthFailure(
                "Development provider requires INTEGRATION_DEVELOPMENT_API_KEY"
            )
        return "connected", "Development workspace reachable (mock)."

    def execute(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        auth: AuthContext,
        connection: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not auth.secrets.get("api_key"):
            raise ExternalAuthFailure(
                "Development provider requires INTEGRATION_DEVELOPMENT_API_KEY"
            )
        if capability == "list_repositories":
            return {"repositories": _REPOS[self.slug]}
        if capability == "get_repository":
            return {"repository": _get_repo(payload, self.slug)}
        if capability == "list_issues":
            return {"issues": _list_issues(payload, self.slug)}
        if capability == "get_issue":
            return {"issue": _get_issue(payload, self.slug)}
        if capability == "create_issue":
            return {"issue": _create_issue(payload, self.slug)}
        if capability == "update_issue":
            return {"issue": _update_issue(payload, self.slug)}
        if capability == "create_comment":
            return {"comment": _create_comment(payload, self.slug)}
        raise ExternalValidationFailure(f"Unknown development capability {capability!r}")


def _get_repo(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    repo_id = str(payload.get("repo_id", ""))
    for repo in _REPOS[slug]:
        if repo["id"] == repo_id:
            return repo
    raise ExternalNotFoundFailure(f"Repository {repo_id!r} not found")


def _list_issues(payload: dict[str, Any], slug: str) -> list[dict[str, Any]]:
    repository = str(payload.get("repository", ""))
    state = str(payload.get("state", "open"))
    issues = []
    for issue in _ISSUES[slug].values():
        if repository and issue.repository != repository:
            continue
        if state and issue.state != state:
            continue
        issues.append(issue.to_dict())
    return issues


def _get_issue(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    issue_id = str(payload.get("issue_id", ""))
    issue = _ISSUES[slug].get(issue_id)
    if issue is None:
        raise ExternalNotFoundFailure(f"Issue {issue_id!r} not found")
    return issue.to_dict()


def _create_issue(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    repository = str(payload.get("repository", ""))
    title = str(payload.get("title", ""))
    if not repository or not title:
        raise ExternalValidationFailure("Issue requires repository and title")
    if repository not in {r["name"] for r in _REPOS[slug]}:
        raise ExternalNotFoundFailure(f"Repository {repository!r} not found")
    next_number = max((i.number for i in _ISSUES[slug].values()), default=0) + 1
    issue_id = f"issue-{len(_ISSUES[slug]) + 1:03d}"
    issue = ExternalIssue(
        id=issue_id,
        title=title,
        state="open",
        repository=repository,
        number=next_number,
        body=str(payload.get("body", "")),
        labels=[str(item) for item in (payload.get("labels") or [])],
    )
    _ISSUES[slug][issue_id] = issue
    return issue.to_dict()


def _update_issue(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    issue_id = str(payload.get("issue_id", ""))
    issue = _ISSUES[slug].get(issue_id)
    if issue is None:
        raise ExternalNotFoundFailure(f"Issue {issue_id!r} not found")
    if "state" in payload:
        issue.state = str(payload["state"])
    if "labels" in payload:
        issue.labels = [str(item) for item in payload["labels"]]
    return issue.to_dict()


def _create_comment(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    issue_id = str(payload.get("issue_id", ""))
    body = str(payload.get("body", ""))
    if issue_id not in _ISSUES[slug]:
        raise ExternalNotFoundFailure(f"Issue {issue_id!r} not found")
    if not body:
        raise ExternalValidationFailure("Comment requires body")
    comment_id = f"comment-{len(_COMMENTS[slug]) + 1:04d}"
    comment = {"id": comment_id, "issue_id": issue_id, "body": body}
    _COMMENTS[slug].setdefault(issue_id, []).append(comment)
    return comment
