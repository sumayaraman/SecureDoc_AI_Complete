"""Security boundary notes.

Every organization-owned query must be scoped by the authenticated user's organization.
The production application should use private object storage with short-lived signed URLs,
strict MIME/extension/size validation, rate limiting, mature authentication, and a
read-only allowlisted query layer for the assistant. Secrets belong in environment variables.
"""
