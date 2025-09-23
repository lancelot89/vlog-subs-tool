# scripts/test_exe.ps1
# Minimal smoke test for the Windows onedir build.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/test_exe.ps1

Write-Host "=== VLog字幕ツール PyInstaller テスト ===" -ForegroundColor Green
Write-Host "シンプルな onedir ビルドがソース実行と同じ挙動になることを確認します" -ForegroundColor Cyan

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$root/.."

# 前回成果物のクリーンアップ
Write-Host "前回のビルド成果物を削除中..." -ForegroundColor Yellow
Remove-Item -Recurse -Force ".\dist\windows" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force ".\build\windows" -ErrorAction SilentlyContinue

# PyInstallerでビルド
Write-Host "PyInstallerでonedirビルド中..." -ForegroundColor Yellow
try {
    pyinstaller `
        --clean `
        --distpath ".\dist\windows" `
        --workpath ".\build\windows" `
        ".\vlog-subs-tool.spec"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstallerビルドが失敗しました (終了コード: $LASTEXITCODE)"
    }
} catch {
    Write-Host "ビルドエラー: $_" -ForegroundColor Red
    exit 1
}

$exePath = ".\dist\windows\vlog-subs-tool\vlog-subs-tool.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "エラー: EXEファイルが生成されませんでした" -ForegroundColor Red
    Write-Host "期待されるパス: $exePath" -ForegroundColor Red
    exit 1
}

$fileSize = (Get-Item $exePath).Length / 1MB
Write-Host "EXEファイル生成成功: $exePath" -ForegroundColor Green
Write-Host "ファイルサイズ: $([math]::Round($fileSize, 2)) MB" -ForegroundColor Cyan

# 起動テスト
Write-Host "=== onedirバイナリの起動テスト ===" -ForegroundColor Green
Write-Host "GUIアプリケーションのため、ウィンドウが開いたら手動で閉じてください" -ForegroundColor Yellow

try {
    $process = Start-Process -FilePath $exePath -PassThru
    Start-Sleep -Seconds 5

    if ($process.HasExited) {
        Write-Host "エラー: EXEが予期せず終了しました (終了コード: $($process.ExitCode))" -ForegroundColor Red
        exit 1
    }

    Write-Host "成功: プロセスが起動しました (PID: $($process.Id))" -ForegroundColor Green
    Write-Host "必要に応じてUIの操作を確認してください" -ForegroundColor Cyan

    $timeout = 30
    $elapsed = 0
    while (-not $process.HasExited -and $elapsed -lt $timeout) {
        Start-Sleep -Seconds 1
        $elapsed++
    }

    if (-not $process.HasExited) {
        Write-Host "注意: テストタイムアウトのためプロセスを終了します" -ForegroundColor Yellow
        $process.Kill()
    }

    Write-Host "起動テスト完了" -ForegroundColor Green
} catch {
    Write-Host "EXE起動エラー: $_" -ForegroundColor Red
    exit 1
}

Write-Host "=== テスト完了 ===" -ForegroundColor Green
