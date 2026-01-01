# 使用IP地址部署后端配置说明

## 前置要求

1. **公网IP地址**：你的服务器需要有公网IP（不是内网IP）
2. **防火墙配置**：需要开放后端端口（默认8000）
3. **路由器端口转发**（如果服务器在内网）：需要在路由器上配置端口转发

## 步骤 1: 获取公网IP地址

### Windows
```powershell
# 方法1: 使用PowerShell
(Invoke-WebRequest -Uri "https://api.ipify.org").Content

# 方法2: 使用curl
curl https://api.ipify.org

# 方法3: 访问网站
# https://www.whatismyip.com/
```

### Linux/Mac
```bash
curl https://api.ipify.org
# 或
curl ifconfig.me
```

## 步骤 2: 配置后端服务器

### 2.1 更新 `.env` 文件

在 `backend` 目录下的 `.env` 文件中添加：

```env
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mindmirror
DB_USER=postgres
DB_PASSWORD=postgres

# 服务器配置
PORT=8000
HOST=0.0.0.0  # 监听所有网络接口

# CORS配置 - 添加你的Vercel域名
# 多个域名用逗号分隔
CORS_ORIGIN=http://localhost:8080,https://your-app.vercel.app,https://your-app-git-main.vercel.app
```

**重要**：将 `your-app.vercel.app` 替换为你的实际Vercel域名。

### 2.2 启动后端服务器

```bash
cd backend
npm start
```

你应该看到：
```
🚀 后端服务器启动成功
📡 监听地址: 0.0.0.0:8000
🌐 外部访问: http://<你的公网IP>:8000
```

## 步骤 3: 配置防火墙

### Windows (防火墙)

1. 打开 **Windows Defender 防火墙**
2. 点击 **高级设置**
3. 选择 **入站规则** → **新建规则**
4. 选择 **端口** → **TCP** → **特定本地端口** → 输入 `8000`
5. 选择 **允许连接**
6. 应用到所有配置文件
7. 命名为 "心镜后端API"

### Linux (iptables/ufw)

```bash
# Ubuntu/Debian (使用ufw)
sudo ufw allow 8000/tcp
sudo ufw reload

# CentOS/RHEL (使用firewalld)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### Mac

```bash
# 使用pfctl配置，或通过系统偏好设置 → 安全性与隐私 → 防火墙
```

## 步骤 4: 配置路由器端口转发（如果需要）

如果你的服务器在内网（通过路由器连接），需要配置端口转发：

1. 登录路由器管理界面（通常是 `192.168.1.1` 或 `192.168.0.1`）
2. 找到 **端口转发** 或 **虚拟服务器** 设置
3. 添加规则：
   - **外部端口**: 8000
   - **内部IP**: 你的服务器内网IP（如 `192.168.1.100`）
   - **内部端口**: 8000
   - **协议**: TCP

## 步骤 5: 测试后端是否可访问

在浏览器或使用curl测试：

```bash
# 替换为你的公网IP
curl http://<你的公网IP>:8000/api/health
```

应该返回：
```json
{
  "status": "ok",
  "message": "心镜后端API服务运行正常",
  "timestamp": "..."
}
```

## 步骤 6: 在Vercel上配置环境变量

1. 登录 Vercel Dashboard
2. 选择你的项目 → **Settings** → **Environment Variables**
3. 添加环境变量：
   - **Key**: `VITE_API_BASE_URL`
   - **Value**: `http://<你的公网IP>:8000/api`
   - **Environment**: 选择所有环境

**示例**：
```
VITE_API_BASE_URL=http://123.45.67.89:8000/api
```

4. 保存并重新部署

## 步骤 7: 处理HTTPS混合内容问题

⚠️ **重要**：如果Vercel使用HTTPS，而你的后端使用HTTP，浏览器会阻止请求（混合内容策略）。

### 解决方案A: 使用HTTPS（推荐）

使用Nginx反向代理 + Let's Encrypt免费SSL证书：

```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 解决方案B: 使用Cloudflare Tunnel（免费）

1. 安装 Cloudflare Tunnel
2. 创建隧道并配置
3. 获得HTTPS URL

### 解决方案C: 临时方案（仅开发测试）

在浏览器中允许不安全内容（不推荐用于生产环境）。

## 常见问题

### Q1: 无法从外部访问

**检查清单**：
- [ ] 服务器监听 `0.0.0.0` 而不是 `localhost`
- [ ] 防火墙已开放8000端口
- [ ] 路由器已配置端口转发（如果在内网）
- [ ] 公网IP地址正确

### Q2: CORS错误

确保 `.env` 文件中的 `CORS_ORIGIN` 包含你的Vercel域名：
```
CORS_ORIGIN=http://localhost:8080,https://your-app.vercel.app
```

### Q3: 连接超时

- 检查防火墙设置
- 检查路由器端口转发
- 确认服务器正在运行
- 使用 `netstat -an | grep 8000` 检查端口是否监听

### Q4: 动态IP地址

如果你的IP地址会变化，考虑：
- 使用动态DNS服务（如DuckDNS、No-IP）
- 使用内网穿透工具（如frp、ngrok）
- 定期更新Vercel环境变量

## 安全建议

1. **使用HTTPS**：生产环境强烈建议使用HTTPS
2. **限制访问**：考虑添加API密钥认证
3. **定期更新**：保持系统和依赖包更新
4. **监控日志**：定期检查服务器日志

