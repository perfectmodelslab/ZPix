# ZPix building script for Windows.

param(
    [ValidateSet("exe", "grc")]
    [string]$Target
)
# -Target exe only builds the launcher executable,
# -Target grc only the Gradio custom components.
# Both are built when no target is given.

$ErrorActionPreference = 'Stop'

function New-LauncherExecutable {
    $vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"

    if (-not (Test-Path $vsWhere)) {
        Write-Host "Visual Studio is required. Get it here: https://aka.ms/vs/download"
        exit 1
    }

    $vsPath = & $vsWhere -latest -property installationPath
    Import-Module "$vsPath\Common7\Tools\Microsoft.VisualStudio.DevShell.dll"
    Enter-VsDevShell -VsInstallPath $vsPath -SkipAutomaticLocation

    vcpkg install
    if ($LASTEXITCODE -ne 0) { exit 1 }

    cmake -B build -S .
    if ($LASTEXITCODE -ne 0) { exit 1 }

    cmake --build build --config Release
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

function New-GradioComponents {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host "Node.js is required. Get it here: https://nodejs.org"
        exit 1
    }

    $env:GRADIO_ANALYTICS_ENABLED = "False"
    $uv = "tools\astral\uv.exe"

    # Gradio builds Python packages with the build module.
    & $uv pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { exit 1 }

    foreach ($component in Get-ChildItem "source\gr" -Directory) {
        $componentDir = $component.FullName

        # Gradio requires an editable install to build.
        & $uv pip install -e $componentDir
        if ($LASTEXITCODE -ne 0) { exit 1 }

        npm install --prefix "$componentDir\frontend"
        if ($LASTEXITCODE -ne 0) { exit 1 }

        if (Test-Path "$componentDir\dist") {
            Remove-Item "$componentDir\dist" -Recurse -Force
        }

        # Gradio rewrites pyproject.toml on build, breaking it on Windows.
        $pyproject = [IO.File]::ReadAllBytes("$componentDir\pyproject.toml")
        try {
            & $uv run gradio cc build $componentDir --no-generate-docs
        } finally {
            [IO.File]::WriteAllBytes("$componentDir\pyproject.toml", $pyproject)
        }
        if ($LASTEXITCODE -ne 0) { exit 1 }

        foreach ($wheel in Get-ChildItem "$componentDir\dist\*.whl") {
            # Removes previous versions of this wheel.
            $package = $wheel.Name.Split("-")[0]
            Remove-Item "wheels\$package-*.whl"

            Copy-Item $wheel.FullName "wheels"
        }
    }

    Write-Host "All wheels copied to $PSScriptRoot\wheels"
}

# Paths resolve from this script's directory.
Push-Location $PSScriptRoot

try {
    if ($Target -ne "grc") { New-LauncherExecutable }
    if ($Target -ne "exe") { New-GradioComponents }
} finally {
    Pop-Location
}
