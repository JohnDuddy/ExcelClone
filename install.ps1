[CmdletBinding()]
param(
    [string]$DesktopDir = [Environment]::GetFolderPath("Desktop")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

try {
    $installDir = (Resolve-Path -LiteralPath $PSScriptRoot).Path
    $requiredPython = "C:\Users\drdud\AppData\Local\Programs\Python\Python313\python.exe"
    $pythonCommand = $null
    $pythonPrefix = @()

    if (Test-Path -LiteralPath $requiredPython -PathType Leaf) {
        $pythonCommand = $requiredPython
    }
    else {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($null -ne $launcher) {
            & $launcher.Source -3.13 -c "import sys; raise SystemExit(sys.version_info[:2] != (3, 13))"
            if ($LASTEXITCODE -eq 0) {
                $pythonCommand = $launcher.Source
                $pythonPrefix = @("-3.13")
            }
        }
    }

    if ($null -eq $pythonCommand) {
        throw "Python 3.13 was not found. Download it from https://www.python.org/downloads/windows/ and rerun INSTALL.bat."
    }

    $version = (& $pythonCommand @pythonPrefix -c "import platform; print(platform.python_version())").Trim()
    if (-not $version.StartsWith("3.13.")) {
        throw "Python 3.13 is required; found $version."
    }

    $requirements = Join-Path $installDir "requirements.txt"
    $wheelhouse = Join-Path $installDir "wheelhouse"
    $iconPath = Join-Path $installDir "assets\duddysheet.ico"
    foreach ($required in @($requirements, $wheelhouse, $iconPath, (Join-Path $installDir "run.py"))) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Required installation content is missing: $required"
        }
    }

    $venvDir = Join-Path $installDir ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    $venvPythonw = Join-Path $venvDir "Scripts\pythonw.exe"
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        Invoke-Checked -FilePath $pythonCommand `
            -Arguments (@($pythonPrefix) + @("-m", "venv", $venvDir)) `
            -FailureMessage "Could not create the DuddySpreadsheet virtual environment"
    }

    Invoke-Checked -FilePath $venvPython `
        -Arguments @(
            "-m", "pip", "install",
            "--disable-pip-version-check",
            "--no-index",
            "--find-links", $wheelhouse,
            "-r", $requirements
        ) `
        -FailureMessage "Offline dependency installation failed"

    Push-Location $installDir
    try {
        Invoke-Checked -FilePath $venvPython `
            -Arguments @("-c", "import duddysheet; print('OK')") `
            -FailureMessage "DuddySpreadsheet smoke test failed"
    }
    finally {
        Pop-Location
    }

    New-Item -ItemType Directory -Path $DesktopDir -Force | Out-Null
    $shortcutPath = Join-Path $DesktopDir "DuddySpreadsheet.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $venvPythonw
    $shortcut.Arguments = '"run.py"'
    $shortcut.WorkingDirectory = $installDir
    $shortcut.IconLocation = "$iconPath,0"
    $shortcut.Description = "Duddy Spreadsheet personal spreadsheet"
    $shortcut.Save()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)

    $packages = (& $venvPython -c "import matplotlib,numpy,openpyxl,dateutil,PySide6; print(f'PySide6 {PySide6.__version__}; openpyxl {openpyxl.__version__}; matplotlib {matplotlib.__version__}; numpy {numpy.__version__}; python-dateutil {dateutil.__version__}')").Trim()
    Write-Host ""
    Write-Host "DuddySpreadsheet installation complete."
    Write-Host "Install path:  $installDir"
    Write-Host "Virtual env:   $venvDir"
    Write-Host "Shortcut:      $shortcutPath"
    Write-Host "Python:        $version"
    Write-Host "Packages:      $packages"
}
catch {
    Write-Error $_
    exit 1
}
