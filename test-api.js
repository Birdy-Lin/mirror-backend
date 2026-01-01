// 简单的API测试脚本
import fetch from 'node-fetch';

const API_BASE = 'http://localhost:34567/api';

async function testAPI() {
  console.log('🧪 开始测试API...\n');

  // 测试健康检查
  try {
    console.log('1️⃣ 测试健康检查...');
    const healthRes = await fetch(`${API_BASE}/health`);
    const healthData = await healthRes.json();
    console.log('✅ 健康检查:', healthData);
  } catch (error) {
    console.error('❌ 健康检查失败:', error.message);
  }

  // 测试获取所有记录
  try {
    console.log('\n2️⃣ 测试获取所有记录...');
    const recordsRes = await fetch(`${API_BASE}/records`);
    const recordsData = await recordsRes.json();
    console.log(`✅ 获取到 ${recordsData.count} 条记录`);
    if (recordsData.data.length > 0) {
      console.log('   第一条记录:', {
        id: recordsData.data[0].id,
        emotion: recordsData.data[0].emotion,
        timestamp: recordsData.data[0].timestamp,
      });
    }
  } catch (error) {
    console.error('❌ 获取记录失败:', error.message);
  }

  // 测试获取今日记录
  try {
    console.log('\n3️⃣ 测试获取今日记录...');
    const todayRes = await fetch(`${API_BASE}/records/today`);
    const todayData = await todayRes.json();
    console.log(`✅ 今日有 ${todayData.count} 条记录`);
  } catch (error) {
    console.error('❌ 获取今日记录失败:', error.message);
  }

  // 测试获取最近5条记录
  try {
    console.log('\n4️⃣ 测试获取最近5条记录...');
    const recentRes = await fetch(`${API_BASE}/records/recent?count=5`);
    const recentData = await recentRes.json();
    console.log(`✅ 获取到 ${recentData.count} 条最近记录`);
  } catch (error) {
    console.error('❌ 获取最近记录失败:', error.message);
  }

  console.log('\n✨ 测试完成！');
}

testAPI();

