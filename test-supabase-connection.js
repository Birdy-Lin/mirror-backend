import pg from 'pg';
import dotenv from 'dotenv';
import readline from 'readline';

dotenv.config();

const { Pool } = pg;

// 从环境变量或命令行参数获取连接信息
const supabaseUrl = process.env.SUPABASE_URL || 'https://kcqmnnnhxmckihqtvmwd.supabase.co';
const projectRef = supabaseUrl.replace('https://', '').replace('.supabase.co', '');

// 创建命令行输入接口
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function question(query) {
  return new Promise(resolve => rl.question(query, resolve));
}

async function testConnection() {
  console.log('🔗 Supabase 连接测试工具\n');
  console.log(`项目 URL: ${supabaseUrl}`);
  console.log(`项目引用: ${projectRef}\n`);

  // 获取密码
  const password = process.env.SUPABASE_PASSWORD || await question('请输入 Supabase 数据库密码: ');
  
  // 构建连接字符串
  // 方式1: 直接连接（端口 5432）
  const directConnectionString = `postgresql://postgres:${password}@db.${projectRef}.supabase.co:5432/postgres?sslmode=require`;
  
  // 方式2: 连接池（端口 6543，推荐用于生产环境）
  const poolerConnectionString = `postgresql://postgres.${projectRef}:${password}@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require`;

  console.log('\n尝试连接方式 1: 直接连接 (端口 5432)...');
  await testConnectionString(directConnectionString, '直接连接');

  console.log('\n尝试连接方式 2: 连接池 (端口 6543)...');
  await testConnectionString(poolerConnectionString, '连接池');

  rl.close();
}

async function testConnectionString(connectionString, type) {
  const pool = new Pool({
    connectionString: connectionString,
    ssl: {
      rejectUnauthorized: false
    },
    max: 1,
    connectionTimeoutMillis: 5000,
  });

  try {
    // 测试连接
    const result = await pool.query('SELECT NOW() as current_time, current_setting(\'timezone\') as timezone');
    console.log(`✅ ${type} 连接成功！`);
    console.log(`   当前时间: ${result.rows[0].current_time}`);
    console.log(`   时区: ${result.rows[0].timezone}`);

    // 测试查询表
    try {
      const tableResult = await pool.query(`
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('mirror_records', 'emotion_mapping')
        ORDER BY table_name
      `);
      
      if (tableResult.rows.length > 0) {
        console.log(`   已存在的表: ${tableResult.rows.map(r => r.table_name).join(', ')}`);
      } else {
        console.log(`   ⚠️  表 mirror_records 和 emotion_mapping 不存在，需要先执行 init_database_supabase.sql`);
      }
    } catch (err) {
      console.log(`   ⚠️  查询表信息失败: ${err.message}`);
    }

    // 保存可用的连接字符串
    console.log(`\n📝 可用的连接字符串（添加到 .env 文件）:`);
    console.log(`DATABASE_URL=${connectionString}\n`);

    await pool.end();
    return true;
  } catch (error) {
    console.log(`❌ ${type} 连接失败: ${error.message}`);
    if (error.message.includes('password')) {
      console.log('   提示: 请检查密码是否正确');
    } else if (error.message.includes('timeout')) {
      console.log('   提示: 连接超时，请检查网络或尝试其他连接方式');
    }
    await pool.end();
    return false;
  }
}

// 运行测试
testConnection().catch(err => {
  console.error('测试失败:', err);
  rl.close();
  process.exit(1);
});

