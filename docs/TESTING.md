# Verification record

## Environment

Python 3.13.5 on Linux. FastAPI 0.128.2, Uvicorn 0.48.0, HTTPX 0.28.1, Pydantic 2.13.4, pytest 9.0.2. SQLite comes from the Python runtime. Browser checks used Playwright 1.57.0 and system Chromium.

## Verified

- The automated Python test suite passes. Its captured output is in `test-results.txt`.
- All 90 template reference tasks compile and execute across all three fixture databases.
- Each of the 12 deliberately faulty seed answers fails at least one fixture; each reference passes the suite.
- A full 30-task, two-arm scripted run completes, preserving 60 outputs and producing a report and JSON artifact.
- Request-budget exhaustion pauses the run; extending the budget resumes it without rerunning already committed outputs.
- Eleven browser checks pass against the real FastAPI `TestClient`: initial state, editing/validation/approval, export, generation, search, holdout read-only controls, experiment creation, budget/resume, output inspection, mobile layout, and absence of JavaScript errors. Captured output is in `browser-results.txt`.
- Desktop and mobile layouts were rendered and visually inspected. The screenshots use an explicitly labeled scripted sample workspace, not a real model result.

The browser in this environment disallows URL navigation. For UI checks, bundled HTML/CSS/JavaScript was rendered directly in memory; a narrow fetch bridge called the real FastAPI test client. No browser policy was modified. This exercises UI handlers and application endpoints together but does not validate deployment networking, HTTPS, or reverse-proxy behavior.

## Not verified here

No real authenticated model API call was made. Provider behavior was tested with mocked HTTP success, incomplete output, rate-limit, authorization-error, and budget-exhaustion responses.

Docker was unavailable, so the Dockerfile and Compose configuration were supplied but not built or run. Python 3.11/3.12 compatibility is configured for CI, not locally verified in this environment. GitHub Actions has not been run against a remote repository. No independent domain expert reviewed the data and no customer interview was conducted.

## Bugs found during verification

The SQL child initially inherited Python site initialization, which consumed too much address space before its memory limit. Adding `-S` alongside `-I` made its runtime stdlib-only and allowed valid reference queries to pass under the limit.

A resume race briefly returned the old paused status before the worker published its new status, leaving the browser without a polling loop. The coordinator now sets queued status before launching a resumed worker. The browser resume check covers this path.

The tests also cover subtle result-comparison issues: unordered duplicate preservation, column position, NULL versus zero, type preservation, tolerance-aware matching, and large duplicate multisets.
