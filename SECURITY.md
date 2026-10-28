# Security Policy

## Supported Versions

MARS-408 is developed on `main`. Security fixes land on `main`; there are no maintained release branches.

| Version | Supported |
|---|---|
| `main` (latest) | ✅ |
| any tag / older commit | ❌ |

---

## Reporting a Vulnerability

Please **do not open a public issue** for security problems.

- Open a [private security advisory](https://github.com/TrueFurina/MARS-408/security/advisories/new), or
- Contact the maintainer via the GitHub profile: [@TrueFurina](https://github.com/TrueFurina)

We aim to acknowledge within **7 days**. This is a student/academic project maintained alongside coursework — please allow for uneven response times.

**In scope**: the FastAPI backend, the LangGraph agent pipeline, the prompt/guardrail layer, the Vue frontend, and anything that could leak learner data or allow prompt-injection to escalate into tool misuse.

**Out of scope**: findings that require a local attacker with filesystem access, denial-of-service via resource exhaustion on a self-hosted single-user deployment, and issues in third-party LLM providers.

---

## Known Historical Findings (disclosed, not hidden)

This repository has one historical credential exposure. It is recorded here rather than quietly removed, because a security project should be honest about its own history — the same principle as the capability table in `README.md`, which marks ⚠️ / ⏳ items and states they are not selling points.

### `py-server/iq_run_tmp/.env.test`

| Field | Value |
|---|---|
| Status | **Removed from `HEAD`** (commit `7eb0f7dc08`); still readable in pre-removal history |
| Location | `py-server/iq_run_tmp/.env.test` |
| Contents | Local test configuration: `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, a local `VECTORDB_DATA_DIR`, `AUTH_SECRET=test-secret-*`, `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=admin****` |
| Nature | **Test fixture, not production credentials** |
| Exploitability | **None observed.** `VECTORDB_DATA_DIR` points at a local disk path (`E:/...`), and this project ships no server artifact or public deployment. There is no reachable service behind these values.
| Residual risk | The values illustrate a weak-credential pattern (`admin` + a common password). They must never be reused for a real deployment. |

A blank template now lives at `py-server/iq_run_tmp/.env.test.example`, and `.gitignore` blocks future `.env*` commits.

> If you are reviewing this repository and find any other credential-like material, please report it via the private channel above rather than opening an issue.

---

## Handling of Secrets in This Repository

- `.env`, `.env.*`, `*.pem`, `*.p12`, `*.key` are git-ignored.
- Only `*.example` templates are tracked, with **empty values**.
- LLM provider keys (`DEEPSEEK_API_KEY`, Spark credentials) are expected to come from the environment, never from tracked files.
- If you deploy this yourself: rotate any key you have ever pasted into a file, and prefer a secret manager over a checked-in `.env`.

### A note on test fixtures that look like secrets

Some test fixtures intentionally contain secret-shaped strings to verify that the agent refuses to persist credentials. For example, the benchmark case `memory-no-secrets` feeds the agent a fake API key and asserts it does **not** echo or store it — this is the control case for OWASP *Sensitive Data Exposure*. Such strings are generated placeholders, not live credentials.

---

## Scope of This Project

MARS-408 is an educational multi-agent system. It is intended for:

- authorized environments and coursework
- research on agent orchestration and teaching-policy learning

It is **not** a hardened production service. Self-hosting it on the public internet without authentication hardening, rate limiting, and prompt-injection defenses of your own is outside the threat model this project defends against.
