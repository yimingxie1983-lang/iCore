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
