# MaskBoundingBox component hot reload demo for Windows.

$ErrorActionPreference = 'Stop'

$appDir = "$PSScriptRoot\..\..\.."
$env:GRADIO_ANALYTICS_ENABLED = "False"

& "$appDir\.venv\Scripts\gradio.exe" cc dev "$PSScriptRoot\demo\app.py" --component-directory $PSScriptRoot
