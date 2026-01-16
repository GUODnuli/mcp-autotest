@echo off

echo ====================================
echo MCP 接口测试智能体 - 开发模式
echo 热重载已启用
echo ====================================
echo.

set RELOAD=true

cd /d "%~dp0"

python backend/main.py

pause
