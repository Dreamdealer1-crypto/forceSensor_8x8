param(
    [string]$Run = 'run01_order003e',
    [double]$Vref = 1.03,
    [double]$Vdda = 3.3,
    [double]$RfOhm = 10000.0,
    [int]$AdcFullScale = 65535,
    [int]$MinSamples = 30,
    [int]$MaxSamples = 50
)

$ErrorActionPreference = 'Stop'
$resistors = @(
    @{ label = '10k'; ohm = 10000.0 },
    @{ label = '22k'; ohm = 22000.0 },
    @{ label = '47k'; ohm = 47000.0 },
    @{ label = '100k'; ohm = 100000.0 }
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
    if ($target.Count -lt $MinSamples -or $target.Count -gt $MaxSamples) {
        throw "$($r.label) has $($target.Count) ROW0/COL0 samples; expected $MinSamples..$MaxSamples."
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

$xs = @($summary | ForEach-Object { [double]$_.inv_r })
$ys = @($summary | ForEach-Object { [double]$_.delta_v })
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
$summaryPath = ".\data\analysis\${date}_order-003e_quick_transfer_summary_${Run}.csv"
$fitPath = ".\data\analysis\${date}_order-003e_quick_transfer_fit_${Run}.csv"
$summary | Export-Csv -LiteralPath $summaryPath -NoTypeInformation -Encoding UTF8
[pscustomobject]@{
    fit_range = '10k_22k_47k_100k'
    x = '1/R'
    y = 'delta_v'
    slope = [math]::Round($slope, 6)
    intercept = [math]::Round($intercept, 6)
    r_squared = [math]::Round($r2, 6)
} | Export-Csv -LiteralPath $fitPath -NoTypeInformation -Encoding UTF8

Write-Host "Summary: $summaryPath"
Write-Host "Fit: $fitPath"
$summary | Format-Table resistance_label,samples,mean_adc,std_adc,mean_voltage_v,delta_v,theory_delta_v,error_pct -AutoSize
Write-Host "R^2(10k,22k,47k,100k) = $([math]::Round($r2, 6))"
