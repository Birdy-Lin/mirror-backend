import pg from 'pg';
import dotenv from 'dotenv';

dotenv.config();

const { Pool } = pg;

// Supabase 项目信息
const SUPABASE_URL = 'https://kcqmnnnhxmckihqtvmwd.supabase.co';
const PROJECT_REF = 'kcqmnnnhxmckihqtvmwd';

console.log('🔗 测试 Supabase 连接\n');
console.log(`项目 URL: ${SUPABASE_URL}`);
console.log(`项目引用: ${PROJECT_REF}\n`);

// 检查环境变量
if (!process.env.SUPABASE_PASSWORD && !process.env.DATABASE_URL) {
  console.log('❌ 未找到连接信息！');
  console.log('\n📝 请按以下步骤操作：');
  console.log('1. 访问 Supabase Dashboard: https://supabase.com/dashboard');
  console.log('2. 选择项目，进入 Settings → Database');
  console.log('3. 找到 "Connection string" 部分');
  console.log('4. 复制 "URI" 格式的连接字符串');
  console.log('5. 在 backend/.env 文件中添加：');
  console.log('   DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.kcqmnnnhxmckihqtvmwd.supabase.co:5432/postgres');
  console.log('\n或者运行: node test-supabase-connection.js');
  process.exit(1);
}

// 构建连接字符串
let connectionString;
if (process.env.DATABASE_URL) {
  connectionString = process.env.DATABASE_URL;
  console.log('✅ 使用环境变量 DATABASE_URL');
} else {
  const password = process.env.SUPABASE_PASSWORD;
  connectionString = `postgresql://postgres:${password}@db.${PROJECT_REF}.supabase.co:5432/postgres?sslmode=require`;
  console.log('✅ 使用环境变量 SUPABASE_PASSWORD');
}

console.log(`\n尝试连接...`);

const pool = new Pool({
  connectionString: connectionString,
  ssl: {
    rejectUnauthorized: false
  },
  max: 1,
  connectionTimeoutMillis: 10000,
});

// 测试连接
pool.query('SELECT NOW() as current_time, current_setting(\'timezone\') as timezone, version() as pg_version')
  .then(result => {
    console.log('\n✅ 连接成功！');
    console.log(`   当前时间: ${result.rows[0].current_time}`);
    console.log(`   时区: ${result.rows[0].timezone}`);
    console.log(`   PostgreSQL 版本: ${result.rows[0].pg_version.split(',')[0]}`);
    
    // 检查表是否存在
    return pool.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_name IN ('mirror_records', 'emotion_mapping')
      ORDER BY table_name
    `);
  })
  .then(result => {
    if (result.rows.length > 0) {
      console.log(`\n📊 已存在的表:`);
      result.rows.forEach(row => {
        console.log(`   - ${row.table_name}`);
      });
    } else {
      console.log(`\n⚠️  表 mirror_records 和 emotion_mapping 不存在`);
      console.log(`   请在 Supabase SQL Editor 中执行 init_database_supabase.sql`);
    }
    
    return pool.end();
  })
  .then(() => {
    console.log('\n✅ 测试完成！');
    process.exit(0);
  })
  .catch(error => {
    console.error('\n❌ 连接失败:', error.message);
    if (error.message.includes('password')) {
      console.log('\n💡 提示: 密码错误，请检查 SUPABASE_PASSWORD 或 DATABASE_URL');
    } else if (error.message.includes('timeout')) {
      console.log('\n💡 提示: 连接超时，请检查网络连接');
    } else {
      console.log('\n💡 提示: 请检查连接字符串是否正确');
    }
    process.exit(1);
  });

