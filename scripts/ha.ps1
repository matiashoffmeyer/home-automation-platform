# =============================================================================
# HA Remote Helpers — PowerShell module til at styre HA fra terminal
# =============================================================================
# Dot-source dette i din PowerShell session eller profile:
#   . C:\Users\Matia\Documents\homeassistant-main\scripts\ha.ps1
#
# For permanent: tilfoej til $PROFILE:
#   notepad $PROFILE
#   # tilfoej linjen ovenfor
#
# Forudsaetninger:
# - SSH key paret med HA addon (se docs/remote_workflow.md)
# - Optional: $env:HA_TOKEN sat til long-lived access token (for ha-state/ha-call)
# =============================================================================

# Configuration — override via env vars hvis noedvendigt
$global:HA_HOST = if ($env:HA_HOST) { $env:HA_HOST } else { "homeassistant.local" }
$global:HA_USER = if ($env:HA_USER) { $env:HA_USER } else { "root" }
$global:HA_PORT = if ($env:HA_PORT) { $env:HA_PORT } else { "22" }
$global:HA_KEY  = if ($env:HA_KEY)  { $env:HA_KEY }  else { "$HOME\.ssh\ha_key" }

# -----------------------------------------------------------------------------
# Core SSH helpers
# -----------------------------------------------------------------------------

function ha-cmd {
    <#
    .SYNOPSIS
    Run a command on HA via SSH (wrapped in login shell so ha CLI har env vars).
    .EXAMPLE
    ha-cmd "ls /config"
    ha-cmd "ha core restart"
    .NOTES
    Kommando wrappes i 'zsh -lc' saa SUPERVISOR_TOKEN er sat. Uden det
    fejler 'ha' CLI med "missing or invalid API token" pga non-interactive
    SSH ikke loader profile.
    #>
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Cmd)
    $cmdStr = ($Cmd -join ' ') -replace "'", "'\''"
    ssh -p $HA_PORT -i $HA_KEY -o BatchMode=yes "${HA_USER}@${HA_HOST}" "zsh -lc '$cmdStr'"
}

function ha-shell {
    <#
    .SYNOPSIS
    Interactive SSH session i HA.
    #>
    ssh -p $HA_PORT -i $HA_KEY "${HA_USER}@${HA_HOST}"
}

# -----------------------------------------------------------------------------
# HA Core operations
# -----------------------------------------------------------------------------

function ha-restart {
    <#
    .SYNOPSIS
    Restart HA Core. Tager 30-60 sek.
    #>
    Write-Host "Restarting HA Core..." -ForegroundColor Cyan
    ha-cmd "ha core restart"
}

function ha-stop {
    Write-Host "Stopping HA Core..." -ForegroundColor Yellow
    ha-cmd "ha core stop"
}

function ha-logs {
    <#
    .SYNOPSIS
    View HA Core logs (default last 100 lines).
    .EXAMPLE
    ha-logs        # last 100 lines
    ha-logs 500    # last 500 lines
    #>
    param([int]$Lines = 100)
    ha-cmd "ha core logs --tail $Lines"
}

function ha-check {
    <#
    .SYNOPSIS
    Validate HA config.
    .NOTES
    BEMARK: ha core check er buggy i HAOS 2026.4.0 (per CLAUDE.md). Brug
    ha-restart i stedet — restart koerer validering selv under boot.
    #>
    Write-Warning "ha core check er buggy i HAOS 2026.4.0 — brug ha-restart i stedet."
    ha-cmd "ha core check"
}

# -----------------------------------------------------------------------------
# Git deploy workflow
# -----------------------------------------------------------------------------

function ha-pull {
    <#
    .SYNOPSIS
    Pull latest fra git origin/main UDEN restart.
    Bruges til docs-only ændringer eller manuel restart bagefter.
    #>
    ha-cmd "cd /config; git fetch origin; git reset --hard origin/main"
}

function ha-deploy {
    <#
    .SYNOPSIS
    Pull + restart + smoke test + auto-revert hvis fail. Den primaere "deploy" command.
    .DESCRIPTION
    Bruger scripts/ha_deploy.sh (Blok B, sprint 2026-05-06):
      1. Pre-deploy snapshot
      2. Pull origin/main
      3. Restart HA
      4. Wait for /api/ ready (timeout 120s)
      5. Smoke test (18 tests)
      6. Auto-revert til previous SHA hvis smoke fail (+ mobile push)
      7. Success notification
    .NOTES
    Override: ha-deploy --skip-smoke (docs-only) eller --force (deploy trods smoke fail).
    Log: /tmp/ha_deploy_<epoch>.log + path i .cache/last_deploy_log_path.txt
    #>
    Write-Host "Deploying via ha_deploy.sh (smoke gate + auto-revert)..." -ForegroundColor Cyan
    $repoRoot = Split-Path $PSScriptRoot -Parent
    bash "$repoRoot/scripts/ha_deploy.sh" $args
}

function ha-deploy-legacy {
    <#
    .SYNOPSIS
    LEGACY: pull + restart UDEN smoke gate (gammel adfærd pre-Blok B).
    Brug ha-deploy i stedet med mindre du eksplicit vil skip safety net.
    #>
    Write-Host "Legacy deploy (no smoke gate)..." -ForegroundColor Yellow
    ha-cmd "cd /config; git fetch origin; git reset --hard origin/main; ha core restart"
}

function ha-push-and-deploy {
    <#
    .SYNOPSIS
    Lokalt: git push origin main + remote: deploy.
    #>
    Write-Host "Pushing to origin/main..." -ForegroundColor Cyan
    git push origin main
    if ($LASTEXITCODE -eq 0) {
        ha-deploy
    } else {
        Write-Error "git push fejlede — deploy aborteret."
    }
}

# -----------------------------------------------------------------------------
# File operations
# -----------------------------------------------------------------------------

function ha-cat {
    <#
    .SYNOPSIS
    Print fil-indhold fra HA /config.
    .EXAMPLE
    ha-cat automations/light_power_recovery.yaml
    #>
    param([Parameter(Mandatory=$true)][string]$File)
    ha-cmd "cat /config/$File"
}

function ha-edit {
    <#
    .SYNOPSIS
    Edit fil i HA via vim. Interactive session.
    .EXAMPLE
    ha-edit automations/light_power_recovery.yaml
    .NOTES
    Direkte edit = ude af git sync. Brug kun til hurtige tests — ellers git push.
    #>
    param([Parameter(Mandatory=$true)][string]$File)
    Write-Warning "Direkte edit gaar ude af git sync. Brug 'git pull' bagefter for at hente til lokal."
    ssh -t -p $HA_PORT -i $HA_KEY "${HA_USER}@${HA_HOST}" "vim /config/$File"
}

function ha-ls {
    <#
    .SYNOPSIS
    List filer i HA /config eller subdirectory.
    #>
    param([string]$Path = "")
    ha-cmd "ls -la /config/$Path"
}

# -----------------------------------------------------------------------------
# REST API operations (kraever HA_TOKEN env var)
# -----------------------------------------------------------------------------

function _ha-check-token {
    if (-not $env:HA_TOKEN) {
        Write-Error "HA_TOKEN env var ikke sat. Kor: `$env:HA_TOKEN = 'din_long_lived_token'"
        return $false
    }
    return $true
}

function ha-state {
    <#
    .SYNOPSIS
    Hent state af entity via REST API.
    .EXAMPLE
    ha-state light.badevaerelse_loft
    ha-state sensor.activity_state
    #>
    param([Parameter(Mandatory=$true)][string]$EntityId)
    if (-not (_ha-check-token)) { return }
    Invoke-RestMethod -Uri "http://${HA_HOST}:8123/api/states/$EntityId" `
                      -Headers @{Authorization = "Bearer $env:HA_TOKEN"}
}

function ha-call {
    <#
    .SYNOPSIS
    Kald HA service via REST API.
    .EXAMPLE
    ha-call light.turn_on @{entity_id="light.badevaerelse_loft"; brightness_pct=70}
    ha-call homeassistant.restart
    .EXAMPLE
    # Trigger automation manuelt
    ha-call automation.trigger @{entity_id="automation.bath_firmware_defaults_adaptive"}
    #>
    param(
        [Parameter(Mandatory=$true)][string]$DomainService,
        [hashtable]$Data = @{}
    )
    if (-not (_ha-check-token)) { return }
    $parts = $DomainService -split '\.', 2
    $domain = $parts[0]
    $service = $parts[1]
    Invoke-RestMethod -Uri "http://${HA_HOST}:8123/api/services/$domain/$service" `
                      -Method Post `
                      -Headers @{Authorization = "Bearer $env:HA_TOKEN"} `
                      -ContentType "application/json" `
                      -Body ($Data | ConvertTo-Json -Compress)
}

function ha-services {
    <#
    .SYNOPSIS
    List alle tilgaengelige services (komplet domain.service oversigt).
    #>
    if (-not (_ha-check-token)) { return }
    Invoke-RestMethod -Uri "http://${HA_HOST}:8123/api/services" `
                      -Headers @{Authorization = "Bearer $env:HA_TOKEN"}
}

function ha-events {
    <#
    .SYNOPSIS
    List recent events (kraever EventStream subscription, simpelt eksempel).
    #>
    if (-not (_ha-check-token)) { return }
    Invoke-RestMethod -Uri "http://${HA_HOST}:8123/api/events" `
                      -Headers @{Authorization = "Bearer $env:HA_TOKEN"}
}

# -----------------------------------------------------------------------------
# Convenience shortcuts
# -----------------------------------------------------------------------------

function ha-info {
    <#
    .SYNOPSIS
    Print HA core info + supervisor info.
    #>
    Write-Host "=== HA Core info ===" -ForegroundColor Cyan
    ha-cmd "ha core info"
    Write-Host "`n=== Supervisor info ===" -ForegroundColor Cyan
    ha-cmd "ha supervisor info"
}

function ha-help {
    <#
    .SYNOPSIS
    List alle ha-* commands i denne module.
    #>
    Write-Host "HA Remote Helpers — available commands:" -ForegroundColor Cyan
    Get-Command ha-* | Sort-Object Name | ForEach-Object {
        $help = Get-Help $_.Name -Synopsis -ErrorAction SilentlyContinue
        $synopsis = if ($help.Synopsis) { $help.Synopsis } else { "(no description)" }
        Write-Host ("  {0,-25} {1}" -f $_.Name, $synopsis)
    }
    Write-Host "`nFor uddybende help: Get-Help ha-deploy -Detailed (replace 'ha-deploy' with any ha-* command)" -ForegroundColor DarkGray
}

Write-Host "HA helpers loaded. Run 'ha-help' for command list." -ForegroundColor Green
