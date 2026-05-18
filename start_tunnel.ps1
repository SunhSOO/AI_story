param(
    [string]$Subdomain = "mystorybook",
    [int]$Port = 8000,
    [int]$RetrySeconds = 3,
    [string]$LocalHost = "127.0.0.1"
)

$ExpectedUrl = "https://$Subdomain.loca.lt"
$BypassUrl = "$ExpectedUrl/?bypass-tunnel-reminder=true"

function Remove-AnsiEscape {
    param([string]$Text)

    return $Text -replace "$([char]27)\[[0-9;]*[A-Za-z]", ""
}

function Test-LocalPort {
    param(
        [string]$HostName,
        [int]$PortNumber
    )

    $client = New-Object System.Net.Sockets.TcpClient

    try {
        $asyncResult = $client.BeginConnect($HostName, $PortNumber, $null, $null)

        if (-not $asyncResult.AsyncWaitHandle.WaitOne(1000, $false)) {
            return $false
        }

        $client.EndConnect($asyncResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Start-LocalTunnel {
    Write-Host "Starting localtunnel..."
    Write-Host "Requested URL: $ExpectedUrl"
    Write-Host "Requested bypass URL: $BypassUrl"
    Write-Host "Forwarding to: http://$LocalHost`:$Port"

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $process.StartInfo.FileName = "cmd.exe"
    $process.StartInfo.Arguments = "/d /s /c ""npx.cmd --yes localtunnel --port $Port --local-host $LocalHost --subdomain $Subdomain 2>&1"""
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $false
    $process.StartInfo.CreateNoWindow = $true

    try {
        if (-not $process.Start()) {
            throw "Failed to start localtunnel."
        }

        while ($true) {
            $line = $process.StandardOutput.ReadLine()

            if ($null -eq $line) {
                break
            }

            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }

            $cleanLine = Remove-AnsiEscape -Text $line
            Write-Host $cleanLine

            if ($cleanLine -match "https://[^\s]+") {
                $actualUrl = $Matches[0].TrimEnd([char[]]@("/", ".", ",", ")"))
                $actualBypassUrl = "$actualUrl/?bypass-tunnel-reminder=true"

                if ($actualUrl -eq $ExpectedUrl) {
                    Write-Host "Tunnel ready: $actualUrl"
                    Write-Host "Bypass URL: $actualBypassUrl"
                }
                else {
                    Write-Host "Requested subdomain was not assigned."
                    Write-Host "Use actual URL: $actualUrl"
                    Write-Host "Actual bypass URL: $actualBypassUrl"
                    Write-Host "If $ExpectedUrl is required, close the other tunnel using that subdomain and restart this script."
                }
            }
        }

        if (-not $process.HasExited) {
            $process.WaitForExit()
        }

        Write-Host "Localtunnel exit code: $($process.ExitCode)"
    }
    finally {
        try {
            if (-not $process.HasExited) {
                $process.Kill()
            }
        }
        catch {
            Write-Host "Failed to stop localtunnel process: $($_.Exception.Message)"
        }

        $process.Dispose()
    }
}

while ($true) {
    if (-not (Test-LocalPort -HostName $LocalHost -PortNumber $Port)) {
        Write-Host "Waiting for backend: http://$LocalHost`:$Port"
        Start-Sleep -Seconds $RetrySeconds
        continue
    }

    try {
        Start-LocalTunnel
    }
    catch {
        Write-Host "Localtunnel process crashed: $($_.Exception.Message)"
    }

    Write-Host "Localtunnel disconnected. Restarting in $RetrySeconds seconds..."
    Start-Sleep -Seconds $RetrySeconds
}
