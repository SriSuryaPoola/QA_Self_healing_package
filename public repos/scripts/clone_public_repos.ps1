$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$repoDir = Join-Path $workspace "repos"
New-Item -ItemType Directory -Force -Path $repoDir | Out-Null

$targets = @(
    @{
        Name = "the-internet"
        Url = "https://github.com/saucelabs/the-internet.git"
        Branch = "master"
    },
    @{
        Name = "sample-app-web"
        Url = "https://github.com/saucelabs/sample-app-web.git"
        Branch = "main"
    }
)

foreach ($target in $targets) {
    $destination = Join-Path $repoDir $target.Name
    if (Test-Path -LiteralPath $destination) {
        Write-Host "Already cloned: $destination"
        continue
    }

    Write-Host "Cloning $($target.Url) -> $destination"
    git clone --depth 1 --branch $target.Branch $target.Url $destination
}

Write-Host "Public repo replicas are ready in: $repoDir"

