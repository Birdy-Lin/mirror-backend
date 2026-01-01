import pg from 'pg';
import dotenv from 'dotenv';

dotenv.config();

const { Pool } = pg;

// 创建数据库连接池
// 支持 Supabase（使用连接字符串）和本地 PostgreSQL
const poolConfig = process.env.DATABASE_URL
  ? {
      // Supabase 或其他云服务：使用连接字符串
      connectionString: process.env.DATABASE_URL,
      ssl: process.env.DATABASE_URL.includes('supabase') 
        ? { rejectUnauthorized: false } // Supabase 需要 SSL
        : false,
    }
  : {
      // 本地 PostgreSQL：使用配置对象
      host: process.env.DB_HOST || 'localhost',
      port: parseInt(process.env.DB_PORT || '5432'),
      database: process.env.DB_NAME || 'mindmirror',
      user: process.env.DB_USER || 'postgres',
      password: process.env.DB_PASSWORD || 'postgres',
      ssl: false,
    };

export const pool = new Pool({
  ...poolConfig,
  max: 20, // 最大连接数
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
});

// 测试数据库连接
pool.on('connect', () => {
  console.log('✅ 数据库连接成功');
});

pool.on('error', (err) => {
  console.error('❌ 数据库连接错误:', err);
});

// 查询所有记录
export async function getAllRecords() {
  const query = `
    SELECT 
      id,
      image,
      timestamp,
      emotion,
      acne,
      wrinkles,
      pores,
      dark_circles,
      note
    FROM mirror_records
    ORDER BY timestamp DESC
  `;
  
  const result = await pool.query(query);
  return result.rows;
}

// 查询今日记录
export async function getTodayRecords() {
  const query = `
    SELECT 
      id,
      image,
      timestamp,
      emotion,
      acne,
      wrinkles,
      pores,
      dark_circles,
      note
    FROM mirror_records
    WHERE DATE(timestamp) = CURRENT_DATE
    ORDER BY timestamp DESC
  `;
  
  const result = await pool.query(query);
  return result.rows;
}

// 查询最近N条记录
export async function getRecentRecords(count) {
  const query = `
    SELECT 
      id,
      image,
      timestamp,
      emotion,
      acne,
      wrinkles,
      pores,
      dark_circles,
      note
    FROM mirror_records
    ORDER BY timestamp DESC
    LIMIT $1
  `;
  
  const result = await pool.query(query, [count]);
  return result.rows;
}

