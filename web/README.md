# iCore 前端

## 启动

```bash
# 先启动后端（仓库根目录）
python -m cancer_claw.app

# 再启动前端
cd web
npm install
npm run dev                     # http://localhost:5180
```

## 目录结构

```
web/
├── public/
├── src/
│   ├── api/                  # axios / SSE
│   ├── components/
│   │   ├── Layout/
│   │   ├── common/
│   │   └── ui/               # shadcn/ui
│   ├── lib/
│   ├── pages/
│   ├── store/
│   ├── utils/
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── index.html
├── package.json
├── vite.config.ts
└── tailwind.config.ts
```
