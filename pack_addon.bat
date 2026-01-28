@echo off
chcp 65001 >nul
title Blender 插件打包工具

cd /d "%~dp0"
python pack_addon.py

if errorlevel 1 (
    echo.
    echo 打包失败，请检查错误信息
    pause
)
