param(
    [string]$Port = 'COM7',
    [int]$BaselineFrames = 100,
    [double]$FullScaleDelta = 18000.0,
    [double]$ThresholdMin = 60.0,
    [double]$ThresholdSigma = 2.5,
    [int]$LogEvery = 5,
    [switch]$PrintSummary,
    [string]$Run = ''
)

$ErrorActionPreference = 'Stop'
$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $toolDir

if ([string]::IsNullOrWhiteSpace($Run)) {
    $Run = "$(Get-Date -Format 'yyyy-MM-dd')_order-live-pressure_run01"
}

Push-Location $projectRoot
try {
    $args = @(
        '.\tools\live_pressure_heatmap.py',
        '--port', $Port,
        '--baseline-frames', $BaselineFrames,
        '--full-scale-delta', $FullScaleDelta,
        '--threshold-min', $ThresholdMin,
        '--threshold-sigma', $ThresholdSigma,
        '--log-every', $LogEvery,
        '--run', $Run
    )
    if ($PrintSummary) {
        $args += '--print-summary'
    }

    python @args
}
finally {
    Pop-Location
}
