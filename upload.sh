#!/bin/bash
# 快速上传脚本：一键上传到服务器

# 配置
SERVER_USER="${1:-ubuntu}"
SERVER_HOST="${2:-your-server.com}"
SERVER_PATH="${3:-/opt/auto-register}"
PORT="${4:-18080}"

# 检查参数
if [ "$SERVER_HOST" = "your-server.com" ]; then
    echo "❌ 错误: 请指定正确的服务器地址"
    echo ""
    echo "用法: ./upload.sh [用户名] [服务器地址] [服务器路径] [端口]"
    echo ""
    echo "示例:"
    echo "  ./upload.sh ubuntu 192.168.1.100 /opt/auto-register 18080"
    echo "  ./upload.sh root example.com /home/auto-register 8080"
    echo ""
    exit 1
fi

echo "🚀 AutoRegister 一键上传"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📍 目标: $SERVER_USER@$SERVER_HOST:$SERVER_PATH"
echo "🌐 端口: $PORT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. 测试连接
echo "1️⃣  测试 SSH 连接..."
if ! ssh -o ConnectTimeout=5 "$SERVER_USER@$SERVER_HOST" "echo OK" &>/dev/null; then
    echo "❌ 无法连接到服务器，请检查:"
    echo "  - 服务器地址是否正确"
    echo "  - SSH 密钥是否配置"
    echo "  - 防火墙是否允许 SSH"
    exit 1
fi
echo "✅ 连接成功"
echo ""

# 2. 创建远程目录
echo "2️⃣  创建服务器目录..."
ssh "$SERVER_USER@$SERVER_HOST" "mkdir -p $SERVER_PATH" || {
    echo "❌ 无法创建目录"
    exit 1
}
echo "✅ 目录准备完成"
echo ""

# 3. 上传文件
echo "3️⃣  上传项目文件（这可能需要 1-5 分钟）..."
echo "   正在同步文件..."
rsync -avz --delete --progress \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='node_modules' \
  --exclude='.idea' \
  --exclude='.vscode' \
  --exclude='*.log' \
  . "$SERVER_USER@$SERVER_HOST:$SERVER_PATH/" || {
    echo "❌ 上传失败"
    exit 1
}
echo "✅ 文件上传完成"
echo ""

# 4. 显示后续步骤
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 上传完成！"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 后续步骤（使用 Docker 方式 - 推荐）："
echo ""
echo "  1️⃣  连接到服务器:"
echo "     ssh $SERVER_USER@$SERVER_HOST"
echo ""
echo "  2️⃣  进入项目目录:"
echo "     cd $SERVER_PATH"
echo ""
echo "  3️⃣  配置环境变量："
echo "     nano .env"
echo "     # 编辑必要的配置"
echo ""
echo "  4️⃣  启动服务（选择一种）："
echo ""
echo "     🐳 使用 Docker Compose（推荐）："
echo "     docker-compose up -d"
echo ""
echo "     或 使用 Docker run："
echo "     docker build -t auto-register:latest ."
echo "     docker run -d --name auto-register -p $PORT:18080 \\"
echo "       -v \$(pwd)/.env:/app/.env \\"
echo "       --restart unless-stopped \\"
echo "       auto-register:latest"
echo ""
echo "  5️⃣  检查运行状态:"
echo "     docker ps"
echo "     docker logs -f auto-register"
echo ""
echo "  6️⃣  访问 Web UI:"
echo "     http://$SERVER_HOST:$PORT"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📚 更多帮助："
echo "   - 查看完整部署指南: cat DEPLOYMENT.md"
echo "   - SSH 到服务器后，查看完整说明:"
echo "     ssh $SERVER_USER@$SERVER_HOST 'cat $SERVER_PATH/DEPLOYMENT.md'"
echo ""
