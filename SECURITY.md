# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Experimental preview — security issues accepted |

## Reporting a Vulnerability

**Do not open a public issue.** Email the maintainer directly.

If you discover a security vulnerability:

1. Describe the issue with steps to reproduce.
2. Include affected versions.
3. If applicable, note whether the issue could expose provider credentials, job output, or environment variables.

You will receive an acknowledgment within 72 hours and a timeline for resolution.

## Credential Safety

Agent Crossbar:

- **Never logs provider credentials.** Readiness probes extract only non-secret auth state.
- **Binds provider stderr** in job results to 500 characters, stripping ANSI and known secret patterns.
- **Does not include provider credentials** in fork PR CI workflows (read-only permissions, no secrets).

If you believe credentials have leaked through Agent Crossbar output:

1. Rotate the affected credentials immediately.
2. Report the leak path via the vulnerability process above.

## Supply Chain

- PyPI releases use [trusted publishing](https://docs.pypi.org/trusted-publishers/).
- npm releases follow only after PyPI install smoke passes.
- CI runs secret scanning, dependency auditing, CodeQL, and Dependabot on every push.
- No commit-signing enforcement yet (planned for 0.2.0).
