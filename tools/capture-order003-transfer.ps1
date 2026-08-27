param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('10k','22k','47k','68k','100k','220k','470k','1M','1.5M')]
    [string]$Resistance,

    [string]$Port = 'COM7',
    [int]$Frames = 100,
    [int]$Baud = 115200,
    [string]$Run = 'run01'
)

$ErrorActionPreference = 'Stop'
$date = Get-Date -Format 'yyyy-MM-dd'
$safeR = $Resistance.ToLower().Replace('.', 'p')
$rawPath = ".\data\raw\${date}_order-003_transfer_${safeR}_${Run}.log"
$csvPath = ".\data\csv\${date}_order-003_transfer_${safeR}_${Run}.csv"

New-Item -ItemType Directory -Force -Path '.\data\raw', '.\data\csv' | Out-Null

$serial = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
$serial.NewLine = "`n"
$serial.ReadTimeout = 3000

$lines = New-Object System.Collections.Generic.List[string]
$rows = New-Object System.Collections.Generic.List[object]
$frame = -1
$timestampUs = ''
$vrefMv = ''
$endCount = 0
$captureActive = $false
$currentFrameRows = New-Object System.Collections.Generic.List[object]

try {
    $serial.Open()
    $serial.DiscardInBuffer()
    $deadline = (Get-Date).AddMinutes(3)

    while ((Get-Date) -lt $deadline -and $endCount -lt $Frames) {
        try {
            $line = $serial.ReadLine().TrimEnd("`r")
        }
        catch [TimeoutException] {
            continue
        }

        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        if ($line -match '^FRAME,(\d+),(\d+),(\d+)') {
            $frame = [int]$Matches[1]
            $timestampUs = $Matches[2]
            $vrefMv = $Matches[3]
            $captureActive = $true
            $currentFrameRows.Clear()
            $lines.Add($line)
            continue
        }

        if ($captureActive -and $line -match '^R(\d+),') {
            $parts = $line.Split(',')
            $row = [int]$Matches[1]
            for ($col = 0; $col -lt 8; $col++) {
                $currentFrameRows.Add([pscustomobject]@{
                    resistance = $Resistance
                    frame = $frame
                    timestamp_us = $timestampUs
                    vref_mv = $vrefMv
                    row = $row
                    col = $col
                    adc_raw = [int]$parts[$col + 1]
                })
            }
            $lines.Add($line)
            continue
        }

        if ($captureActive -and $line -eq 'END') {
            if ($currentFrameRows.Count -eq 64) {
                foreach ($rowItem in $currentFrameRows) {
                    $rows.Add($rowItem)
                }
                $lines.Add($line)
            }
            $endCount++
            $captureActive = $false
        }
    }
}
finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
}

$lines | Set-Content -LiteralPath $rawPath -Encoding UTF8
$rows | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8

Write-Host "Resistance: $Resistance"
Write-Host "Captured complete frames: $endCount"
Write-Host "Raw log: $rawPath"
Write-Host "CSV: $csvPath"

if ($endCount -lt $Frames) {
    throw "Captured only $endCount complete frames, expected at least $Frames."
}
