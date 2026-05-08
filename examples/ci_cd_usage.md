# CI/CD Usage Example

AegisAI does not require a platform service. In CI, install the package with the browser framework you use, run your existing tests, and upload `.aegisai/` as an artifact if you want reports/audits.

```powershell
pip install ".[selenium,playwright]"
python -m pytest tests -q
python -m aegisai report --output .aegisai/reports/latest.json
```

For public browser checks:

```powershell
$env:AEGISAI_RUN_PUBLIC_REPO_TESTS="1"
$env:AEGISAI_HEADLESS="1"
python -m pytest tests/reliability -q
```

For team cache experiments without a platform:

```powershell
$env:AEGISAI_CACHE_PATH=".aegisai/team-locator-cache.json"
```
