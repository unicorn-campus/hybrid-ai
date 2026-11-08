$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw '의존성 설치에 실패했습니다.' }
    }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw '빌드에 실패했습니다.' }
    & npm.cmd start
} finally {
    Pop-Location
}
