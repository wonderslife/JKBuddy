// 列出 LibreChat agents 集合中的智能体列表（脱敏示例脚本）
// 运行：node scripts/list_agents.js
// 注意：连接串已脱敏为占位符，请替换为你的实际 MongoDB 配置。
const { MongoClient } = require('<path-to-node_modules>/mongodb');
(async () => {
  const c = new MongoClient(
    'mongodb://<mongo-user>:<mongo-pass>@<db-host>:<db-port>/LibreChat?authSource=admin',
  );
  await c.connect();
  const db = c.db('LibreChat');
  const agents = await db.collection('agents').find({}).project({ id: 1, name: 1, type: 1 }).toArray();
  console.log('=== Agents 列表 ===');
  for (const a of agents) console.log(a.type, a.id, a.name);
  await c.close();
})().catch((e) => {
  console.error('ERR', e.message);
  process.exit(1);
});
