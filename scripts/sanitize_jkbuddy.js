// 统一脱敏脚本：将 JKBuddy 发布目录中的真实企业名/IP/用户名替换为抽象名
// 用法：在 JKBuddy 仓库根目录运行  node scripts/sanitize_jkbuddy.js
// 注意：请在"未脱敏的原始副本"上运行本脚本，且只运行一次（避免重复前缀）。
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const SELF = path.basename(__filename); // 自身文件名，跳过处理

// 替换映射表：真实名称 -> 抽象名
// ⚠️ 安全说明：为保证公开仓库安全，此处原始映射中的真实企业名、用户名与内网 IP 已全部移除。
// 请将下方 <占位符> 替换为你自己的真实敏感值后，仅在"未脱敏的原始副本"上运行本脚本。
const MAP = [
  ['<real-holding-group>', '金控集团'],
  ['<real-angel-fund>', '某天使投资基金'],
  ['<real-capital-platform>', '某投资平台'],
  ['<real-holding-company>', '某控股公司'],
  ['<real-agri-company>', '某农投公司'],
  ['<real-tech-company>', '某科技有限公司'],
  ['<real-pe-fund>', '某股权投资基金合伙企业'],
  ['<real-venture-capital>', '某科技风投'],
  ['<real-invest-mgmt>', '某投资管理公司'],
  ['<real-venture-group>', '某创投集团'],
  ['<real-city-fund>', '某市投资基金'],
  ['<real-legacy-fund>', '某原引导基金'],
  ['<real-agri-dev>', '某农投发展公司'],
  ['<your_db_name>', 'your_db_name'],
  ['<local-project-home>', ''],
  ['<internal-ip>', '<internal-ip>'],
  ['<server-host>', '<server-host>'],
  ['<local-model-host>', '<local-model-host>'],
  ['<db-host>', '<db-host>'],
  ['<server-home>', '<server-home>'],
  ['<server-user>', '<user>'],
];

const SUFFIX = ['.md', '.yaml', '.yml', '.txt', '.py', '.js', '.toml', '.json'];

function walk(dir, cb) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (['.git', 'node_modules', '.venv', '__pycache__'].includes(e.name)) continue;
      walk(p, cb);
    } else if (e.isFile() && e.name !== SELF && SUFFIX.includes(path.extname(e.name).toLowerCase())) {
      cb(p);
    }
  }
}

let total = 0;
walk(ROOT, (file) => {
  let content = fs.readFileSync(file, 'utf8');
  let changed = false;
  for (const [from, to] of MAP) {
    if (content.includes(from)) {
      content = content.split(from).join(to);
      changed = true;
    }
  }
  if (changed) {
    fs.writeFileSync(file, content, 'utf8');
    total++;
    console.log('sanitized:', path.relative(ROOT, file));
  }
});
console.log('\n处理完成，共脱敏文件数:', total);
