param(
    [string]$DatabasePath = (Join-Path $PSScriptRoot "..\data\tracker.db"),
    [string]$BackupDirectory = (Join-Path $PSScriptRoot "..\backups")
)

$ResolvedDatabase = Resolve-Path $DatabasePath -ErrorAction Stop
New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Destination = Join-Path $BackupDirectory "tracker-$Timestamp.db"

$Python = @"
import sqlite3
source = sqlite3.connect(r'''$ResolvedDatabase''')
destination = sqlite3.connect(r'''$Destination''')
with destination:
    source.backup(destination)
source.close()
destination.close()
"@
$Python | python -
if ($LASTEXITCODE -ne 0) { throw "SQLite backup failed" }
Write-Host "Backup created: $Destination"
