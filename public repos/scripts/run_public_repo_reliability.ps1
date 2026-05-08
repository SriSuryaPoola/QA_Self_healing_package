$ErrorActionPreference = "Stop"

$packageRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = $env:AEGISAI_PYTHON
if (-not $python) {
    $python = "python"
}

Push-Location $packageRoot
try {
    $env:AEGISAI_RUN_PUBLIC_REPO_TESTS = "1"
    if (-not $env:AEGISAI_HEADLESS) {
        $env:AEGISAI_HEADLESS = "1"
    }

    & $python -m pytest tests/reliability -q
    if ($LASTEXITCODE -ne 0) {
        throw "Public repo reliability suite failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

