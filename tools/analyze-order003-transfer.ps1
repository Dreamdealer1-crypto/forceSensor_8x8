param(
    [string]$Run = 'run01',
    [double]$Vref = 1.03,
    [double]$Vdda = 3.3,
    [double]$RfOhm = 10000.0,
    [int]$AdcFullScale = 65535
)

$ErrorActionPreference = 'Stop'
$resistors = @(
    @{ label = '10k'; ohm = 10000.0 },
    @{ label = '22k'; ohm = 22000.0 },
    @{ label = '47k'; ohm = 47000.0 },
    @{ label = '68k'; ohm = 68000.0 },
    @{ label = '100k'; ohm = 100000.0 },
    @{ label = '220k'; ohm = 220000.0 },
    @{ label = '470k'; ohm = 470000.0 },
    @{ label = '1.5M'; ohm = 1500000.0 }
)

function Mean([double[]]$Values) {
    return ($Values | Measure-Object -Average).Average
}

function StdSample([double[]]$Values, [double]$MeanValue) {
    if ($Values.Count -lt 2) { return 0.0 }
    $sum = 0.0
    foreach ($value in $Values) {
        $sum += [math]::Pow($value - $MeanValue, 2)
    }
    return [math]::Sqrt($sum / ($Values.Count - 1))
}

$summary = New-Object System.Collections.Generic.List[object]

foreach ($r in $resistors) {
    $safe = $r.label.ToLower().Replace('.', 'p')
    $path = ".\data\csv\*_order-003_transfer_${safe}_${Run}.csv"
    $file = Get-ChildItem -Path $path -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $file) {
        throw "Missing capture CSV for $($r.label): $path"
    }

    $rows = Import-Csv -LiteralPath $file.FullName
    $target = @($rows | Where-Object { [int]$_.row -eq 0 -and [int]$_.col -eq 0 } | ForEach-Object { [double]$_.adc_raw })
    if ($target.Count -lt 100) {
        throw "$($r.label) has $($target.Count) ROW0/COL0 samples; expected at least 100."
    }

    $meanAdc = Mean $target
    $stdAdc = StdSample $target $meanAdc
    $meanVoltage = $meanAdc * $Vdda / $AdcFullScale
    $deltaV = $meanVoltage - $Vref
    $theoryDeltaV = $Vref * $RfOhm / [double]$r.ohm
    $theoryVout = $Vref + $theoryDeltaV
    $errorV = $deltaV - $theoryDeltaV
    $errorPct = if ([math]::Abs($theoryDeltaV) -gt 1e-12) { 100.0 * $errorV / $theoryDeltaV } else { 0.0 }

    $summary.Add([pscustomobject]@{
        resistance_label = $r.label
        resistance_ohm = [int]$r.ohm
        inv_r = 1.0 / [double]$r.ohm
        samples = $target.Count
        mean_adc = [math]::Round($meanAdc, 3)
        std_adc = [math]::Round($stdAdc, 3)
        mean_voltage_v = [math]::Round($meanVoltage, 6)
        delta_v = [math]::Round($deltaV, 6)
        theory_vout_v = [math]::Round($theoryVout, 6)
        theory_delta_v = [math]::Round($theoryDeltaV, 6)
        error_v = [math]::Round($errorV, 6)
        error_pct = [math]::Round($errorPct, 3)
        source_csv = $file.FullName
    })
}

$fitRows = @($summary | Where-Object { [double]$_.resistance_ohm -ge 10000.0 -and [double]$_.resistance_ohm -le 220000.0 })
$xs = @($fitRows | ForEach-Object { [double]$_.inv_r })
$ys = @($fitRows | ForEach-Object { [double]$_.delta_v })
$xMean = Mean $xs
$yMean = Mean $ys
$sxx = 0.0
$sxy = 0.0
for ($i = 0; $i -lt $xs.Count; $i++) {
    $sxx += ($xs[$i] - $xMean) * ($xs[$i] - $xMean)
    $sxy += ($xs[$i] - $xMean) * ($ys[$i] - $yMean)
}
$slope = $sxy / $sxx
$intercept = $yMean - $slope * $xMean
$sst = 0.0
$sse = 0.0
for ($i = 0; $i -lt $xs.Count; $i++) {
    $pred = $intercept + $slope * $xs[$i]
    $sst += ($ys[$i] - $yMean) * ($ys[$i] - $yMean)
    $sse += ($ys[$i] - $pred) * ($ys[$i] - $pred)
}
$r2 = 1.0 - ($sse / $sst)

$date = Get-Date -Format 'yyyy-MM-dd'
$summaryPath = ".\data\analysis\${date}_order-003_transfer_summary_${Run}.csv"
$fitPath = ".\data\analysis\${date}_order-003_transfer_fit_${Run}.csv"
$summary | Export-Csv -LiteralPath $summaryPath -NoTypeInformation -Encoding UTF8
[pscustomobject]@{
    fit_range = '10k_to_220k'
    x = '1/R'
    y = 'delta_v'
    slope = [math]::Round($slope, 6)
    intercept = [math]::Round($intercept, 6)
    r_squared = [math]::Round($r2, 6)
    pass_r2 = ($r2 -ge 0.995)
} | Export-Csv -LiteralPath $fitPath -NoTypeInformation -Encoding UTF8

Write-Host "Summary: $summaryPath"
Write-Host "Fit: $fitPath"
$summary | Format-Table resistance_label,mean_adc,std_adc,delta_v,theory_delta_v,error_pct -AutoSize
Write-Host "R^2(10k..220k) = $([math]::Round($r2, 6))"
