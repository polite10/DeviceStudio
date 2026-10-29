$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$requirements = Join-Path $projectRoot 'requirements.txt'
$marker = Join-Path $projectRoot '.venv\studio-requirements.sha256'

if (!(Test-Path -LiteralPath $venvPython)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (!$pythonCommand) { $pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue }
    if (!$pythonCommand) { throw 'Python 3.12+ bulunamadi. Python kurup yeniden deneyin.' }
    & $pythonCommand.Source -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 'Python 3.12+ gerekli.')"
    if ($LASTEXITCODE) { throw 'Python 3.12+ gerekli.' }
    & $pythonCommand.Source -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE) { throw 'Proje Python ortami olusturulamadi.' }
}

& $venvPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 'Proje .venv ortami Python 3.12+ ile olusturulmali.')"
if ($LASTEXITCODE) { throw 'Proje .venv ortami Python 3.12+ ile olusturulmali.' }
$requirementsHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash.ToLowerInvariant()
$installedHash = if (Test-Path -LiteralPath $marker) { (Get-Content -LiteralPath $marker -Raw).Trim() } else { '' }
$dependencyProbe = & $venvPython -c "import importlib.util; print('ready' if all(importlib.util.find_spec(m) for m in ('PySide6', 'serial')) else 'missing')"
$dependenciesMissing = $dependencyProbe -ne 'ready'
if ($installedHash -ne $requirementsHash -or $dependenciesMissing) {
    & $venvPython -m pip install --disable-pip-version-check -r $requirements
    if ($LASTEXITCODE) { throw 'Studio bagimliliklari kurulamadi.' }
    [System.IO.File]::WriteAllText($marker, $requirementsHash, [System.Text.Encoding]::ASCII)
}

Push-Location -LiteralPath $projectRoot
try {
    & $venvPython (Join-Path $projectRoot 'studio.py') @args
    $studioExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $studioExitCode
