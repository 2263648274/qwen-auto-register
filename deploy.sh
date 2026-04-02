#!/bin/bash
# 部署脚本：上传并启动 AutoRegister

set -e

# 配置变量
SERVER_USER="${1:-root}"
SERVER_HOST="${2:-your-server.com}"
SERVER_PATH="${3:-/opt/auto-register}"
PYTHON_VERSION="3.12"

echo "📦 开始部署 AutoRegister..."
echo "目标服务器: $SERVER_USER@$SERVER_HOST:$SERVER_PATH"
echo ""

# 1. 创建服务器文件夹
echo "1️⃣  创建服务器文件夹..."
ssh "$SERVER_USER@$SERVER_HOST" "mkdir -p $SERVER_PATH"

# 2. 排除不需要的文件和文件夹
echo "2️⃣  上传项目文件..."
rsync -avz --delete \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='node_modules' \
  --exclude='.idea' \
  --exclude='.vscode' \
  . "$SERVER_USER@$SERVER_HOST:$SERVER_PATH/"

# 3. 在服务器上创建虚拟环境
echo "3️⃣  设置 Python 虚拟环境..."
ssh "$SERVER_USER@$SERVER_HOST" "cd $SERVER_PATH && python3.$PYTHON_VERSION -m venv .venv"

# 4. 安装依赖
echo "4️⃣  安装依赖..."
ssh "$SERVER_USER@$SERVER_HOST" "cd $SERVER_PATH && .venv/bin/pip install --upgrade pip setuptools wheel"
ssh "$SERVER_USER@$SERVER_HOST" "cd $SERVER_PATH && .venv/bin/pip install -e ."

# 5. 安装 Playwright 浏览器
echo "5️⃣  安装 Playwright 浏览器..."
ssh "$SERVER_USER@$SERVER_HOST" "cd $SERVER_PATH && .venv/bin/playwright install chromium"

# 6. 创建 systemd 服务
echo "6️⃣  创建 systemd 服务..."
ssh "$SERVER_USER@$SERVER_HOST" "cat > /tmp/auto-register.service << 'EOF'
[Unit]
Description=AutoRegister Web Service
After=network.target

[Service]
Type=simple
User=$SERVER_USER
WorkingDirectory=$SERVER_PATH
Environment=\"PATH=$SERVER_PATH/.venv/bin\"
ExecStart=$SERVER_PATH/.venv/bin/python -m auto_register --mode web --host 0.0.0.0 --port 18080
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
"

ssh "$SERVER_USER@$SERVER_HOST" "sudo mv /tmp/auto-register.service /etc/systemd/system/"
ssh "$SERVER_USER@$SERVER_HOST" "sudo systemctl daemon-reload"
ssh "$SERVER_USER@$SERVER_HOST" "sudo systemctl enable auto-register"

echo ""
echo "✅ 部署完成！"
echo ""
echo "📋 后续操作："
echo "  1. 更新 .env 文件："
echo "     ssh $SERVER_USER@$SERVER_HOST 'nano $SERVER_PATH/.env'"
echo ""
echo "  2. 启动服务："
echo "     ssh $SERVER_USER@$SERVER_HOST 'sudo systemctl start auto-register'"
echo ""
echo "  3. 查看日志："
echo "     ssh $SERVER_USER@$SERVER_HOST 'sudo journalctl -u auto-register -f'"
echo ""
echo "  4. 访问 Web UI："
echo "     http://$SERVER_HOST:18080"
echo ""
