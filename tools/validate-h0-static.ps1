param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ })]
    [string]$VoltageCsv,

    [ValidateScript({ -not $_ -or (Test-Path -LiteralPath $_) })]
    [string]$ObservationCsv
)

$ErrorActionPreference = 'Stop'

function Convert-ToNullableDouble {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }
    return [double]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)
}

$rows = Import-Csv -LiteralPath $VoltageCsv
$missing = @()
$rangeFailures = @()
$railWarnings = @()
$qualitativeNotes = @()
$observationNotes = @()

foreach ($row in $rows) {
    $measured = Convert-ToNullableDouble $row.measured_v
    if ($null -eq $measured) {
        if ($row.condition -eq 'NORMAL_REPORTED') {
            $qualitativeNotes += "$($row.measurement_id) $($row.device) $($row.pin) reported normal without exact voltage"
            continue
        }
        $missing += $row.measurement_id
        continue
    }

    $min = Convert-ToNullableDouble $row.expected_v_min
    $max = Convert-ToNullableDouble $row.expected_v_max

    if (($null -ne $min -and $measured -lt $min) -or ($null -ne $max -and $measured -gt $max)) {
        $rangeFailures += "$($row.measurement_id) $($row.device) $($row.pin) measured=$measured V expected=$min..$max V"
    }

    if ($row.node -like '*TIA_OUTPUT' -and ($measured -le 0.05 -or $measured -ge 3.25)) {
        $railWarnings += "$($row.measurement_id) $($row.device) $($row.pin) output near rail: $measured V"
    }
}

$observationWarnings = @()
if ($ObservationCsv) {
    $observations = Import-Csv -LiteralPath $ObservationCsv
    foreach ($obs in $observations) {
        if ($obs.status -eq 'UNKNOWN' -or [string]::IsNullOrWhiteSpace($obs.status)) {
            $observationWarnings += "$($obs.observation_id) $($obs.item) is UNKNOWN"
        }
        elseif ($obs.status -eq 'NOT_REPORTED') {
            $observationNotes += "$($obs.observation_id) $($obs.item) is NOT_REPORTED"
        }
        elseif ($obs.item -like '*abnormal_heat' -and $obs.status -match 'YES|TRUE|PRESENT') {
            $observationWarnings += "$($obs.observation_id) $($obs.item): $($obs.status)"
        }
        elseif ($obs.item -like '*oscillation_present' -and $obs.status -match 'YES|TRUE|PRESENT') {
            $observationWarnings += "$($obs.observation_id) $($obs.item): $($obs.status)"
        }
        elseif ($obs.item -eq 'any_output_close_to_0v_or_3v3' -and $obs.status -match 'YES|TRUE|PRESENT') {
            $observationWarnings += "$($obs.observation_id) $($obs.item): $($obs.status)"
        }
    }
}

Write-Host "H0 static validation"
Write-Host "Voltage file: $VoltageCsv"
if ($ObservationCsv) {
    Write-Host "Observation file: $ObservationCsv"
}

if ($missing.Count) {
    Write-Host "`nMissing voltage values:"
    $missing | ForEach-Object { Write-Host "  $_" }
}

if ($rangeFailures.Count) {
    Write-Host "`nVoltage values outside expected range:"
    $rangeFailures | ForEach-Object { Write-Host "  $_" }
}

if ($railWarnings.Count) {
    Write-Host "`nTIA output rail warnings:"
    $railWarnings | ForEach-Object { Write-Host "  $_" }
}

if ($qualitativeNotes.Count) {
    Write-Host "`nQualitative normal reports:"
    $qualitativeNotes | ForEach-Object { Write-Host "  $_" }
}

if ($observationWarnings.Count) {
    Write-Host "`nObservation warnings:"
    $observationWarnings | ForEach-Object { Write-Host "  $_" }
}

if ($observationNotes.Count) {
    Write-Host "`nObservation notes:"
    $observationNotes | ForEach-Object { Write-Host "  $_" }
}

if ($missing.Count -or $rangeFailures.Count -or $railWarnings.Count -or $observationWarnings.Count) {
    Write-Host "`nResult: WAITING_OR_REWORK"
    exit 2
}

if ($qualitativeNotes.Count) {
    Write-Host "`nResult: READY_FOR_SUPERVISOR_REVIEW_WITH_QUALITATIVE_NOTES"
    exit 0
}

Write-Host "`nResult: READY_FOR_SUPERVISOR_REVIEW"
exit 0
