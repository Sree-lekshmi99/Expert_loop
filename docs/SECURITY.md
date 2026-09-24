# Security model

## Intended use

This is a local single-user workbench using fictional data. Keep it bound to loopback. Do not deploy it directly to the public internet or load proprietary databases into it.

## SQL controls implemented

Candidate SQL executes in a separate Python process using `-I -S`: isolated Python configuration, no site initialization, and no inherited API key or application environment. Only absolute paths to the three generated fixture databases are passed by the server. A request cannot supply an arbitrary database path.

Fixture databases open with `mode=ro&immutable=1`, `query_only=ON`, and `trusted_schema=OFF`. A SQLite authorizer permits SELECT, reads of the four fixture tables, and an allowlist of built-in functions. Writes, attachments, PRAGMAs in user SQL, schema inspection, extension loading, table-valued file access, and recursive CTEs are denied. Python `execute()` accepts only a single statement.

There are SQL-length, value-size, column, expression-depth, compound-query and row-count limits. A SQLite progress handler interrupts expensive execution. The parent imposes a wall timeout. On supported Unix platforms the worker also applies address-space, CPU, core-dump and file-size resource limits. Windows does not have Python's `resource` module, so those OS resource limits are unavailable; the parent timeout and SQLite controls still apply.

Code-authored catalog references take a separate trusted preparation path. Candidate and reviewer-submitted SQL always use the subprocess path.

## Important boundary

A child process is **not** a complete security sandbox. This project does not enforce a per-query network namespace or syscall policy, defend against native SQLite/Python vulnerabilities, or certify safe multi-tenant execution. SQLite in this configuration exposes no enabled networking/file-reading extension to the query, but this is not the same as OS-enforced network isolation. Use a separately isolated execution service with no network/secrets and tightly scoped read-only mounts before accepting hostile public submissions.

The supplied Docker configuration runs as a non-root user, drops capabilities, enables no-new-privileges, makes the image filesystem read-only, and mounts only app state plus temporary space. It is additional containment, not a multi-tenant security guarantee. Docker was not available in the build environment; validate the container in your own environment.

## Web/API controls

The app binds to `127.0.0.1` by default. Mutating requests require `X-ExpertLoop: 1` and reject a mismatched browser Origin. Host allowlisting mitigates DNS rebinding, and no cross-origin CORS permissions are added. These are not authentication. Local scripts and other local users can access the app.

The UI escapes task text and SQL before HTML display. It has no third-party CDN script, font, analytics, or external asset dependency. Response headers disallow embedding and restrict script/connect sources. Interactive API documentation uses FastAPI's standard documentation assets and may require internet access; the application itself does not.

API keys stay in server-side environment variables. The SQL child receives a scrubbed environment. The dashboard exposes only whether a key is present. Provider errors are normalized rather than persisting raw response headers or error bodies. Never commit `.env`, private state directories, or real customer exports.

## Reporting a problem

For this starter repository, track security issues privately in the repository you create. There is no hosted service or security response team associated with the supplied project.
