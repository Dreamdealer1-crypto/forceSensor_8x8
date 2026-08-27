param()

$ErrorActionPreference = 'Stop'
$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$localConfig = Join-Path $toolDir 'stm32-tools.local.ps1'

if (Test-Path -LiteralPath $localConfig) {
    . $localConfig
}

function Resolve-Tool {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$ConfiguredPath
    )

    if ($ConfiguredPath -and (Test-Path -LiteralPath $ConfiguredPath)) {
        return (Resolve-Path -LiteralPath $ConfiguredPath).Path
    }

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    return $null
}

$programmer = Resolve-Tool -Name 'STM32_Programmer_CLI' -ConfiguredPath $script:STM32ProgrammerCli
$gcc = Resolve-Tool -Name 'arm-none-eabi-gcc' -ConfiguredPath $script:ArmNoneEabiGcc
$cmake = Resolve-Tool -Name 'cmake' -ConfiguredPath $script:CMake
$ninja = Resolve-Tool -Name 'ninja' -ConfiguredPath $script:Ninja
$make = Resolve-Tool -Name 'make' -ConfiguredPath $script:Make

$rows = @(
    [PSCustomObject]@{ Tool = 'STM32_Programmer_CLI'; Path = $programmer; Status = $(if ($programmer) { 'FOUND' } else { 'MISSING' }) },
    [PSCustomObject]@{ Tool = 'arm-none-eabi-gcc'; Path = $gcc; Status = $(if ($gcc) { 'FOUND' } else { 'MISSING' }) },
    [PSCustomObject]@{ Tool = 'cmake'; Path = $cmake; Status = $(if ($cmake) { 'FOUND' } else { 'MISSING' }) },
    [PSCustomObject]@{ Tool = 'ninja'; Path = $ninja; Status = $(if ($ninja) { 'FOUND' } else { 'MISSING' }) },
    [PSCustomObject]@{ Tool = 'make'; Path = $make; Status = $(if ($make) { 'FOUND' } else { 'MISSING' }) }
)

$rows | Format-Table -AutoSize

if ($programmer) {
    & $programmer --version
}

if ($gcc) {
    & $gcc --version
}

if ($cmake) {
    & $cmake --version
}

if ($ninja) {
    & $ninja --version
}

if (-not $programmer) {
    throw 'STM32_Programmer_CLI was not found. Install STM32CubeProgrammer/STM32CubeCLT or update tools\stm32-tools.local.ps1.'
}
