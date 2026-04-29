@echo off
chcp 65001 >nul 2>&1
title TransVsverter 开发服务
echo ========================================
echo   TransVsverter - 一键启动
echo ========================================
echo.
python start_dev.py %*
pause
