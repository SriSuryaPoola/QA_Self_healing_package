# Public Repo Reliability Workspace

This folder is for real-world AegisAI validation against public QA/demo applications.

The cloned third-party repos live under `repos/` and are intentionally ignored by Git so the package repository does not vendor external source code. The committed files here are only the harness, scripts, and findings.

## Current Public Targets

| Folder | Public repo | Runtime target | Why it is useful |
|---|---|---|---|
| `repos/the-internet` | `https://github.com/saucelabs/the-internet` | `https://the-internet.herokuapp.com` | Login form, iframe, shadow DOM, dynamic UI patterns |
| `repos/sample-app-web` | `https://github.com/saucelabs/sample-app-web` | Public replica/reference only for now | Modern web app source for future local app runs |

## Clone The Replicas

```powershell
& ".\public repos\scripts\clone_public_repos.ps1"
```

## Run The Reliability Suite

```powershell
& ".\public repos\scripts\run_public_repo_reliability.ps1"
```

If `python` on your PATH is not the interpreter with Selenium/Playwright installed, point the script at the right executable:

```powershell
$env:AEGISAI_PYTHON="C:\Users\Pula Srisurya\AppData\Local\Programs\Python\Python314\python.exe"
& ".\public repos\scripts\run_public_repo_reliability.ps1"
```

To watch the browser as a real user:

```powershell
$env:AEGISAI_HEADLESS="0"
& ".\public repos\scripts\run_public_repo_reliability.ps1"
```

## What These Tests Prove

- Selenium auto-activation can heal broken locators on a public app, not just the local demo.
- Playwright can use the core SDK manually from page HTML.
- Playwright hooks capture failure context, but do not auto-heal actions yet.
- iframe context switching is a current Selenium shortcoming.
- Shadow DOM piercing is a current Selenium L4 shortcoming.

## Why Tests Are Opt-In

These tests hit public live sites and launch real browsers. That makes them slower and occasionally dependent on network/browser availability, so normal `pytest` keeps them skipped unless `AEGISAI_RUN_PUBLIC_REPO_TESTS=1` is set.
