# AutoRegister - Qwen Token 自动获取

自动完成 Qwen 注册、邮箱激活、登录，提取 OAuth Token 并写入 auth-profiles.json，无需 `openclaw onboard`。

## 流程

1. 临时邮箱 API 生成邮箱（默认 Mail.tm，可切换 1secMail）
2. 打开 chat.qwen.ai 注册页
3. 填写注册表单（邮箱 + 随机密码）
4. 提交注册
5. 轮询收件箱获取激活链接
6. 打开激活链接完成验证
7. 填写登录表单
8. 提交登录
9. 通过 OAuth 设备码流程获取 API token（无头模式自动点击「同意」，有界面时需手动确认）
10. 写入 auth-profiles.json

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 网络要求

**中国大陆用户需要配置代理：**

### 方式一：环境变量（推荐）

```bash
# Windows PowerShell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"

# Linux/Mac
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
```

### 方式二：.env 文件

在项目目录下创建 `.env` 文件：

```
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

### 方式三：永久设置（系统环境变量）

1. 搜索"环境变量"
2. 用户变量 → 新建
3. `HTTP_PROXY = http://127.0.0.1:你的代理端口`
4. `HTTPS_PROXY = http://127.0.0.1:你的代理端口`
5. 重启终端

## 使用

### 安装为可执行模块（推荐）

```bash
pip install -e .
# 然后可从任意目录运行：
python -m auto_register
```

### GUI 模式（默认）

```bash
# 在项目目录下，设置 PYTHONPATH：
# Windows:
set PYTHONPATH=src
python -m auto_register

# 或使用 run 脚本：
python scripts/run.py
```

### CLI 模式

```bash
python -m auto_register --no-gui
python -m auto_register --no-gui --headless
python -m auto_register --auth-path /path/to/auth-profiles.json
```

## 配置

- **auth-profiles 路径**：默认 `~/.openclaw/agents/main/agent/auth-profiles.json`
- 环境变量 `OPENCLAW_AUTH_PROFILES_PATH` 可覆盖
- **临时邮箱**：默认 Mail.tm（无 403）；设置 `AUTO_REGISTER_EMAIL_PROVIDER=1secmail` 使用 1secMail
- **Gateway 自动重启**：写入 token 后自动执行 `openclaw gateway restart`。若 `openclaw` 未加入 PATH：
  - 复制 `.env.example` 为 `.env`，填入 `OPENCLAW_NODE_PATH` 和 `OPENCLAW_PATH`
  - 或设置系统环境变量（需**重启终端/IDE**后生效）

## 故障排查（OpenClaw 401）

若 token 格式正确但 OpenClaw 仍返回 401：

1. **验证 token 是否有效**
   ```bash
   python scripts/test_qwen_token.py
   ```
   - 若显示「Token 有效」→ 问题在 OpenClaw 侧，见下方
   - 若显示「Token 无效」→ chat 的 token 可能与 portal 不通用，尝试官方 OAuth：  
     `openclaw models auth login --provider qwen-portal --set-default`

2. **检查 Gateway**
   ```bash
   openclaw gateway status
   openclaw gateway restart
   ```

3. **确认插件已启用**
   ```bash
   openclaw plugins enable qwen-portal-auth
   ```
   重启 Gateway 后生效。

4. **确认 auth-profiles 路径**
   - 默认：`~/.openclaw/agents/main/agent/auth-profiles.json`
   - 若 OpenClaw 使用其他路径，设置 `OPENCLAW_AUTH_PROFILES_PATH` 与之一致。

5. **查看 Gateway 日志**
   ```powershell
   Get-Content $env:TEMP\openclaw\openclaw-*.log -Tail 50
   ```

## 打包（PyInstaller）

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "0"
playwright install chromium
pyinstaller --noconfirm --windowed --onefile ^
  --name auto_register ^
  src/auto_register/gui/app.py
```
