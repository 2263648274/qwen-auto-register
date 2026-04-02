# 🚀 快速部署参考（3 分钟版）

## ⚡ 最快方式（使用 Docker）

### 第 1 步：上传代码

**Linux/Mac:**
```bash
bash upload.sh ubuntu 192.168.1.100 /opt/auto-register 18080
```

**Windows（需要 Git Bash）:**
```bash
# 右键项目文件夹 → Git Bash Here
bash upload.sh ubuntu 192.168.1.100 /opt/auto-register 18080
```

**或者手动上传：**
```bash
# 任何系统都支持
rsync -avz --exclude='.venv' --exclude='__pycache__' . ubuntu@192.168.1.100:/opt/auto-register/
```

### 第 2 步：配置并启动（在服务器上）

```bash
# 连接到服务器
ssh ubuntu@192.168.1.100

# 进入项目目录
cd /opt/auto-register

# 编辑 .env（很重要！）
nano .env
# 👉 配置：QWEN_API_KEY、密码等

# 启动服务
docker-compose up -d

# 检查状态
docker ps
docker logs -f auto-register
```

### 第 3 步：访问

```
http://192.168.1.100:18080
```

---

## 📋 关键配置项（.env）

```ini
# Qwen API 配置（必需）
QWEN_API_KEY=your-api-key-here
QWEN_ACCOUNT_PASSWORD=your-password

# 代理配置（如果需要）
CLI_PROXY_API_KEY=your-proxy-key
CLI_PROXY_PASSWORD=your-proxy-password
CLI_PROXY_BASE_URL=http://proxy-server/management

# 可选
AUTO_REGISTER_EMAIL_PROVIDER=cloudflare
```

---

## 🔧 常用命令速查

| 操作 | 命令 |
|-----|------|
| 查看容器 | `docker ps` |
| 查看日志 | `docker logs -f auto-register` |
| 重启服务 | `docker-compose restart` |
| 停止服务 | `docker-compose down` |
| 更新代码 | `git pull && docker-compose up -d --build` |
| 进入容器 | `docker exec -it auto-register bash` |
| 查看端口占用 | `lsof -i :18080` 或 `netstat -tlnp` |

---

## ✅ 验证检查清单

- [ ] SSH 可以连接到服务器
- [ ] 文件已上传到 `/opt/auto-register`
- [ ] `.env` 文件已配置
- [ ] Docker 已安装：`docker --version`
- [ ] Docker Compose 已安装：`docker-compose --version`
- [ ] Docker 守护进程已运行：`docker ps`
- [ ] 端口 18080 未被占用
- [ ] Web UI 可访问：`curl http://localhost:18080/healthz`

---

## 🆘 常见问题速解

**"Docker not found"**
```bash
# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

**"Cannot connect to Docker daemon"**
```bash
sudo systemctl start docker
sudo systemctl enable docker
```

**"Permission denied"**
```bash
sudo usermod -aG docker $USER
# 退出后重新登录
exit
```

**"Port 18080 already in use"**
```bash
# 杀死占用进程
sudo lsof -i :18080
sudo kill -9 <PID>

# 或改用其他端口
# 编辑 docker-compose.yml：ports: ["8080:18080"]
```

**".env not found"**
```bash
# 从示例创建
cp .env.example .env
# 或手动创建并配置
nano .env
```

---

## 📚 完整文档

查看详细部署指南：
```bash
cat DEPLOYMENT.md
```

或在本地：
```bash
# 项目目录中
less DEPLOYMENT.md
```

---

## 🎯 部署后的建议

1. **设置备份**
   ```bash
   # 定期备份 auth_files 和日志
   crontab -e
   # 添加: 0 2 * * * tar -czf /backup/auto-register-$(date +\%Y\%m\%d).tar.gz /opt/auto-register
   ```

2. **配置 Nginx 反向代理**（可选）
   ```bash
   sudo apt install nginx
   sudo nano /etc/nginx/sites-available/auto-register
   # 参考 DEPLOYMENT.md 中的 Nginx 配置示例
   ```

3. **监控执行日志**
   ```bash
   docker logs -f auto-register --tail 100
   ```

4. **定期更新代码**
   ```bash
   git pull
   docker-compose up -d --build
   ```

---

**🎉 部署完成！快去 http://你的服务器:18080 测试一下吧！**
