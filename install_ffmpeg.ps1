# Download and install FFmpeg for Windows
$ffmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$downloadPath = "$env:TEMP\ffmpeg.zip"
$extractPath = "C:\ffmpeg"

Write-Host "Downloading FFmpeg..." -ForegroundColor Green
try {
    Invoke-WebRequest -Uri $ffmpegUrl -OutFile $downloadPath -UseBasicParsing
    Write-Host "Download complete!" -ForegroundColor Green
} catch {
    Write-Host "Error downloading FFmpeg: $_" -ForegroundColor Red
    exit 1
}

Write-Host "Extracting FFmpeg..." -ForegroundColor Green
try {
    Expand-Archive -Path $downloadPath -DestinationPath $env:TEMP -Force
    
    # Find the extracted folder (it has a version number)
    $ffmpegFolder = Get-ChildItem -Path $env:TEMP -Filter "ffmpeg-*" -Directory | Select-Object -First 1
    
    # Move to C:\ffmpeg
    if (Test-Path $extractPath) {
        Remove-Item $extractPath -Recurse -Force
    }
    Move-Item -Path $ffmpegFolder.FullName -Destination $extractPath
    
    Write-Host "Extraction complete!" -ForegroundColor Green
} catch {
    Write-Host "Error extracting FFmpeg: $_" -ForegroundColor Red
    exit 1
}

# Add to PATH
$ffmpegBinPath = "$extractPath\bin"
Write-Host "Adding FFmpeg to PATH..." -ForegroundColor Green

# Get current PATH
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")

# Check if already in PATH
if ($currentPath -notlike "*$ffmpegBinPath*") {
    # Add to user PATH
    $newPath = "$currentPath;$ffmpegBinPath"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    
    # Also add to current session PATH
    $env:Path += ";$ffmpegBinPath"
    
    Write-Host "FFmpeg added to PATH!" -ForegroundColor Green
} else {
    Write-Host "FFmpeg already in PATH!" -ForegroundColor Yellow
}

# Clean up
Remove-Item $downloadPath -Force -ErrorAction SilentlyContinue

Write-Host "`nFFmpeg installation complete!" -ForegroundColor Green
Write-Host "Location: $extractPath" -ForegroundColor Cyan
Write-Host "Please restart your terminal or VS Code for PATH changes to take effect." -ForegroundColor Yellow
Write-Host "`nVerifying installation..." -ForegroundColor Green

# Test ffmpeg
try {
    & "$ffmpegBinPath\ffmpeg.exe" -version | Select-Object -First 1
    Write-Host "`nFFmpeg is working correctly!" -ForegroundColor Green
} catch {
    Write-Host "`nCould not verify FFmpeg. Please restart your terminal." -ForegroundColor Yellow
}
