while ($true) {
    Write-Host "Starting localtunnel..."
    try {
        # mystorybook 서브도메인 사용 (실패 시 랜덤 URL 할당될 수 있음)
        npx localtunnel --port 8000 --subdomain mystorybook
    }
    catch {
        Write-Host "Localtunnel process crashed. Restarting in 3 seconds..."
        Start-Sleep -Seconds 3
    }
    # npx가 에러 없이 종료되는 경우에도 재시작
    Write-Host "Localtunnel disconnected. Restarting in 3 seconds..."
    Start-Sleep -Seconds 3
}
