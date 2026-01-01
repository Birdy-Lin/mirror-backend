# 后端API测试说明

## 1. 配置环境变量

在 `backend` 目录下创建 `.env` 文件（如果还没有）：

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mindmirror
DB_USER=postgres
DB_PASSWORD=postgres
PORT=34567
CORS_ORIGIN=http://localhost:8080
```

## 2. 启动后端服务器

```bash
cd backend
npm start
```

或者开发模式（自动重启）：

```bash
npm run dev
```

看到以下输出表示启动成功：

```
🚀 后端服务器启动成功
📡 API地址: http://localhost:34567
🔗 健康检查: http://localhost:34567/api/health
📊 所有记录: http://localhost:34567/api/records
📅 今日记录: http://localhost:34567/api/records/today
🕐 最近记录: http://localhost:34567/api/records/recent?count=5
✅ 数据库连接成功
```

## 3. 测试API端点

### 3.1 健康检查

```bash
curl http://localhost:34567/api/health
```

预期响应：
```json
{
  "status": "ok",
  "message": "心镜后端API服务运行正常",
  "timestamp": "2024-01-01T12:00:00.000Z"
}
```

### 3.2 获取所有记录

```bash
curl http://localhost:34567/api/records
```

### 3.3 获取今日记录

```bash
curl http://localhost:34567/api/records/today
```

### 3.4 获取最近5条记录

```bash
curl http://localhost:34567/api/records/recent?count=5
```

## 4. 前端连接测试

确保前端项目中的 `.env` 文件（或 `vite.config.ts`）配置了：

```
VITE_API_BASE_URL=http://localhost:34567/api
```

然后启动前端：

```bash
cd frontend/mirror-insights
npm run dev
```

访问 `http://localhost:8080`，前端应该能够正常显示数据库中的数据。

## 5. 常见问题

### 问题1: 数据库连接失败

**错误信息**: `❌ 数据库连接错误: ...`

**解决方案**:
1. 确认PostgreSQL服务正在运行
2. 检查 `.env` 文件中的数据库配置是否正确
3. 确认数据库 `mindmirror` 已创建
4. 确认表 `mirror_records` 已创建

### 问题2: CORS错误

**错误信息**: `Access to fetch at 'http://localhost:34567/api/...' from origin 'http://localhost:8080' has been blocked by CORS policy`

**解决方案**:
1. 检查 `backend/.env` 中的 `CORS_ORIGIN` 是否设置为 `http://localhost:8080`
2. 重启后端服务器

### 问题3: 端口被占用

**错误信息**: `Error: listen EADDRINUSE: address already in use :::34567`

**解决方案**:
1. 修改 `backend/.env` 中的 `PORT` 为其他端口（如 `8001`）
2. 同时修改前端的 `VITE_API_BASE_URL` 为对应端口

