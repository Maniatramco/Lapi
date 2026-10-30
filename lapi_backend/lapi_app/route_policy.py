"""Who may call each API route: one table, checked when a request signs in (main.auth).

  public    no sign-in (sign-in itself, status, recovery that is local-only)
  signed_in any signed-in person; the route only touches their own records, or
            dataset content they can open (the route code filters by dataset access)
  viewer    reads dataset content; the route code requires Viewer on that dataset
  editor    changes dataset content; the route code requires Editor on that dataset
  owner     changes a dataset's settings or members; the route code requires Owner
  contributor Administrators and Contributors (creating, deleting and restoring datasets and
            onboarding; Contributors are Owner on every dataset). Model mapping stays 'admin':
            new datasets use the workspace Default models.
  audit     Administrators and Auditors (read-only views of people, access and usage)
  admin     Administrators only: managing the workspace

auth() enforces 'admin', 'contributor' and 'audit' here, for every route. Dataset levels need the
dataset, so the route code enforces them (dataset_access.require_level and
get_record(level=...)); test_route_policy.py checks both. A route missing from this
table is refused, so a new route cannot ship without a decision.
"""
from fastapi import HTTPException

POLICY = {
    # Sign-in and the person's own account
    ('GET', '/api/auth/status'): 'public',
    ('POST', '/api/auth/login'): 'public',
    ('GET', '/api/auth/keycloak/start'): 'public',
    ('GET', '/api/auth/keycloak/callback'): 'public',
    ('POST', '/api/auth/recovery/prepare'): 'public',
    ('POST', '/api/auth/recovery/reset'): 'public',
    ('POST', '/api/auth/keycloak/backchannel-logout'): 'public',  # Verified Keycloak logout token.
    ('GET', '/api/auth/me'): 'signed_in',
    ('GET', '/api/me/sessions'): 'signed_in',
    ('DELETE', '/api/me/sessions/{short_id}'): 'signed_in',
    ('POST', '/api/me/sessions/sign-out-others'): 'signed_in',
    ('GET', '/api/auth/totp'): 'signed_in',
    ('POST', '/api/auth/totp/setup'): 'signed_in',
    ('POST', '/api/auth/totp/confirm'): 'signed_in',
    ('POST', '/api/auth/totp/disable'): 'signed_in',
    ('POST', '/api/auth/logout'): 'signed_in',
    ('POST', '/api/auth/password'): 'signed_in',
    ('GET', '/api/me/memory'): 'signed_in',
    ('PUT', '/api/me/memory'): 'signed_in',
    ('DELETE', '/api/me/memory'): 'signed_in',
    ('GET', '/api/me/walkthrough'): 'signed_in',
    ('POST', '/api/me/walkthrough'): 'signed_in',
    ('GET', '/api/me/preferences'): 'signed_in',
    ('GET', '/api/me/screens'): 'signed_in',
    ('GET', '/api/me/agent-training'): 'signed_in',
    ('POST', '/api/me/agent-training'): 'signed_in',
    ('GET', '/api/screens'): 'admin',
    ('PUT', '/api/screens'): 'admin',
    ('POST', '/api/screens/preset'): 'admin',
    ('PUT', '/api/me/preferences'): 'signed_in',

    # People, roles, teams and access
    ('GET', '/api/users'): 'audit',
    ('POST', '/api/users'): 'admin',
    ('POST', '/api/users/{user_id}/password'): 'admin',
    ('DELETE', '/api/users/{user_id}'): 'admin',
    ('PATCH', '/api/users/{user_id}/role'): 'admin',
    ('POST', '/api/users/{user_id}/sessions/sign-out'): 'admin',
    ('POST', '/api/users/{user_id}/totp/reset'): 'admin',
    ('GET', '/api/users/{user_id}/datasets'): 'audit',
    ('PUT', '/api/users/{user_id}/datasets'): 'admin',
    ('GET', '/api/access-map'): 'audit',
    ('GET', '/api/teams'): 'audit',
    ('POST', '/api/teams'): 'admin',
    ('PUT', '/api/teams/{team_id}/members'): 'admin',
    ('PUT', '/api/teams/{team_id}/datasets'): 'admin',
    ('DELETE', '/api/teams/{team_id}'): 'admin',
    ('GET', '/api/datasets/{id}/members'): 'owner',
    ('PUT', '/api/datasets/{id}/members'): 'owner',

    # Workspace storage, database and reset
    ('GET', '/api/storage/status'): 'signed_in',
    ('GET', '/api/storage'): 'admin',
    ('POST', '/api/storage/test'): 'admin',
    ('PUT', '/api/storage'): 'admin',
    ('GET', '/api/storage/database'): 'admin',
    ('POST', '/api/storage/database/test'): 'admin',
    ('PUT', '/api/storage/database'): 'admin',
    ('POST', '/api/storage/database/prepare'): 'admin',
    ('POST', '/api/storage/database/activate'): 'admin',
    ('GET', '/api/workspace/reset-preview'): 'admin',
    ('POST', '/api/workspace/reset'): 'admin',
    ('POST', '/api/workspace/archives/{id}/restore'): 'admin',
    ('GET', '/api/workspace/defaults'): 'signed_in',
    ('GET', '/api/workspace/knowledge-index'): 'signed_in',
    ('POST', '/api/workspace/knowledge-index/retry'): 'admin',
    ('POST', '/api/workspace/knowledge-index/remove-orphans'): 'admin',
    ('GET', '/api/runtime-config'): 'signed_in',
    ('GET', '/api/overview'): 'signed_in',
    ('GET', '/api/documentation'): 'signed_in',
    ('GET', '/api/documentation/export'): 'signed_in',

    # Settings, models and their prices
    ('GET', '/api/settings'): 'signed_in',
    ('PATCH', '/api/settings'): 'admin',
    ('GET', '/api/settings/export'): 'signed_in',
    ('POST', '/api/settings/test'): 'admin',
    ('GET', '/api/capabilities'): 'signed_in',
    ('GET', '/api/settings/profiles'): 'signed_in',
    ('POST', '/api/settings/profiles'): 'admin',
    ('PUT', '/api/settings/profiles/{id}'): 'admin',
    ('POST', '/api/settings/profiles/{id}/activate'): 'admin',
    ('GET', '/api/settings/profiles/{id}/export'): 'signed_in',
    ('GET', '/api/models'): 'signed_in',
    ('POST', '/api/models'): 'admin',
    ('PUT', '/api/models/{id}'): 'admin',
    ('GET', '/api/models/{model_id}/prompt-guide'): 'signed_in',
    ('PUT', '/api/models/{model_id}/prompt-guide'): 'admin',
    ('GET', '/api/model-providers'): 'signed_in',
    ('GET', '/api/model-registrations/parameter-schema'): 'signed_in',
    ('GET', '/api/model-registrations/{id}/parameter-history'): 'signed_in',
    ('POST', '/api/model-registrations'): 'admin',
    ('PUT', '/api/model-registrations/{id}'): 'admin',
    ('POST', '/api/model-registrations/test'): 'admin',
    ('PUT', '/api/model-registrations/{id}/default'): 'admin',
    ('PUT', '/api/model-registrations/{id}/enabled'): 'admin',
    ('GET', '/api/model-registrations/{id}/prices'): 'signed_in',
    ('POST', '/api/model-registrations/{id}/prices'): 'admin',
    ('GET', '/api/local-models'): 'signed_in',
    ('GET', '/api/admin/token-usage'): 'admin',
    ('GET', '/api/admin/token-usage/export'): 'admin',
    ('GET', '/api/token-usage/conversations/{id}'): 'signed_in',

    # Datasets
    ('GET', '/api/knowledge-bases'): 'signed_in',
    ('POST', '/api/knowledge-bases'): 'contributor',
    ('GET', '/api/datasets'): 'signed_in',
    ('POST', '/api/datasets'): 'contributor',
    ('GET', '/api/datasets/{id}'): 'viewer',
    ('PATCH', '/api/datasets/{id}'): 'owner',
    ('PATCH', '/api/datasets/{id}/status'): 'contributor',
    ('GET', '/api/datasets/{id}/models'): 'viewer',
    ('PUT', '/api/datasets/{id}/models'): 'admin',
    ('POST', '/api/datasets/{id}/migrate-settings'): 'contributor',
    ('POST', '/api/datasets/{id}/assign-documents'): 'contributor',
    ('POST', '/api/datasets/{id}/local-models'): 'admin',
    ('DELETE', '/api/datasets/{id}'): 'contributor',
    ('GET', '/api/dataset-trash'): 'contributor',
    ('POST', '/api/dataset-trash/{id}/restore'): 'contributor',
    ('GET', '/api/datasets/{dataset_id}/instructions'): 'viewer',
    ('GET', '/api/datasets/{dataset_id}/instructions/versions'): 'viewer',
    ('PUT', '/api/datasets/{dataset_id}/instructions'): 'owner',
    ('GET', '/api/datasets/{dataset_id}/prompt-guide'): 'viewer',
    ('PUT', '/api/datasets/{dataset_id}/prompt-guide'): 'owner',
    ('GET', '/api/metadata-relationships'): 'signed_in',

    # Documents
    ('GET', '/api/documents'): 'signed_in',
    ('POST', '/api/documents/upload'): 'editor',
    ('GET', '/api/documents/{id}'): 'viewer',
    ('GET', '/api/documents/{id}/preview'): 'viewer',
    ('GET', '/api/documents/{id}/row-context'): 'viewer',
    ('GET', '/api/documents/{id}/download'): 'viewer',
    ('GET', '/api/documents/{id}/source'): 'viewer',
    ('GET', '/api/documents/{id}/page-image'): 'viewer',
    ('GET', '/api/documents/{id}/merged-sources/{key}/{action}'): 'viewer',
    ('POST', '/api/documents/{id}/reindex'): 'editor',
    ('POST', '/api/documents/{id}/reextract'): 'editor',
    ('DELETE', '/api/documents/{id}'): 'editor',
    ('POST', '/api/documents/{id}/keep'): 'editor',
    ('GET', '/api/admin/documents'): 'admin',
    ('GET', '/api/admin/documents/{id}/deletion-preview'): 'admin',
    ('DELETE', '/api/admin/documents/{id}'): 'admin',
    ('POST', '/api/admin/documents/{id}/retry'): 'admin',
    ('GET', '/api/index'): 'signed_in',
    ('POST', '/api/index/search'): 'signed_in',
    ('POST', '/api/knowledge/search'): 'signed_in',
    ('GET', '/api/knowledge/sources/{id}'): 'viewer',
    ('GET', '/api/knowledge/published-sources/{id}'): 'viewer',

    # Connectors (Editor of the dataset they import into)
    ('GET', '/api/source-connections'): 'signed_in',
    ('POST', '/api/source-connections/test'): 'editor',
    ('POST', '/api/source-connections'): 'editor',
    ('PUT', '/api/source-connections/{identifier}'): 'editor',
    ('GET', '/api/source-connections/{identifier}/files'): 'editor',
    ('POST', '/api/source-connections/{identifier}/import'): 'editor',
    ('POST', '/api/source-connections/{identifier}/publish'): 'editor',

    # Prompt templates and extractions
    ('GET', '/api/templates'): 'signed_in',
    ('POST', '/api/templates/validate'): 'signed_in',
    ('POST', '/api/templates'): 'editor',
    ('POST', '/api/templates/suggest'): 'editor',
    ('POST', '/api/templates/table-plan'): 'editor',
    ('PUT', '/api/templates/{id}'): 'editor',
    ('GET', '/api/templates/{id}/versions'): 'viewer',
    ('GET', '/api/templates/{id}/export'): 'viewer',
    ('GET', '/api/extractions'): 'signed_in',
    ('POST', '/api/extractions'): 'editor',
    ('GET', '/api/extractions/{id}'): 'viewer',
    ('GET', '/api/extractions/{id}/merged-file'): 'viewer',
    ('PATCH', '/api/extractions/{id}'): 'editor',
    ('POST', '/api/extractions/{id}/resume'): 'editor',
    ('POST', '/api/extractions/{id}/reextract'): 'editor',
    ('POST', '/api/extractions/{id}/rerun'): 'editor',
    ('GET', '/api/extractions/{id}/versions'): 'viewer',
    ('GET', '/api/extractions/{id}/source-evidence'): 'viewer',
    ('GET', '/api/extractions/{id}/export'): 'viewer',
    ('GET', '/api/extract-data'): 'signed_in',
    ('GET', '/api/extract-data/export'): 'signed_in',

    # Background jobs (Editor to retry or cancel others' work)
    ('GET', '/api/jobs'): 'signed_in',
    ('POST', '/api/jobs/{id}/retry'): 'editor',
    ('POST', '/api/jobs/{id}/cancel'): 'editor',

    # Chat, the agent and personal temporary files
    ('GET', '/api/conversations'): 'signed_in',
    ('POST', '/api/conversations'): 'signed_in',
    ('GET', '/api/conversations/{id}'): 'signed_in',
    ('POST', '/api/conversations/{id}/messages'): 'signed_in',
    ('POST', '/api/conversations/{id}/messages/stream'): 'signed_in',
    ('GET', '/api/conversations/{id}/export'): 'signed_in',
    ('POST', '/api/messages/{id}/feedback'): 'signed_in',
    ('POST', '/api/temporary-chat/sessions'): 'signed_in',
    ('DELETE', '/api/temporary-chat/sessions/{id}'): 'signed_in',
    ('POST', '/api/temporary-chat/documents'): 'signed_in',
    ('GET', '/api/temporary-chat/documents/{id}'): 'signed_in',
    ('DELETE', '/api/temporary-chat/documents/{id}'): 'signed_in',
    ('POST', '/api/temporary-chat/messages'): 'signed_in',
    ('GET', '/api/dataset-chat/catalog'): 'signed_in',
    ('GET', '/api/dataset-chat/conversations'): 'signed_in',
    ('GET', '/api/dataset-chat/conversations/{id}'): 'signed_in',
    ('POST', '/api/dataset-chat/messages'): 'signed_in',
    ('POST', '/api/dataset-chat/reply'): 'signed_in',
    ('POST', '/api/agent-v2/consent'): 'signed_in',
    ('GET', '/api/agent-v2/goals'): 'signed_in',
    ('GET', '/api/agent-v2/catalog'): 'signed_in',
    ('POST', '/api/agent-v2/plans'): 'signed_in',
    ('GET', '/api/agent-v2/plans/{id}'): 'signed_in',
    ('POST', '/api/agent-v2/plans/{id}/reply'): 'signed_in',
    ('GET', '/api/agent-v2/plans/{id}/events'): 'signed_in',
    ('POST', '/api/agent-v2/plans/{id}/knowledge/retry'): 'signed_in',
    ('POST', '/api/agent-v2/plans/{id}/goal'): 'signed_in',
    # Tool calls run the same document and extraction functions, which apply dataset levels.
    ('POST', '/api/agent-v2/plans/{id}/calls/{index}'): 'signed_in',
    ('POST', '/api/agent-v2/plans/{id}/calls/{index}/upload'): 'editor',
    ('POST', '/api/agent-v2/plans/{id}/restart'): 'signed_in',
    ('POST', '/api/agent-v2/plans/{id}/calls/{index}/recover'): 'signed_in',
    ('GET', '/api/agent-v2/onboarding'): 'contributor',
    ('GET', '/api/agent-v2/onboarding/{id}'): 'contributor',
    ('POST', '/api/agent-v2/onboarding'): 'contributor',
    ('POST', '/api/agent-v2/onboarding/{id}/files'): 'contributor',
    ('POST', '/api/agent-v2/onboarding/{id}/advance'): 'contributor',
    ('GET', '/api/skills'): 'signed_in',
    # Personal skills; sharing with a dataset or the workspace is administrator-only in skills.py.
    ('POST', '/api/skills'): 'signed_in',
    ('POST', '/api/skills/upload'): 'signed_in',
    ('GET', '/api/skills/{skill_id}/download'): 'signed_in',
    ('PUT', '/api/skills/{skill_id}'): 'signed_in',
    ('DELETE', '/api/skills/{skill_id}'): 'signed_in',
}

LEVELS = {'public', 'signed_in', 'viewer', 'editor', 'owner', 'contributor', 'audit', 'admin'}


def check(method, path, actor):
    """Apply the route's policy for a signed-in request. `path` is the route template."""
    from . import core, dataset_access
    policy = POLICY.get((method, path))
    if policy is None:
        # Fail closed: an unclassified route is a missing decision, not an open door.
        raise HTTPException(403, 'This action is not available.')
    if policy == 'admin' and not core.is_administrator(actor):
        raise HTTPException(403, 'Administrator access is required.')
    if policy == 'contributor' and not dataset_access.manages_datasets(actor):
        raise HTTPException(403, 'Administrator or Contributor access is required.')
    if policy == 'audit' and not (core.is_administrator(actor) or dataset_access.is_auditor(actor)):
        raise HTTPException(403, 'Administrator or Auditor access is required.')
    return policy
