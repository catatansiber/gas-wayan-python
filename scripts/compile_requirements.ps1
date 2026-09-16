<#
Kompilasi ulang requirements.txt / requirements-dev.txt (lock file dengan hash) dari
requirements.in / requirements-dev.in. Jalankan setelah mengubah salah satu file .in.
Jangan edit requirements*.txt secara manual.
#>
param(
    [string]$VenvPython = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = 'Stop'

# --allow-unsafe: sertakan pip/setuptools dalam lock file (dengan hash). Tanpa ini, instal
# dengan --require-hashes bisa gagal saat sebuah dependency (mis. pip-tools -> build) butuh
# setuptools di waktu instal tapi setuptools tidak ikut ter-hash.
& $VenvPython -m piptools compile --generate-hashes --allow-unsafe --output-file=requirements.txt requirements.in
if ($LASTEXITCODE -ne 0) { throw "pip-compile gagal untuk requirements.in" }

& $VenvPython -m piptools compile --generate-hashes --allow-unsafe --output-file=requirements-dev.txt requirements-dev.in
if ($LASTEXITCODE -ne 0) { throw "pip-compile gagal untuk requirements-dev.in" }

Write-Host "OK - requirements.txt dan requirements-dev.txt diperbarui."
