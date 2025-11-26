if ($args.Count -eq 0) {
    Write-Host "Usage: .\dman.ps1 <command>" -ForegroundColor Yellow
    Write-Host "Example: .\dman.ps1 migrate" -ForegroundColor Gray
    exit
}

docker compose run --rm manage $args