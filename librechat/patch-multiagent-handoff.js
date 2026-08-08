#!/usr/bin/env node
/**
 * 部署补丁：为 @librechat/agents 的 MultiAgentGraph 增加"文本兜底交接"能力。
 *
 * v3 修复：v2 兜底虽然能路由到目标 Agent（A2），但只回传 A1 的原始 result，
 * 没有生成 transfer ToolMessage。A2 的 processHandoffReception 靠
 * `lc_transfer_to_<dest>` 的 ToolMessage 才能识别"被交接、需要执行查询"，
 * 缺失时 A2 会把 A1 的分类文本原样复述而不是执行工具。
 * v3 在路由前追加一个 name=`lc_transfer_to_<dest>` 的 ToolMessage，让 A2
 * 正确识别交接并进入"执行器"上下文。
 *
 * 使用：在 LibreChat 根目录执行 `node patch-multiagent-handoff.js`。
 * 幂等：v3 已应用跳过；v2/v1 自动升级到 v3。
 * 仅修改 dist 编译产物。
 */

const fs = require('fs');
const path = require('path');

const TARGETS = [
  {
    file: 'node_modules/@librechat/agents/dist/cjs/graphs/MultiAgentGraph.cjs',
    commandRef: '_langchain_langgraph.Command',
    messageRef: '_langchain_core_messages.ToolMessage',
  },
  {
    file: 'node_modules/@librechat/agents/dist/esm/graphs/MultiAgentGraph.mjs',
    commandRef: 'Command',
    messageRef: 'ToolMessage',
  },
];

const V1_MARKER = 'Robustness fallback: local/small models sometimes emit the';
const V2_MARKER = 'normalized.includes(dest)';
const V3_MARKER = 'id_fallback_';

/** v3 完整注入块 */
function buildInjection(commandRef, messageRef) {
  return `
				/**
				* Robustness fallback: local/small models sometimes emit the
				* transfer tool name as plain text instead of making a real
				* tool call. When a handoff source agent ends its turn with an
				* AI message that references \`lc_transfer_to_<dest>\` in text,
				* route to that destination anyway. A synthetic transfer
				* ToolMessage is appended so the receiving agent correctly
				* recognizes the handoff via processHandoffReception.
				*/
				if (handoffDestinations.size > 0) {
					const lastMessage = result.messages[result.messages.length - 1];
					if (lastMessage != null && lastMessage.getType() === "ai") {
						const content = typeof lastMessage.content === "string" ? lastMessage.content : "";
						const normalized = content.replace(/\\s+/g, "");
						for (const dest of handoffDestinations) {
							if (typeof dest === "string" && normalized.includes(dest)) {
								const transferMsg = new ${messageRef}({
									content: \`Successfully transferred to \${dest}\`,
									name: \`lc_transfer_to_\${dest}\`,
									tool_call_id: \`id_fallback_\${Date.now()}\`,
									additional_kwargs: { handoff_source_name: agentId }
								});
								return new ${commandRef}({
									update: { ...result, messages: result.messages.concat(transferMsg) },
									goto: dest
								});
							}
						}
					}
				}
`;
}

/** v3 内层 if 块（含 ToolMessage 生成） */
function v3InnerBlock() {
  return `if (typeof dest === "string" && normalized.includes(dest)) {
						const transferMsg = new ${'MSG_REF_PLACEHOLDER'}({
							content: \`Successfully transferred to \${dest}\`,
							name: \`lc_transfer_to_\${dest}\`,
							tool_call_id: \`id_fallback_\${Date.now()}\`,
							additional_kwargs: { handoff_source_name: agentId }
						});
						return new ${'CMD_REF_PLACEHOLDER'}({
							update: { ...result, messages: result.messages.concat(transferMsg) },
							goto: dest
						});
					}`;
}

function fillRefs(block, commandRef, messageRef) {
  return block
    .replaceAll('CMD_REF_PLACEHOLDER', commandRef)
    .replaceAll('MSG_REF_PLACEHOLDER', messageRef);
}

/** v2 if 块（无 ToolMessage） */
function v2InnerRegex() {
  return /if \(typeof dest === "string" && normalized\.includes\(dest\)\) \{[\s\S]*?return new [A-Za-z_.]+\(\{[\s\S]*?update: result,[\s\S]*?goto: dest[\s]*\}\);[\s]*\}/;
}

/** v1 内层（match 正则版） */
function v1InnerRegex() {
  return /const match = content\.match\(\/lc_transfer_to_\(\[A-Za-z0-9_-\]\+\)\/\);[\s\S]*?return new [A-Za-z_.]+\(\{[\s\S]*?update: result,[\s\S]*?goto: match\[1\][\s]*\}\);[\s]*\}[\s]*\}/;
}

function applyPatch(src, commandRef, messageRef, filePath) {
  if (src.includes(V3_MARKER)) {
    console.log(`[OK] 已应用 v3 补丁，跳过: ${filePath}`);
    return src;
  }
  if (src.includes(V2_MARKER)) {
    const re = v2InnerRegex();
    if (!re.test(src)) {
      console.log(`[FAIL] v2 补丁存在但无法定位替换点: ${filePath}`);
      return null;
    }
    src = src.replace(re, fillRefs(v3InnerBlock(), commandRef, messageRef));
    console.log(`[MIGRATE] v2 -> v3 升级成功: ${filePath}`);
    return src;
  }
  if (src.includes(V1_MARKER)) {
    const re = v1InnerRegex();
    if (!re.test(src)) {
      console.log(`[FAIL] v1 补丁存在但无法定位替换点: ${filePath}`);
      return null;
    }
    const v3Inner = `const normalized = content.replace(/\\s+/g, "");
						${fillRefs(v3InnerBlock(), commandRef, messageRef)}`;
    src = src.replace(re, v3Inner);
    console.log(`[MIGRATE] v1 -> v3 升级成功: ${filePath}`);
    return src;
  }
  const anchor = '} else result = await agentSubgraph.invoke(state, config);';
  const idx = src.indexOf(anchor);
  if (idx === -1) {
    console.log(`[FAIL] 未找到注入锚点: ${filePath}`);
    return null;
  }
  const injectAt = idx + anchor.length;
  src = src.slice(0, injectAt) + buildInjection(commandRef, messageRef) + src.slice(injectAt);
  console.log(`[DONE] 已打补丁: ${filePath}`);
  return src;
}

let allOk = true;
for (const target of TARGETS) {
  const abs = path.resolve(process.cwd(), target.file);
  if (!fs.existsSync(abs)) {
    console.log(`[SKIP] 文件不存在: ${abs}`);
    allOk = false;
    continue;
  }
  const original = fs.readFileSync(abs, 'utf8');
  const next = applyPatch(original, target.commandRef, target.messageRef, abs);
  if (next == null) {
    allOk = false;
    continue;
  }
  if (next !== original) fs.writeFileSync(abs, next, 'utf8');
}

console.log('\n补丁执行完成。请重启 LibreChat 后端使其生效。');
process.exit(allOk ? 0 : 1);