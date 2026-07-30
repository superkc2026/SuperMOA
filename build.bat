@echo off
chcp 65001 >nul
echo ========================================
echo   SuperMOA - PyInstaller Build
echo ========================================
echo.

REM 检查 venv
if not exist .venv\Scripts\activate.bat (
    echo [ERROR] .venv not found. Run: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM 清理旧产物
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist SuperMOA.spec del SuperMOA.spec

REM 激活 venv
call .venv\Scripts\activate.bat

REM 安装/确认 pyinstaller
pip install pyinstaller -q

REM 打包
pyinstaller ^
    --noconsole ^
    --onefile ^
    --name SuperMOA ^
    --add-data "web;web" ^
    --add-data "engine;engine" ^
    --hidden-import fastapi ^
    --hidden-import uvicorn ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import httpx ^
    --hidden-import yaml ^
    --hidden-import bcrypt ^
    --hidden-import pystray ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageDraw ^
    --hidden-import PIL.ImageFont ^
    --hidden-import slowapi ^
    --hidden-import multipart ^
    --hidden-import requests ^
    --hidden-import engine ^
    --hidden-import engine.config ^
    --hidden-import engine.auth ^
    --hidden-import engine.orchestrator ^
    --hidden-import engine.streaming ^
    --hidden-import engine.vendors ^
    --hidden-import engine.constants ^
    --hidden-import engine.exceptions ^
    --hidden-import engine.log_manager ^
    --hidden-import engine.updater ^
    --hidden-import engine.error_reporter ^
    tray.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [FAILED] Build error
    pause
    exit /b 1
)

echo.
echo ========================================
echo   BUILD OK - Post-processing
echo ========================================

REM --- 代码签名 ---
REM 暂无代码签名证书，先跳过签名，仅做 SHA256 校验和
echo [INFO] Code signing: SKIPPED (no certificate)
echo [WARN]  For distribution, obtain a code signing certificate.

REM --- SHA256 校验和 ---
echo.
echo [INFO] Generating SHA256 checksum...
certutil -hashfile dist\SuperMOA.exe SHA256 > dist\SuperMOA.exe.sha256

if %ERRORLEVEL% NEQ 0 (
    echo [WARN] SHA256 checksum generation failed
) else (
    echo [OK] SHA256 checksum: dist\SuperMOA.exe.sha256
)

REM --- 输出文件清单 ---
echo.
echo ========================================
echo   BUILD COMPLETE
echo ========================================
echo   Output:
echo     dist\SuperMOA.exe
echo     dist\SuperMOA.exe.sha256
echo ========================================
pause
