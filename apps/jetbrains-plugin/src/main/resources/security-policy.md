# SecureLoop Security Policy

## SQL and Database Access

- Do not concatenate, interpolate, or format user-controlled input into SQL strings.
- Use parameterized queries or prepared statements for all user-controlled values.
- Preserve existing authorization checks when modifying data access code.

## Error Handling

- Do not expose stack traces or internal exception messages to end users.
- Log internal errors through the existing logging framework.

## Secrets

- Do not hardcode API keys, passwords, tokens, or credentials.
- Read secrets from environment variables or approved secret managers.

## Fix Requirements

- Keep changes minimal.
- Match existing project conventions.
- Do not introduce new dependencies unless required.
- Explain the security rationale in the PR body.
