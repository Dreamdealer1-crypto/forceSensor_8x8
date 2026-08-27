param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ })]
    [string]$Firmware,

    [string]$Address = '0x08000000',
    [string]$Port = 'SWD',
    [string]$Mode = 'UR',
    [string]$Reset = 'HWrst',
    [switch]$NoVerify
)

$ErrorActionPreference = 'Stop'
$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$localConfig = Join-Path $toolDir 'stm32-tools.local.ps1'

if (Test-Path -LiteralPath $localConfig) {
    . $localConfig
}

function Resolve-Programmer {
    if ($script:STM32ProgrammerCli -and (Test-Path -LiteralPath $script:STM32ProgrammerCli)) {
        return (Resolve-Path -LiteralPath $script:STM32ProgrammerCli).Path
    }

    $cmd = Get-Command 'STM32_Programmer_CLI' -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw 'STM32_Programmer_CLI was not found. Run tools\check-stm32-tools.ps1, then update tools\stm32-tools.local.ps1 if needed.'
}

$programmer = Resolve-Programmer
$firmwarePath = (Resolve-Path -LiteralPath $Firmware).Path
$extension = [IO.Path]::GetExtension($firmwarePath).ToLowerInvariant()

$connectArgs = @('-c', "port=$Port", "mode=$Mode", "reset=$Reset")
$writeArgs = @('-w', $firmwarePath)

if ($extension -eq '.bin') {
    $writeArgs += $Address
}
elseif ($extension -notin @('.hex', '.elf')) {
    throw "Unsupported firmware extension '$extension'. Use .hex, .elf, or .bin."
}

if (-not $NoVerify) {
    $writeArgs += '-v'
}

$args = $connectArgs + $writeArgs + @('-rst')

Write-Host "Using STM32 programmer: $programmer"
Write-Host "Flashing firmware: $firmwarePath"
& $programmer @args
exit $LASTEXITCODE
