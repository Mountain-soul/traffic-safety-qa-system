$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
if (-not $env:NEO4J_USER) { $env:NEO4J_USER = "neo4j" }
if (-not $env:NEO4J_HTTP_URI) { $env:NEO4J_HTTP_URI = "http://localhost:7474" }

python .\qa_web_app.py --user $env:NEO4J_USER --http-uri $env:NEO4J_HTTP_URI --host 127.0.0.1 --port 8000
