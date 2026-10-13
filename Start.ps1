$ErrorActionPreference='Stop'
$bundled=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$python=if(Test-Path -LiteralPath $bundled){$bundled}else{(Get-Command python -ErrorAction Stop).Source}
if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot '.deps/serial'))){
 & $python -m pip install --target (Join-Path $PSScriptRoot '.deps') -r (Join-Path $PSScriptRoot 'requirements.txt')
 if($LASTEXITCODE){throw 'Python bagimliliklari kurulamadi'}
}
& $python (Join-Path $PSScriptRoot 'studio.py')
