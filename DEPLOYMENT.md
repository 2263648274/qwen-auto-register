# 🚀 AutoRegister 部署指南

## 📋 前置条件

### 本地发送到服务器
- rsync 或 scp（用于上传文件）
- SSH 访问权限

### 服务器端要求
- Python 3.10+ 或 Docker
- Linux 系统（推荐 Ubuntu 20.04+）
- 至少 2GB 可用内存
- 至少 5GB 磁盘空间

---

## 方案 A: 使用 Docker 部署（⭐ 推荐）

### 1️⃣ 上传项目到服务器

```bash
# 从本地上传整个项目
rsync -avz --exclude='.venv' --exclude='__pycache__' \
  . username@your-server.com:/opt/auto-register/

# 或使用 SCP（分块上传）
scp -r . username@your-server.com:/opt/auto-register/
```

### 2️⃣ 在服务器上启动

```bash
# SSH 连接到服务器
ssh username@your-server.com

# 进入项目目录
cd /opt/auto-register

# 构建 Docker 镜像
docker build -t auto-register:latest .

# 方式 A: 使用 docker-compose（推荐）
docker-compose up -d

# OR 方式 B: 直接使用 docker run
docker run -d \
  --name auto-register \
  -p 18080:18080 \
  -v $(pwd)/.env:/app/.env \
  --restart unless-stopped \
  auto-register:latest
```

### 3️⃣ 验证服务运行

```bash
# 查看容器状态
docker ps | grep auto-register

# 查看最近的日志
docker logs -f auto-register

# 测试健康检查
curl http://localhost:18080/healthz
```

### 4️⃣ 配置环境变量

在服务器上编辑 `.env` 文件：

```bash
nano /opt/auto-register/.env
```

需要配置的关键变量：
```
QWEN_API_KEY=your-qwen-api-key
QWEN_ACCOUNT_PASSWORD=your-account-password
QWEN_ACCOUNT_EMAIL_PATTERN=your-pattern
CLI_PROXY_API_KEY=your-proxy-api-key
CLI_PROXY_PASSWORD=your-proxy-password
CLI_PROXY_BASE_URL=http://your-proxy-server/management
```

### 5️⃣ 服务管理

```bash
# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 更新代码后重启
docker-compose up -d --build

# 查看所有日志
docker logs auto-register

# 进入容器调试
docker exec -it auto-register bash
```

---

## 方案 B: 直接部署（不使用 Docker）

### 1️⃣ 上传项目

```bash
# 从本地上传
rsync -avz --exclude='.venv' --exclude='__pycache__' \
  . username@your-server.com:/opt/auto-register/
```

### 2️⃣ 在服务器上配置

```bash
ssh username@your-server.com

cd /opt/auto-register

# 创建虚拟环境
python3.12 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

# 安装 Playwright 浏览器
playwright install chromium
```

### 3️⃣ 配置环境变量

```bash
# 编辑 .env 文件
nano .env

# 或创建新的 .env
cat > .env << 'EOF'
QWEN_API_KEY=your-key-here
QWEN_ACCOUNT_PASSWORD=your-password
# ... 其他配置
EOF
```

### 4️⃣ 创建 systemd 服务（Linux）

```bash
# 创建服务文件
sudo tee /etc/systemd/system/auto-register.service > /dev/null << 'EOF'
[Unit]
Description=AutoRegister Web Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/auto-register
Environment="PATH=/opt/auto-register/.venv/bin"
ExecStart=/opt/auto-register/.venv/bin/python -m auto_register --mode web --host 0.0.0.0 --port 18080
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 重载 systemd
sudo systemctl daemon-reload

# 启用服务（开机自动启动）
sudo systemctl enable auto-register

# 启动服务
sudo systemctl start auto-register

# 查看状态
sudo systemctl status auto-register

# 查看日志
sudo journalctl -u auto-register -f
```

---

## 常见问题

### Q: 如何更新代码？

**Docker 方案：**
```bash
# 本地更新代码后上传
rsync -avz --exclude='.venv' . username@server:/opt/auto-register/

# 在服务器上重建并重启
ssh username@server
cd /opt/auto-register
docker-compose up -d --build
```

**直接部署方案：**
```bash
# 本地更新并上传
rsync -avz --exclude='.venv' . username@server:/opt/auto-register/

# 在服务器上重启
ssh username@server
sudo systemctl restart auto-register
```

### Q: 如何调试问题？

```bash
# Docker
docker logs -f auto-register

# 直接部署
sudo journalctl -u auto-register -f

# 或进入虚拟环境直接运行
cd /opt/auto-register
source .venv/bin/activate
python -m auto_register --mode web --host 127.0.0.1 --port 18080
```

### Q: 如何修改端口？

**Docker 方案：**
编辑 `docker-compose.yml`：
```yaml
ports:
  - "8080:18080"  # 改成 8080
```
然后运行 `docker-compose up -d --build`

**直接部署：**
```bash
sudo systemctl edit auto-register
# 修改 ExecStart 中的 --port 参数
```

### Q: 能否通过 Nginx 反向代理？

```nginx
# /etc/nginx/sites-available/auto-register
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:18080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用：
```bash
sudo ln -s /etc/nginx/sites-available/auto-register /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 监控和维护

```bash
# 查看容器资源占用（Docker）
docker stats auto-register

# 查看服务运行时间
sudo systemctl status auto-register

# 自动清理历史日志
docker exec auto-register sh -c 'rm -f /app/logs/*.log.* 2>/dev/null || true'
```

---

## 🆘 快速故障排查

| 问题 | 解决方案 |
|------|--------|
| 端口被占用 | `lsof -i :18080` 查看，`kill -9 PID` 杀掉占用进程 |
| 认证失败 | 检查 `.env` 中的 `QWEN_API_KEY` 和密码是否正确 |
| 浏览器超时 | 检查防火墙是否开放 18080 端口，`sudo ufw allow 18080` |
| 内存不足 | 增加服务器内存或优化 Playwright 配置 |
| 日志文件过大 | 定期清理 `logs/` 目录或配置日志轮转 |

