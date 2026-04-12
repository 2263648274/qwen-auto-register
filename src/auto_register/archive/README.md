# Archive Notes

This folder stores legacy modules that were removed from active runtime flow.

## Why archived

The current project scope is:

1. Register account
2. Activate account
3. Handoff to CLI Proxy API remote auth-link flow

The following legacy capabilities are no longer part of the active path:

1. Local OAuth device-code token exchange in this project
2. Local auth-profiles.json write path
3. Local CPA push from this project
4. OpenClaw gateway restart and related status checks

## Archived modules

1. `legacy/integrations/qwen_oauth_client.py`
2. `legacy/utils/cpa_push.py`
3. `legacy/utils/gateway.py`
4. `legacy/utils/token_utils.py`
5. `legacy/writer/auth_profiles_writer.py`

## Re-activation guidance

If future requirements need any archived feature, restore by moving the file back
to its original package path and re-linking imports from active modules.
