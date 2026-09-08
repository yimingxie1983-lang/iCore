# iCore

面向医学与科研场景的本地 AI Agent 工作台。

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
python run_server.py
```

```powershell
cd web
npm install
npm run dev
```

后端默认监听 `http://localhost:8000`，前端开发服务默认监听 `http://localhost:5180`。

## 本地客户端（Codex 风格）

在任意项目目录里跑 iCore，当前目录就是工作区，不经过网页：

```powershell
pip install -e .
icore                     # 交互会话
icore "查一下这个目录"      # 带首条消息
icore exec "总结 README"    # 非交互，跑完退出
icore resume              # 恢复本目录最近一次会话
```

配置仍用仓库根目录的 `config.yaml`（或 `ONEKEY_CONFIG` / `%USERPROFILE%\.icore\config.yaml`）。

## 桌面客户端（C/S，完整 B/S 功能）

独立窗口打开同一套网页工作台（对话、项目、技能、市场、管理后台等），**不调用系统浏览器**。本地自动拉起 FastAPI。

```powershell
pip install -e ".[desktop]"
cd web; npm install; npm run build; cd ..
python -m cancer_claw.desktop
# 或：icore-gui
```

安装桌面快捷方式（iCore 图标，快捷键 Ctrl+Alt+I）：

```powershell
powershell -File ops/install_desktop_shortcut.ps1
```

打包成 `iCore.exe`：

```powershell
powershell -File ops/build_client.ps1
# 产物：ops/client/iCore/iCore.exe
```

## Docker 部署

```bash
cp ops/env.example ops/.env
nano ops/.env
bash ops/deploy.sh up
```

```bash
bash ops/deploy.sh status
bash ops/deploy.sh logs
bash ops/deploy.sh backup
bash ops/deploy.sh update
bash ops/deploy.sh down
```

## 目录结构

```text
cancer_claw/  后端服务
web/          前端应用
ops/          部署配置
config.yaml  本地配置
run_server.py 后端入口
```

具体模块均按职责分组，运行时数据与源码分离。
