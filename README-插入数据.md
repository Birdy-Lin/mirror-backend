# Supabase 数据插入脚本使用说明

## 📝 脚本说明

`insert-supabase-data.js` 是一个用于向 Supabase 数据库插入测试数据的脚本。

## 🚀 使用方法

### 方法 1: 使用环境变量（推荐）

1. **在 `backend` 目录下创建 `.env` 文件**（如果还没有）：

```env
# Supabase 连接字符串（完整连接字符串）
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.kcqmnnnhxmckihqtvmwd.supabase.co:5432/postgres?sslmode=require

# 或者分别设置
SUPABASE_URL=https://kcqmnnnhxmckihqtvmwd.supabase.co
SUPABASE_PASSWORD=YOUR_PASSWORD
```

2. **运行脚本**：

```bash
cd backend
node insert-supabase-data.js
```

### 方法 2: 交互式输入

如果未设置环境变量，脚本会提示你输入密码：

```bash
cd backend
node insert-supabase-data.js
# 然后按提示输入 Supabase 数据库密码
```

## 📊 插入的数据

脚本会插入 5 条测试数据，包括：

- **happy** - 良好皮肤状态
- **neutral** - 正常皮肤状态
- **sad** - 较差皮肤状态
- **surprise** - 良好皮肤状态
- **angry** - 较差皮肤状态

每条数据包含：
- 情绪类型（emotion）
- 皮肤指标（acne, wrinkles, pores, dark_circles）
- 备注（note）
- 自动生成的时间戳（timestamp）

## ⚠️ 注意事项

1. **确保数据库已初始化**：在插入数据前，请先执行 `init_database_supabase.sql` 初始化数据库表结构。

2. **获取 Supabase 连接信息**：
   - 登录 Supabase Dashboard
   - 进入 Project Settings > Database
   - 复制 Connection string，替换 `[YOUR_PASSWORD]` 为你的数据库密码

3. **连接字符串格式**：
   ```
   postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres?sslmode=require
   ```

## 🔍 验证数据

插入成功后，你可以：

1. **在 Supabase Dashboard 中查看**：
   - 进入 Table Editor
   - 查看 `mirror_records` 表

2. **通过后端 API 查询**：
   ```bash
   curl http://localhost:8000/api/records
   ```

## 📝 示例输出

```
📝 Supabase 数据插入工具

项目 URL: https://kcqmnnnhxmckihqtvmwd.supabase.co
项目引用: kcqmnnnhxmckihqtvmwd

🔗 正在连接数据库...
✅ 数据库连接成功！

📊 准备插入 5 条数据...

✅ 插入成功: mock_1735123456789_1 (happy)
   时间戳: 2024-12-25 10:30:45.123+08
✅ 插入成功: mock_1735123456789_2 (neutral)
   时间戳: 2024-12-25 10:30:45.124+08
...

==================================================
📈 插入完成:
   ✅ 成功: 5 条
   ❌ 失败: 0 条
==================================================

📊 数据库中共有 5 条记录
```

