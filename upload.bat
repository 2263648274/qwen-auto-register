@echo off
REM Windows 快速上传脚本

setlocal enabledelayedexpansion

if "%1"=="" (
    echo ❌ 错误: 缺少服务器地址
    echo.
    echo 用法: upload.bat [用户名@服务器地址] [远程路径] [端口]
    echo.
    echo 示例:
    echo   upload.bat ubuntu@192.168.1.100 /opt/auto-register 18080
    echo   upload.bat root@example.com /home/auto-register 8080
    echo.
    pause
    exit /b 1
)

set SERVER=%1
set REMOTE_PATH=%2
set PORT=%3

if "!REMOTE_PATH!"=="" set REMOTE_PATH=/opt/auto-register
if "!PORT!"=="" set PORT=18080

echo 🚀 AutoRegister 一键上传
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 📍 目标: !SERVER!:!REMOTE_PATH!
echo 🌐 端口: !PORT!
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM 检查 rsync（Windows 上需要 Git Bash 或其他工具）
where rsync >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到 rsync，请安装 Git for Windows 或 WSL
    echo.
    echo 推荐方案:
    echo   1. 安装 Git for Windows (https://git-scm.com/download/win)
    echo      - 安装时选择 "Use Git from Git Bash only"
    echo      - 然后使用 Git Bash 运行此脚本
    echo.
    echo   2. 或使用 scp (OpenSSH in Windows 10+)：
    echo      scp -r . !SERVER!:!REMOTE_PATH!/
    echo.
    pause
    exit /b 1
)

echo 1️⃣  上传项目文件...
echo 正在同步文件，这可能需要 1-5 分钟...
echo.

rsync -avz --delete --progress ^
  --exclude=.git ^
  --exclude=.venv ^
  --exclude=__pycache__ ^
  --exclude=.pytest_cache ^
  --exclude=*.pyc ^
  --exclude=.DS_Store ^
  --exclude=node_modules ^
  --exclude=.idea ^
  --exclude=.vscode ^
  --exclude=*.log ^
  . !SERVER!:!REMOTE_PATH!/

if errorlevel 1 (
    echo.
    echo ❌ 上传失败
    pause
    exit /b 1
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ✅ 上传完成！
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 📝 后续步骤：
echo.
echo   1️⃣  连接到服务器:
echo      ssh !SERVER!
echo.
echo   2️⃣  进入項目目录:
echo      cd !REMOTE_PATH!
echo.
echo   3️⃣  配置环境变量:
echo      nano .env
echo.
echo   4️⃣  启动服务:
echo      docker-compose up -d
echo.
echo   5️⃣  查看状态:
echo      docker ps
echo      docker logs -f auto-register
echo.
echo   6️⃣  访问 Web UI:
echo      http://!SERVER:*=!:!PORT!
echo.
echo 有关更多帮助，请查看 DEPLOYMENT.md
echo.
pause
