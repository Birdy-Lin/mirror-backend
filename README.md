# 心镜后端API服务

## 快速开始

### 1. 安装依赖

```bash
npm install
```

### 2. 配置环境变量

编辑 `.env` 文件，配置数据库连接信息：

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mindmirror
DB_USER=postgres
DB_PASSWORD=postgres
PORT=8000
CORS_ORIGIN=http://localhost:8080
```

### 3. 启动服务

```bash
# 开发模式（自动重启）
npm run dev

# 生产模式
npm start
```

## API端点

- `GET /api/health` - 健康检查
- `GET /api/records` - 获取所有记录
- `GET /api/records/today` - 获取今日记录
- `GET /api/records/recent?count=5` - 获取最近N条记录

## 响应格式

```json
{
  "success": true,
  "data": [...],
  "count": 10
}
```

