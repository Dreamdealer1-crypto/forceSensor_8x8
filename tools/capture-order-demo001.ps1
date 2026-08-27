param(
    [string]$Port = 'COM7',
    [int]$Baud = 115200,
    [int]$BaselineFrames = 100,
    [switch]$ManualControl,
    [switch]$NoHeatmap,
    [int]$FirstPressFrames = 40,
    [int]$ReleaseFrames = 20,
    [int]$SecondPressFrames = 40,
    [int]$FirstPressSeconds = 5,
    [int]$ReleaseSeconds = 3,
    [int]$SecondPressSeconds = 5,
    [string]$Run = 'run01'
)

$ErrorActionPreference = 'Stop'
$date = Get-Date -Format 'yyyy-MM-dd'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$rawPath = Join-Path $projectRoot "data\raw\${date}_order-demo-001_${Run}.log"
$frameCsvPath = Join-Path $projectRoot "data\csv\${date}_order-demo-001_frames_${Run}.csv"
$baselineCsvPath = Join-Path $projectRoot "data\analysis\${date}_order-demo-001_baseline_${Run}.csv"
$eventCsvPath = Join-Path $projectRoot "data\analysis\${date}_order-demo-001_events_${Run}.csv"
$summaryCsvPath = Join-Path $projectRoot "data\analysis\${date}_order-demo-001_summary_${Run}.csv"
$heatmapDir = Join-Path $projectRoot "reports\figures\${date}_order-demo-001_${Run}"

New-Item -ItemType Directory -Force -Path `
    (Join-Path $projectRoot 'data\raw'), `
    (Join-Path $projectRoot 'data\csv'), `
    (Join-Path $projectRoot 'data\analysis'), `
    $heatmapDir | Out-Null

function New-Matrix {
    $matrix = @()
    for ($row = 0; $row -lt 8; $row++) {
        $line = New-Object 'double[]' 8
        $matrix += ,$line
    }
    return $matrix
}

function Copy-Matrix([double[][]]$Source) {
    $matrix = New-Matrix
    for ($row = 0; $row -lt 8; $row++) {
        for ($col = 0; $col -lt 8; $col++) {
            $matrix[$row][$col] = $Source[$row][$col]
        }
    }
    return $matrix
}

function Read-Frame($Serial, [System.Collections.Generic.List[string]]$Lines) {
    $frame = $null
    $deadline = (Get-Date).AddSeconds(10)

    while ((Get-Date) -lt $deadline) {
        try { $line = $Serial.ReadLine().TrimEnd("`r") } catch [TimeoutException] { continue }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        $Lines.Add($line)

        if ($line -match '^FRAME,(\d+),(\d+),(\d+)') {
            $frame = [pscustomobject]@{
                seq = [int]$Matches[1]
                timestamp_us = [int64]$Matches[2]
                vref_mv = [int]$Matches[3]
                matrix = New-Matrix
                rows_seen = New-Object 'bool[]' 8
            }
            continue
        }

        if ($frame -and $line -match '^R(\d+),') {
            $parts = $line.Split(',')
            if ($parts.Count -ne 9) { continue }
            $row = [int]$Matches[1]
            if ($row -lt 0 -or $row -gt 7) { continue }
            for ($col = 0; $col -lt 8; $col++) {
                $frame.matrix[$row][$col] = [double]$parts[$col + 1]
            }
            $frame.rows_seen[$row] = $true
            continue
        }

        if ($frame -and $line -eq 'END') {
            $complete = $true
            for ($row = 0; $row -lt 8; $row++) {
                if (-not $frame.rows_seen[$row]) { $complete = $false }
            }
            if ($complete) { return $frame }
            $frame = $null
        }
    }

    throw 'Timed out waiting for one complete FRAME.'
}

function Get-Phase([datetime]$Start, [int]$FirstPressSeconds, [int]$ReleaseSeconds, [int]$SecondPressSeconds) {
    $elapsed = ((Get-Date) - $Start).TotalSeconds
    if ($elapsed -lt $FirstPressSeconds) { return 'PRESS_1' }
    if ($elapsed -lt ($FirstPressSeconds + $ReleaseSeconds)) { return 'RELEASE' }
    if ($elapsed -lt ($FirstPressSeconds + $ReleaseSeconds + $SecondPressSeconds)) { return 'PRESS_2' }
    return 'DONE'
}

function Capture-PhaseFrames(
    $Serial,
    [System.Collections.Generic.List[string]]$Lines,
    [double[][]]$Baseline,
    [double[][]]$Std,
    [string]$Phase,
    [int]$FrameCount,
    [int]$StartIndex,
    [string]$HeatmapDir,
    [System.Collections.Generic.List[object]]$DeltaRows,
    [System.Collections.Generic.List[object]]$Events,
    [bool]$DisableHeatmap
) {
    for ($i = 0; $i -lt $FrameCount; $i++) {
        $frame = Read-Frame $Serial $Lines
        $Events.Add((Analyze-Frame $frame $Baseline $Std $Phase ($StartIndex + $i) $HeatmapDir $DeltaRows $DisableHeatmap))
    }

    return $StartIndex + $FrameCount
}

function Color-ForValue([double]$Value, [double]$MaxValue) {
    if ($MaxValue -le 0) { $t = 0.0 } else { $t = [math]::Max(0.0, [math]::Min(1.0, $Value / $MaxValue)) }
    $r = [int](255.0 * $t)
    $g = [int](210.0 * (1.0 - [math]::Abs($t - 0.5) * 2.0))
    $b = [int](255.0 * (1.0 - $t))
    return [System.Drawing.Color]::FromArgb($r, $g, $b)
}

function Save-Heatmap([double[][]]$Delta, [string]$Path, [string]$Title) {
    Add-Type -AssemblyName System.Drawing
    $absolutePath = [System.IO.Path]::GetFullPath($Path)
    $parent = Split-Path -Parent $absolutePath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null

    $cell = 64
    $label = 72
    $width = $label + 8 * $cell + 16
    $height = $label + 8 * $cell + 56
    $bitmap = New-Object System.Drawing.Bitmap $width, $height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([System.Drawing.Color]::White)

    $font = New-Object System.Drawing.Font 'Consolas', 11
    $titleFont = New-Object System.Drawing.Font 'Consolas', 14, ([System.Drawing.FontStyle]::Bold)
    $brushText = [System.Drawing.Brushes]::Black
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(60, 60, 60))

    $maxValue = 0.0
    for ($row = 0; $row -lt 8; $row++) {
        for ($col = 0; $col -lt 8; $col++) {
            if ($Delta[$row][$col] -gt $maxValue) { $maxValue = $Delta[$row][$col] }
        }
    }

    $graphics.DrawString($Title, $titleFont, $brushText, 16, 12)
    for ($row = 0; $row -lt 8; $row++) {
        $graphics.DrawString("R$row", $font, $brushText, 16, ($label + $row * $cell + 22))
        for ($col = 0; $col -lt 8; $col++) {
            if ($row -eq 0) {
                $graphics.DrawString("C$col", $font, $brushText, ($label + $col * $cell + 18), 48)
            }
            $x = $label + $col * $cell
            $y = $label + $row * $cell
            $color = Color-ForValue $Delta[$row][$col] $maxValue
            $brush = New-Object System.Drawing.SolidBrush $color
            $graphics.FillRectangle($brush, $x, $y, $cell, $cell)
            $graphics.DrawRectangle($pen, $x, $y, $cell, $cell)
            $text = [string]([int][math]::Round($Delta[$row][$col]))
            $graphics.DrawString($text, $font, $brushText, ($x + 8), ($y + 22))
            $brush.Dispose()
        }
    }

    $graphics.Dispose()
    $stream = [System.IO.File]::Open($absolutePath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $stream.Dispose()
        $bitmap.Dispose()
    }
}

function Analyze-Frame($Frame, [double[][]]$Baseline, [double[][]]$Std, [string]$Phase, [int]$Index, [string]$HeatmapDir, [System.Collections.Generic.List[object]]$DeltaRows, [bool]$DisableHeatmap) {
    $delta = New-Matrix
    $maxDelta = -999999.0
    $maxRow = 0
    $maxCol = 0
    $pressed = 0

    for ($row = 0; $row -lt 8; $row++) {
        for ($col = 0; $col -lt 8; $col++) {
            $d = $Frame.matrix[$row][$col] - $Baseline[$row][$col]
            $delta[$row][$col] = $d
            $threshold = [math]::Max(8.0 * $Std[$row][$col], 300.0)
            $isPressed = $d -gt $threshold
            $DeltaRows.Add([pscustomobject]@{
                phase = $Phase
                index = $Index
                frame_seq = $Frame.seq
                timestamp_us = $Frame.timestamp_us
                row = $row
                col = $col
                raw = [int]$Frame.matrix[$row][$col]
                baseline_raw = [math]::Round($Baseline[$row][$col], 3)
                std_raw = [math]::Round($Std[$row][$col], 3)
                threshold_counts = [math]::Round($threshold, 3)
                delta = [math]::Round($d, 3)
                pressed = $isPressed
            })
            if ($d -gt $maxDelta) {
                $maxDelta = $d
                $maxRow = $row
                $maxCol = $col
            }
            if ($isPressed) { $pressed++ }
        }
    }

    $safePhase = $Phase.ToLower()
    $png = Join-Path $HeatmapDir ("frame_{0:D4}_{1}.png" -f $Index, $safePhase)
    if (-not $DisableHeatmap) {
        Save-Heatmap $delta $png ("$Phase seq=$($Frame.seq) max=R$maxRow C$maxCol d=$([int][math]::Round($maxDelta))")
    }

    return [pscustomobject]@{
        phase = $Phase
        index = $Index
        frame_seq = $Frame.seq
        timestamp_us = $Frame.timestamp_us
        max_row = $maxRow
        max_col = $maxCol
        max_delta = [math]::Round($maxDelta, 3)
        pressed_pixel_count = $pressed
        heatmap_png = if ($DisableHeatmap) { '' } else { $png }
    }
}

Write-Host 'ORDER-DEMO-001 sequence: keep still for baseline; then press point 1, release, press point 2.'
if ($ManualControl) {
    Write-Host 'Manual control enabled. Press Enter at each prompt to start that phase.'
}

$serial = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
$serial.NewLine = "`n"
$serial.ReadTimeout = 1000
$lines = New-Object System.Collections.Generic.List[string]
$baselineRows = New-Object System.Collections.Generic.List[object]
$deltaRows = New-Object System.Collections.Generic.List[object]
$events = New-Object System.Collections.Generic.List[object]

try {
    $serial.Open()
    $serial.DiscardInBuffer()

    if ($ManualControl) {
        Read-Host "Keep the sensor still, then press Enter to capture $BaselineFrames baseline frames"
    }

    $baselineFrameList = New-Object System.Collections.Generic.List[object]
    while ($baselineFrameList.Count -lt $BaselineFrames) {
        $baselineFrameList.Add((Read-Frame $serial $lines))
    }

    $baseline = New-Matrix
    $std = New-Matrix
    for ($row = 0; $row -lt 8; $row++) {
        for ($col = 0; $col -lt 8; $col++) {
            $values = @($baselineFrameList | ForEach-Object { [double]$_.matrix[$row][$col] })
            $mean = ($values | Measure-Object -Average).Average
            $sum = 0.0
            foreach ($value in $values) { $sum += [math]::Pow($value - $mean, 2) }
            $sd = if ($values.Count -gt 1) { [math]::Sqrt($sum / ($values.Count - 1)) } else { 0.0 }
            $baseline[$row][$col] = $mean
            $std[$row][$col] = $sd
        }
    }

    for ($row = 0; $row -lt 8; $row++) {
        for ($col = 0; $col -lt 8; $col++) {
            $baselineThreshold = [math]::Max(8.0 * $std[$row][$col], 300.0)
            $baselineRows.Add([pscustomobject]@{
                row = $row
                col = $col
                baseline_raw = [math]::Round($baseline[$row][$col], 3)
                std_raw = [math]::Round($std[$row][$col], 3)
                threshold_counts = [math]::Round($baselineThreshold, 3)
            })
        }
    }

    $index = 0
    if ($ManualControl) {
        Read-Host "Press point 1 and hold it, then press Enter to capture $FirstPressFrames frames"
        $index = Capture-PhaseFrames $serial $lines $baseline $std 'PRESS_1' $FirstPressFrames $index $heatmapDir $deltaRows $events $NoHeatmap.IsPresent

        Read-Host "Release completely, then press Enter to capture $ReleaseFrames release frames"
        $index = Capture-PhaseFrames $serial $lines $baseline $std 'RELEASE' $ReleaseFrames $index $heatmapDir $deltaRows $events $NoHeatmap.IsPresent

        Read-Host "Press point 2 far from point 1 and hold it, then press Enter to capture $SecondPressFrames frames"
        $index = Capture-PhaseFrames $serial $lines $baseline $std 'PRESS_2' $SecondPressFrames $index $heatmapDir $deltaRows $events $NoHeatmap.IsPresent
    }
    else {
        $phaseStart = Get-Date
        while ($true) {
            $phase = Get-Phase $phaseStart $FirstPressSeconds $ReleaseSeconds $SecondPressSeconds
            if ($phase -eq 'DONE') { break }
            $frame = Read-Frame $serial $lines
            $events.Add((Analyze-Frame $frame $baseline $std $phase $index $heatmapDir $deltaRows $NoHeatmap.IsPresent))
            $index++
        }
    }
}
finally {
    if ($serial.IsOpen) { $serial.Close() }
}

$lines | Set-Content -LiteralPath $rawPath -Encoding UTF8
$baselineRows | Export-Csv -LiteralPath $baselineCsvPath -NoTypeInformation -Encoding UTF8
$deltaRows | Export-Csv -LiteralPath $frameCsvPath -NoTypeInformation -Encoding UTF8
$events | Export-Csv -LiteralPath $eventCsvPath -NoTypeInformation -Encoding UTF8

$summary = $events |
    Group-Object phase |
    ForEach-Object {
        $phaseEvents = @($_.Group)
        $peak = $phaseEvents | Sort-Object {[double]$_.max_delta} -Descending | Select-Object -First 1
        [pscustomobject]@{
            phase = $_.Name
            frames = $phaseEvents.Count
            peak_max_row = $peak.max_row
            peak_max_col = $peak.max_col
            peak_max_delta = $peak.max_delta
            max_pressed_pixel_count = (($phaseEvents | Measure-Object pressed_pixel_count -Maximum).Maximum)
            peak_heatmap_png = $peak.heatmap_png
        }
    }
$summary | Export-Csv -LiteralPath $summaryCsvPath -NoTypeInformation -Encoding UTF8

Write-Host "Raw log: $rawPath"
Write-Host "Frames CSV: $frameCsvPath"
Write-Host "Baseline CSV: $baselineCsvPath"
Write-Host "Events CSV: $eventCsvPath"
Write-Host "Summary CSV: $summaryCsvPath"
Write-Host "Heatmaps: $heatmapDir"
$summary | Format-Table -AutoSize
