# Verify config.json
$content = Get-Content 'D:\proiect\已完结\坤云平台定时处理\config.json' -Raw
Write-Host "File length: $($content.Length) characters"
Write-Host ""

try {
    $json = $content | ConvertFrom-Json
    Write-Host "JSON is VALID" -ForegroundColor Green
    Write-Host ""
    Write-Host "Description: $($json.description)"
    Write-Host "Platform: $($json.platform)"
    Write-Host "Tasks count: $($json.cleanupTasks.Count)"
} catch {
    Write-Host "JSON is INVALID: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "First 200 chars:" -ForegroundColor Gray
    Write-Host $content.Substring(0, [Math]::Min(200, $content.Length))
}
