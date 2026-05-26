@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================
echo   光伏短视频工具 V1.0
echo ================================
echo.
echo 启动服务: http://127.0.0.1:8765
echo 按 Ctrl+C 停止服务
echo ================================
echo.
python server.py
pause
