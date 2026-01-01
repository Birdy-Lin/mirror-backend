import express from 'express';
import cors from 'cors';
import { getAllRecords, getTodayRecords, getRecentRecords } from './db.js';
import dotenv from 'dotenv';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 34567;
// CORS配置：支持多个来源（本地开发 + Vercel部署）
const CORS_ORIGIN = process.env.CORS_ORIGIN || 'http://localhost:8080';
const corsOrigins = CORS_ORIGIN.split(',').map(origin => origin.trim());

// 中间件
app.use(cors({
  origin: (origin, callback) => {
    // 允许无origin的请求（如Postman、curl等）
    if (!origin) return callback(null, true);
    
    // 检查是否在允许的列表中
    if (corsOrigins.includes(origin) || corsOrigins.includes('*')) {
      callback(null, true);
    } else {
      // 开发环境允许所有来源
      if (process.env.NODE_ENV !== 'production') {
        callback(null, true);
      } else {
        callback(new Error('Not allowed by CORS'));
      }
    }
  },
  credentials: true,
}));
app.use(express.json());

// 健康检查
app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    message: '心镜后端API服务运行正常',
    timestamp: new Date().toISOString(),
  });
});

// 获取所有记录
app.get('/api/records', async (req, res) => {
  try {
    const records = await getAllRecords();
    res.json({
      success: true,
      data: records,
      count: records.length,
    });
  } catch (error) {
    console.error('查询所有记录错误:', error);
    res.status(500).json({
      success: false,
      error: '查询记录失败',
      message: error.message,
    });
  }
});

// 获取今日记录
app.get('/api/records/today', async (req, res) => {
  try {
    const records = await getTodayRecords();
    res.json({
      success: true,
      data: records,
      count: records.length,
    });
  } catch (error) {
    console.error('查询今日记录错误:', error);
    res.status(500).json({
      success: false,
      error: '查询今日记录失败',
      message: error.message,
    });
  }
});

// 获取最近N条记录
app.get('/api/records/recent', async (req, res) => {
  try {
    const count = parseInt(req.query.count || '5');
    const records = await getRecentRecords(count);
    res.json({
      success: true,
      data: records,
      count: records.length,
    });
  } catch (error) {
    console.error('查询最近记录错误:', error);
    res.status(500).json({
      success: false,
      error: '查询最近记录失败',
      message: error.message,
    });
  }
});

// 启动服务器 - 监听所有网络接口（0.0.0.0）以支持外部访问
const HOST = process.env.HOST || '0.0.0.0';
app.listen(PORT, HOST, () => {
  console.log(`🚀 后端服务器启动成功`);
  console.log(`📡 监听地址: ${HOST}:${PORT}`);
  console.log(`🔗 本地访问: http://localhost:${PORT}`);
  console.log(`🌐 外部访问: http://<你的公网IP>:${PORT}`);
  console.log(`\n📋 API端点:`);
  console.log(`   - 健康检查: http://localhost:${PORT}/api/health`);
  console.log(`   - 所有记录: http://localhost:${PORT}/api/records`);
  console.log(`   - 今日记录: http://localhost:${PORT}/api/records/today`);
  console.log(`   - 最近记录: http://localhost:${PORT}/api/records/recent?count=5`);
  console.log(`\n🔒 CORS允许的来源: ${corsOrigins.join(', ')}`);
});

