# M10 Dependency Security Audit Report

## Category 6: Dependency Security

### Frontend (npm)

**Status**: Measured / Findings Recorded

`npm audit --json` identified 5 advisories:
- **3 moderate**
- **1 high**
- **1 critical**

No dependency remediation was applied during M10. These findings are recorded for separately approved remediation/hardening work. No `npm audit fix --force` was executed.

**Dependencies under audit** (from `package.json`):

| Package | Version | Type |
|---|---|---|
| `@vitejs/plugin-react` | ^4.3.4 | production |
| `react` | ^18.3.1 | production |
| `react-dom` | ^18.3.1 | production |
| `vite` | ^5.4.14 | production |
| `@testing-library/react` | ^16.2.0 | dev |
| `jsdom` | ^25.0.1 | dev |
| `vitest` | ^2.1.9 | dev |

#### Per-Advisory Assessment Template

Once `npm audit --json` is run, each advisory should be assessed:

| Advisory ID | Package | Severity | Vulnerability Class | Reachable in M9? | Fix Available? | SemVer Cost | Recommendation |
|---|---|---|---|---|---|---|---|
| (fill after run) | | | | | | | |

> [!IMPORTANT]
> **Do NOT run** `npm audit fix --force`.
> **Do NOT change any dependency version** without separate explicit approval.

#### Exploitability Notes

For each advisory, assess:
1. **Is the vulnerable code path reachable?** — M9 is a single-page dashboard
   with no server-side rendering, no file uploads, no user-generated content.
   Many npm advisories target SSR, filesystem access, or SSRF patterns that
   are unreachable in a client-only SPA.
2. **Is a fix available?** — Check if a patched version exists within the
   current semver range, or if it requires a major version bump.
3. **What is the real risk?** — Dev dependencies (vitest, jsdom,
   @testing-library/react) are not shipped to production.

---

### Python (pip)

**Status**: ⚠️ Blocked pending approval

`requirements.txt` contains only:
```
fastapi
uvicorn[standard]
```

No Python dependency audit tool (`pip-audit`, `safety`, etc.) has been
approved for installation in this session.

**To unblock**: Explicitly approve installation of `pip-audit` in a
follow-up session. Then run:
```bash
pip install pip-audit
pip-audit --format=json > test_m10/artifacts/pip_audit_raw.json
pip-audit
```

> [!NOTE]
> The Python attack surface is limited to:
> - `fastapi` + `uvicorn`: HTTP server (locally bound, no TLS)
> - `joblib`: Model deserialization (only loads local `.joblib` file)
> - `scikit-learn`, `numpy`, `pandas`: ML inference (no external data)
> - `pydantic`: Request validation (strict mode, extra="forbid")
>
> None of these accept arbitrary user-uploaded files or connect to external
> services. The primary risk vector is `joblib.load()` if the model file
> were to be tampered with, but that's a deployment-security concern, not
> a dependency vulnerability.
