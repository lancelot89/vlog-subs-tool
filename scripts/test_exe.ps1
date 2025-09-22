# scripts/test_exe.ps1
# Issue #204 対応: EXE起動テストスクリプト
# 使用方法: powershell -ExecutionPolicy Bypass -File scripts/test_exe.ps1

Write-Host "=== VLog字幕ツール EXE起動テスト ===" -ForegroundColor Green
Write-Host "Issue #204 paddlex初期化エラー対応の検証" -ForegroundColor Cyan

# 作業ディレクトリの確認
$workDir = Get-Location
Write-Host "作業ディレクトリ: $workDir" -ForegroundColor Yellow

# 前回のビルド成果物をクリーンアップ
Write-Host "前回のビルドファイルをクリーンアップ中..." -ForegroundColor Yellow
if (Test-Path ".\dist\") {
    Remove-Item -Recurse -Force ".\dist\*" -ErrorAction SilentlyContinue
}
if (Test-Path ".\build\") {
    Remove-Item -Recurse -Force ".\build\*" -ErrorAction SilentlyContinue
}

# PyInstallerでビルド実行
Write-Host "PyInstallerでEXEビルド中..." -ForegroundColor Yellow
try {
    pyinstaller `
        --onefile `
        --windowed `
        --name "vlog-subs-tool" `
        --additional-hooks-dir="hooks" `
        --exclude-module "paddlex" `
        --exclude-module "paddlex-inference" `
        --hidden-import "PySide6.QtCore" `
        --hidden-import "PySide6.QtGui" `
        --hidden-import "PySide6.QtWidgets" `
        --hidden-import "paddleocr" `
        --hidden-import "paddle" `
        --hidden-import "cv2" `
        --hidden-import "numpy" `
        --hidden-import "psutil" `
        --exclude-module "tkinter" `
        --exclude-module "matplotlib" `
        --noupx `
        "app/main.py"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstallerビルドが失敗しました (終了コード: $LASTEXITCODE)"
    }
} catch {
    Write-Host "ビルドエラー: $_" -ForegroundColor Red
    exit 1
}

# ビルド成果物の確認
$exePath = ".\dist\vlog-subs-tool.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "エラー: EXEファイルが生成されませんでした" -ForegroundColor Red
    Write-Host "期待されるパス: $exePath" -ForegroundColor Red
    exit 1
}

# ファイルサイズの表示
$fileSize = (Get-Item $exePath).Length / 1MB
Write-Host "EXEファイル生成成功: $exePath" -ForegroundColor Green
Write-Host "ファイルサイズ: $([math]::Round($fileSize, 2)) MB" -ForegroundColor Cyan

# EXE起動テスト
Write-Host "=== EXE起動テスト実行 ===" -ForegroundColor Green
Write-Host "注意: GUIアプリケーションのため、手動でウィンドウを閉じてください" -ForegroundColor Yellow

try {
    # バックグラウンドでEXEを起動
    $process = Start-Process -FilePath $exePath -PassThru

    # 5秒待機してプロセスの状態を確認
    Start-Sleep -Seconds 5

    if ($process.HasExited) {
        Write-Host "エラー: EXEが予期せず終了しました (終了コード: $($process.ExitCode))" -ForegroundColor Red

        # エラーログがあれば表示を試行
        if (Test-Path ".\vlog-subs-tool.log") {
            Write-Host "ログファイルの内容:" -ForegroundColor Yellow
            Get-Content ".\vlog-subs-tool.log" | Select-Object -Last 20
        }

        exit 1
    } else {
        Write-Host "成功: EXEが正常に起動しました (PID: $($process.Id))" -ForegroundColor Green
        Write-Host "プロセスは動作中です。手動でアプリケーションを閉じてください。" -ForegroundColor Cyan

        # プロセスの終了を待機（タイムアウト付き）
        $timeout = 30  # 30秒でタイムアウト
        $waited = 0
        while (-not $process.HasExited -and $waited -lt $timeout) {
            Start-Sleep -Seconds 1
            $waited++
        }

        if (-not $process.HasExited) {
            Write-Host "警告: プロセスが30秒以内に終了しませんでした。手動でプロセスを終了します。" -ForegroundColor Yellow
            $process.Kill()
        }

        Write-Host "EXE起動テスト完了" -ForegroundColor Green
    }
} catch {
    Write-Host "EXE起動エラー: $_" -ForegroundColor Red
    exit 1
}

Write-Host "=== テスト完了 ===" -ForegroundColor Green
Write-Host "Issue #204 の修正が正常に動作することを確認しました" -ForegroundColor Cyan