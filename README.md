# AutoRegister - Qwen Register + Activate + Remote Auth Link

当前版本目标：

1. 自动注册 Qwen 账号
2. 自动完成邮箱激活
3. 交接到远程 CLI Proxy API 的登录链接认证流程

本地 OAuth、本地认证文件写入、CPA 推送、OpenClaw Gateway 相关逻辑已归档，不在当前活动链路中执行。

## 当前流程

1. 临时邮箱提供方生成邮箱（Mail.tm / 1secMail / Cloud Mail）
2. 打开 Qwen 注册页并提交注册
3. 轮询邮箱获取激活链接并打开
4. 调用远程管理 API 获取登录链接
5. 打开登录链接并轮询远程认证状态
6. 认证文件由远程 CLI Proxy API 服务维护

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 快速启动（Windows）

```powershell
.\scripts\start.ps1
```

默认会启动 Web 控制台（端口 18080）。首次建议不加 -SkipInstall。依赖已准备好后可使用：

```powershell
.\scripts\start.ps1 -SkipInstall
```

打开浏览器访问：

```text
http://127.0.0.1:18080
```

如需桌面 GUI：

```powershell
.\scripts\start.ps1 -Mode gui
```

## Docker Compose 启动

```bash
docker compose up -d --build
```

访问：

```text
http://127.0.0.1:18080
```

停止：

```bash
docker compose down
```

## 关键配置

### 远程管理 API 模式

```dotenv
QWEN_AUTH_MODE=cli-proxy-api-remote
CLI_PROXY_API_BASE_URL=http://your-server:8056
CLI_PROXY_API_KEY=your-management-key
```

### 浏览器代理（注册/激活/授权页）

Playwright 浏览器会按以下优先级读取代理：

1. QWEN_PLAYWRIGHT_PROXY
2. PLAYWRIGHT_PROXY
3. HTTPS_PROXY
4. HTTP_PROXY

示例：

```dotenv
QWEN_PLAYWRIGHT_PROXY=http://127.0.0.1:7897
QWEN_PLAYWRIGHT_PROXY_BYPASS=127.0.0.1,localhost,192.168.10.219
```

在 Docker 内如果代理在宿主机，请用 host.docker.internal：

```dotenv
HTTP_PROXY=http://host.docker.internal:7897
HTTPS_PROXY=http://host.docker.internal:7897
```

### 临时邮箱提供方（Cloud Mail 示例）

```dotenv
AUTO_REGISTER_EMAIL_PROVIDER=cloudflare
CLOUDFLARE_TEMP_EMAIL_BASE_URL=https://your-mail-host
ADMIN_EMAIL=admin@your-domain.com
ADMIN_PASSWORDS=["your-password"]
```

可选：

```dotenv
CLOUDFLARE_TEMP_EMAIL_DOMAIN=your-domain.com
```

## 归档说明

归档说明文档：

1. src/auto_register/archive/README.md
2. src/auto_register/integrations/ARCHIVED_LEGACY.md
3. src/auto_register/utils/ARCHIVED_LEGACY.md
4. src/auto_register/writer/ARCHIVED_LEGACY.md
