import pg from 'pg';
import dotenv from 'dotenv';
import readline from 'readline';

dotenv.config();

const { Pool } = pg;

// 从环境变量获取连接信息
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

async function insertMockData() {
  console.log('📝 Supabase 数据插入工具\n');
  console.log(`项目 URL: ${supabaseUrl}`);
  console.log(`项目引用: ${projectRef}\n`);

  // 获取连接信息
  let connectionString = process.env.DATABASE_URL;
  
  if (!connectionString) {
    const password = process.env.SUPABASE_PASSWORD || await question('请输入 Supabase 数据库密码: ');
    
    // 尝试直接连接（端口 5432）
    connectionString = `postgresql://postgres:${password}@db.${projectRef}.supabase.co:5432/postgres?sslmode=require`;
  }

  // 创建连接池
  const pool = new Pool({
    connectionString: connectionString,
    ssl: {
      rejectUnauthorized: false
    },
    max: 5,
    connectionTimeoutMillis: 10000,
  });

  try {
    // 测试连接
    console.log('\n🔗 正在连接数据库...');
    await pool.query('SELECT 1');
    console.log('✅ 数据库连接成功！\n');

    // 检查表是否存在
    const tableCheck = await pool.query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'mirror_records'
      )
    `);

    if (!tableCheck.rows[0].exists) {
      console.log('❌ 错误: mirror_records 表不存在！');
      console.log('   请先执行 init_database_supabase.sql 初始化数据库\n');
      await pool.end();
      rl.close();
      process.exit(1);
    }

    // 准备插入的数据
    const mockData = [
      {
        id: `mock_${Date.now()}_1`,
        emotion: 'happy',
        acne: 5.5,
        wrinkles: 8.2,
        pores: 12.3,
        dark_circles: 15.0,
        note: 'Good mood and skin condition'
      },
      {
        id: `mock_${Date.now()}_2`,
        emotion: 'neutral',
        acne: 25.0,
        wrinkles: 30.5,
        pores: 35.2,
        dark_circles: 40.0,
        note: 'Normal state'
      },
      {
        id: `mock_${Date.now()}_3`,
        emotion: 'sad',
        acne: 45.5,
        wrinkles: 50.2,
        pores: 55.8,
        dark_circles: 65.0,
        note: 'Work stress'
      },
      {
        id: `mock_${Date.now()}_4`,
        emotion: 'surprise',
        acne: 10.0,
        wrinkles: 15.3,
        pores: 18.5,
        dark_circles: 20.0,
        note: 'Surprise today'
      },
      {
        id: `mock_${Date.now()}_5`,
        emotion: 'angry',
        acne: 60.0,
        wrinkles: 55.5,
        pores: 50.2,
        dark_circles: 70.0,
        note: 'Emotional fluctuation'
      }
    ];

    console.log(`📊 准备插入 ${mockData.length} 条数据...\n`);

    // 插入数据
    let successCount = 0;
    let failCount = 0;

    for (const data of mockData) {
      try {
        const result = await pool.query(`
          INSERT INTO mirror_records (id, emotion, acne, wrinkles, pores, dark_circles, note)
          VALUES ($1, $2, $3, $4, $5, $6, $7)
          RETURNING id, emotion, timestamp, created_at
        `, [
          data.id,
          data.emotion,
          data.acne,
          data.wrinkles,
          data.pores,
          data.dark_circles,
          data.note
        ]);

        console.log(`✅ 插入成功: ${data.id} (${data.emotion})`);
        console.log(`   时间戳: ${result.rows[0].timestamp}`);
        successCount++;
      } catch (error) {
        console.log(`❌ 插入失败: ${data.id}`);
        console.log(`   错误: ${error.message}`);
        failCount++;
      }
    }

    // 统计结果
    console.log('\n' + '='.repeat(50));
    console.log(`📈 插入完成:`);
    console.log(`   ✅ 成功: ${successCount} 条`);
    console.log(`   ❌ 失败: ${failCount} 条`);
    console.log('='.repeat(50) + '\n');

    // 查询总记录数
    const countResult = await pool.query('SELECT COUNT(*) as total FROM mirror_records');
    console.log(`📊 数据库中共有 ${countResult.rows[0].total} 条记录\n`);

    await pool.end();
    rl.close();
    process.exit(0);
  } catch (error) {
    console.error('\n❌ 操作失败:', error.message);
    if (error.message.includes('password')) {
      console.error('   提示: 请检查数据库密码是否正确');
    } else if (error.message.includes('timeout')) {
      console.error('   提示: 连接超时，请检查网络连接');
    } else if (error.message.includes('relation') && error.message.includes('does not exist')) {
      console.error('   提示: 表不存在，请先执行 init_database_supabase.sql 初始化数据库');
    }
    await pool.end();
    rl.close();
    process.exit(1);
  }
}

// 运行脚本
insertMockData();

