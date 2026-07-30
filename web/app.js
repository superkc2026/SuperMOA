
let VENDORS = []; let currentConfig = null; let keyVisible = false;

/** HTML 转义，防止 XSS 注入 */
function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** 将技术性错误消息转换为友好提示（前端版） */
function friendlyError(msg) {
  if (!msg) return '未知错误';
  var lower = String(msg).toLowerCase();
  if (/401|403/.test(msg) || lower.indexOf('unauthorized') >= 0 || lower.indexOf('forbidden') >= 0) return 'API Key 不正确，请检查';
  if (/429/.test(msg) || lower.indexOf('rate') >= 0) return '请求过于频繁，请稍后重试';
  if (/404/.test(msg)) return '模型不存在或地址错误，请检查 Base URL 和模型名';
  if (/50[0-9]/.test(msg)) return '模型服务暂时不可用，请稍后重试';
  if (lower.indexOf('connecterror') >= 0 || lower.indexOf('connecttimeout') >= 0 || lower.indexOf('connectionerror') >= 0) return '无法连接模型服务，请检查网络';
  if (lower.indexOf('timeout') >= 0) return '请求超时，请检查网络或稍后重试';
  if (lower.indexOf('httpstatuserro') >= 0) return '模型调用失败，请检查网络或 API Key';
  if (lower.indexOf('proxy') >= 0) return '代理连接失败，请检查代理设置';
  return msg.length > 200 ? msg.substring(0, 200) : msg;
}

async function init() {
  try {
    const [vRes, cRes, kRes] = await Promise.all([
      fetch('/api/vendors').then(r => r.json()),
      fetch('/api/config').then(r => r.json()),
      fetch('/api/key').then(r => r.json()),
    ]);
    VENDORS = vRes.vendors || [];
    currentConfig = cRes;
    document.getElementById('apiKey').textContent = kRes.masked;
    const baseUrlEl = document.getElementById('baseUrlHint');
    if (baseUrlEl) baseUrlEl.textContent = `${location.origin}/v1`;
    renderAll(); loadCombos();
    showToast('配置加载成功', 'success');
    // 非阻塞加载：更新检查、Profile、错误上报状态
    checkUpdate(); loadProfiles(); loadErrorReportingStatus();
    // 健康红绿灯
    updateHealthLight(); setInterval(updateHealthLight, 30000);
    // 首启引导检查
    checkFirstRun();
  } catch (e) { showToast('加载失败: ' + e.message, 'error'); }
}

function renderAll() {
  // 补充 _vendor 字段（导入的配置可能没有，根据 base_url 反查）
  const fillVendor = (m) => {
    if (m && !m._vendor && m.base_url) {
      const v = VENDORS.find(x => x.base_url === m.base_url);
      if (v) m._vendor = v.name;
    }
  };
  (currentConfig.reference_models || []).forEach(fillVendor);
  fillVendor(currentConfig.aggregator);
  fillVendor(currentConfig.default_passthrough);
  renderReferences(); renderAggregator(); renderPassthrough(); renderMoaParams(); updateReuseSelects(); renderUsage();
}

function renderUsage() {
  const box = document.getElementById('usageBox');
  if (!box) return;
  const agg = currentConfig.aggregator || {};
  const refs = currentConfig.reference_models || [];
  const aggTrigger = escapeHtml(agg.trigger || 'hh：');
  const pass = currentConfig.default_passthrough;
  const passModel = escapeHtml(pass ? pass.model : '（未配置，默认走 MOA）');
  let html = '<p><strong>客户端配置：</strong>Base URL 填上方地址，模型选 <code>SuperMOA</code></p>';
  html += `<p style="margin-top:8px;"><strong>触发词切换模式</strong>（在消息里加前缀即可切换）：</p>`;
  let idx = 1;
  html += `<p>${idx}. 默认（无触发词）→ 透传 <code>${passModel}</code>（快、省钱）</p>`;
  idx++;
  html += `<p>${idx}. <code>${aggTrigger}你的问题</code> → MOA 聚合引擎（质量高，慢）</p>`;
  refs.forEach((r) => {
    idx++;
    const t = escapeHtml(r.trigger || (r.model + '：'));
    const m = escapeHtml(r.model);
    html += `<p>${idx}. <code>${t}你的问题</code> → 直接调 <code>${m}</code></p>`;
  });
  html += '<p style="margin-top:8px;color:var(--text-muted);">支持 WorkBuddy / Hermes / 任何 OpenAI 兼容客户端，行为一致。</p>';
  box.innerHTML = html;
}

function vendorOptions(selected) { return `<option value="">— 自定义 —</option>` + VENDORS.map(v => `<option value="${v.name}" ${v.name===selected?'selected':''}>${v.name}</option>`).join(''); }
function selectModelOptions(vendorName, selected) {
  const v = VENDORS.find(x => x.name === vendorName);
  if (!v || !v.models || !v.models.length) return '<option value="">— 请先选厂商 —</option>';
  return v.models.map(m => `<option value="${m}" ${m===selected?'selected':''}>${m}</option>`).join('');
}

function renderReferences() {
  const list = document.getElementById('referenceList');
  const refs = currentConfig.reference_models || [];
  if (!refs.length) { list.innerHTML = '<div class="empty-state">未配置参考模型，点击右上角"+ 添加"</div>'; return; }
  list.innerHTML = refs.map((r, i) => `
    <div class="form-row" data-idx="${i}" data-type="ref">
      <div><label>厂商</label><select onchange="onVendorChange(this, ${i}, 'ref')">${vendorOptions(r._vendor || '')}</select></div>
      <div><label>Base URL</label><input type="text" value="${r.base_url || ''}" data-field="base_url"></div>
      <div><label>Model</label><select data-field="model">${selectModelOptions(r._vendor, r.model)}</select></div>
      <div><label>触发词（必填）</label><input type="text" value="${r.trigger || ''}" data-field="trigger" placeholder="如 hh：，消息开头加这个词就走这个模型"></div>
      <div class="btn-col"><input type="password" value="${r.api_key || ''}" data-field="api_key" placeholder="API Key" style="width:120px;"><button class="btn-secondary btn-icon" onclick="testModel(${i}, 'ref')" title="测试">⚡</button><button class="btn-danger btn-icon" onclick="removeReference(${i})" title="删除">✕</button></div>
      <div class="test-result" id="test-ref-${i}"></div>
    </div>`).join('');
}

function renderAggregator() {
  if (!currentConfig.aggregator) currentConfig.aggregator = { name:'', base_url:'', api_key:'', model:'' };
  const a = currentConfig.aggregator;
  document.getElementById('aggregatorForm').innerHTML = `
    <div class="form-row" data-type="agg">
      <div><label>厂商</label><select onchange="onVendorChange(this, 0, 'agg')">${vendorOptions(a._vendor || '')}</select></div>
      <div><label>Base URL</label><input type="text" value="${a.base_url || ''}" data-field="base_url"></div>
      <div><label>Model</label><select data-field="model">${selectModelOptions(a._vendor, a.model)}</select></div>
      <div><label>触发词（必填）</label><input type="text" value="${a.trigger || 'hh：'}" data-field="trigger" placeholder="如 hh：，消息开头加这个词就走聚合引擎"></div>
      <div class="btn-col"><input type="password" value="${a.api_key || ''}" data-field="api_key" placeholder="API Key" style="width:120px;"><button class="btn-secondary btn-icon" onclick="testModel(0, 'agg')" title="测试">⚡</button></div>
      <div class="test-result" id="test-agg-0"></div>
    </div>`;
}

function renderPassthrough() {
  const p = currentConfig.default_passthrough;
  const form = document.getElementById('passthroughForm');
  if (!p) { form.innerHTML = '<div class="empty-state">未配置（所有请求走 MOA）<button class="btn-secondary btn-small" style="margin-left:8px;" onclick="addPassthrough()">+ 启用透传</button></div>'; return; }
  form.innerHTML = `
    <div class="form-row" data-type="pass">
      <div><label>厂商</label><select onchange="onVendorChange(this, 0, 'pass')">${vendorOptions(p._vendor || '')}</select></div>
      <div><label>Base URL</label><input type="text" value="${p.base_url || ''}" data-field="base_url"></div>
      <div><label>Model</label><select data-field="model">${selectModelOptions(p._vendor, p.model)}</select></div>
      <div></div>
      <div class="btn-col"><input type="password" value="${p.api_key || ''}" data-field="api_key" placeholder="API Key" style="width:120px;"><button class="btn-secondary btn-icon" onclick="testModel(0, 'pass')" title="测试">⚡</button><button class="btn-danger btn-icon" onclick="removePassthrough()" title="删除">✕</button></div>
      <div class="test-result" id="test-pass-0"></div>
    </div>`;
}

function renderMoaParams() {
  const m = currentConfig.moa || {};
  document.getElementById('moaRefTemp').value = m.reference_temperature ?? 0.7;
  document.getElementById('moaRefMaxTokens').value = m.reference_max_tokens ?? 2048;
  document.getElementById('moaRefTimeout').value = m.reference_timeout ?? 30;
  document.getElementById('moaAggTimeout').value = m.aggregator_timeout ?? 120;
  document.getElementById('moaDegraded').value = m.degraded_policy || 'loud';
  document.getElementById('moaMaxCtx').value = m.max_context_messages ?? 10;
  document.getElementById('moaStream').value = String(m.stream ?? true);
}

function updateReuseSelects() {
  const refs = currentConfig.reference_models || [];
  const opts = '<option value="">— 选择参考模型 —</option>' + refs.map((r, i) => `<option value="${i}">${r.model || 'ref-'+i}</option>`).join('');
  const show = refs.length > 0;
  document.getElementById('aggReuseBar').style.display = show ? 'flex' : 'none';
  document.getElementById('passReuseBar').style.display = show ? 'flex' : 'none';
  document.getElementById('aggReuseSelect').innerHTML = opts;
  document.getElementById('passReuseSelect').innerHTML = opts;
}

function onVendorChange(sel, idx, type) {
  const v = VENDORS.find(x => x.name === sel.value); if (!v) return;
  const target = type === 'ref' ? currentConfig.reference_models[idx] : type === 'agg' ? currentConfig.aggregator : currentConfig.default_passthrough;
  Object.assign(target, { _vendor: v.name, base_url: v.base_url, model: v.models[0] || target.model });
  if (type === 'ref') renderReferences(); else if (type === 'agg') renderAggregator(); else renderPassthrough();
}

function addReference() { if (!currentConfig.reference_models) currentConfig.reference_models = []; if (currentConfig.reference_models.length >= 5) { showToast('最多 5 个', 'error'); return; } currentConfig.reference_models.push({name:'',base_url:'',api_key:'',model:'',trigger:''}); renderReferences(); updateReuseSelects(); }
function removeReference(idx) { currentConfig.reference_models.splice(idx, 1); renderReferences(); updateReuseSelects(); }
function addPassthrough() { currentConfig.default_passthrough = {name:'',base_url:'',api_key:'',model:''}; renderPassthrough(); }
function removePassthrough() { currentConfig.default_passthrough = null; renderPassthrough(); }

function reuseRef(type, idxStr) {
  const idx = parseInt(idxStr); if (isNaN(idx)) return;
  const ref = currentConfig.reference_models[idx]; if (!ref) return;
  if (type === 'agg') { currentConfig.aggregator = {...currentConfig.aggregator, _vendor: ref._vendor, base_url: ref.base_url, model: ref.model, api_key: ref.api_key}; renderAggregator(); }
  else { currentConfig.default_passthrough = {_vendor: ref._vendor, name:'', base_url: ref.base_url, model: ref.model, api_key: ref.api_key}; renderPassthrough(); }
  showToast('已复用参考模型配置', 'success');
}

function collectForm() {
  const refs = [];
  document.querySelectorAll('[data-type="ref"]').forEach(row => { const ref = {}; row.querySelectorAll('[data-field]').forEach(inp => ref[inp.dataset.field] = inp.value); refs.push(ref); });
  const aggRow = document.querySelector('[data-type="agg"]'); let aggregator = null;
  if (aggRow) { aggregator = {}; aggRow.querySelectorAll('[data-field]').forEach(inp => aggregator[inp.dataset.field] = inp.value); }
  const passRow = document.querySelector('[data-type="pass"]'); let passthrough = null;
  if (passRow) { passthrough = {}; passRow.querySelectorAll('[data-field]').forEach(inp => passthrough[inp.dataset.field] = inp.value); }
  return { gateway: currentConfig.gateway, reference_models: refs, aggregator, default_passthrough: passthrough,
    moa: { reference_temperature: parseFloat(document.getElementById('moaRefTemp').value), reference_max_tokens: parseInt(document.getElementById('moaRefMaxTokens').value), reference_timeout: parseInt(document.getElementById('moaRefTimeout').value), aggregator_timeout: parseInt(document.getElementById('moaAggTimeout').value), degraded_policy: document.getElementById('moaDegraded').value, max_context_messages: parseInt(document.getElementById('moaMaxCtx').value), stream: document.getElementById('moaStream').value === 'true' } };
}

async function saveConfig() {
  const cfg = collectForm();
  try { const resp = await fetch('/api/config', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)}); const data = await resp.json();
    if (resp.ok && data.status === 'ok') { showToast('配置已保存', 'success'); await loadConfig(); } else { showToast(data.error?.details?.join('; ') || data.error?.message || '保存失败', 'error'); }
  } catch (e) { showToast('保存失败: ' + e.message, 'error'); }
}
async function loadConfig() { currentConfig = await (await fetch('/api/config')).json(); renderAll(); }
function exportConfig() { const a = document.createElement('a'); a.href = '/api/config/export'; a.download = 'config.yaml'; document.body.appendChild(a); a.click(); document.body.removeChild(a); showToast('已导出（API Key 已脱敏）', 'success'); }
async function importConfig(event) {
  const file = event.target.files[0]; if (!file) return; const text = await file.text();
  try { const resp = await fetch('/api/config/import', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({yaml:text})}); const data = await resp.json();
    if (resp.ok && data.status === 'ok') { showToast('配置已导入', 'success'); await loadConfig(); } else { showToast(data.error?.message || '导入失败', 'error'); }
  } catch (e) { showToast('导入失败: ' + e.message, 'error'); } event.target.value = '';
}

async function testModel(idx, type) {
  const rows = document.querySelectorAll(`[data-type="${type === 'ref' ? 'ref' : type === 'agg' ? 'agg' : 'pass'}"]`);
  const row = type === 'ref' ? rows[idx] : rows[0]; if (!row) return;
  const cfg = { base_url: row.querySelector('[data-field="base_url"]').value, api_key: row.querySelector('[data-field="api_key"]').value, model: row.querySelector('[data-field="model"]').value };
  await doTest(cfg, `test-${type}-${type === 'ref' ? idx : 0}`);
}
async function doTest(cfg, resultId) {
  const el = document.getElementById(resultId); if (!el) return; el.className = 'test-result loading'; el.textContent = '测试中...';
  try { const data = await (await fetch('/api/test', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)})).json();
    if (data.status === 'ok') { el.className = 'test-result ok'; el.textContent = `✓ 成功 ${data.preview ? '| ' + data.preview : ''}`; }
    else { el.className = 'test-result error'; el.textContent = `✗ ${friendlyError(data.message || '失败')}`; }
  } catch (e) { el.className = 'test-result error'; el.textContent = '✗ ' + friendlyError(e.message); }
}

async function testAll() {
  const refCount = (currentConfig.reference_models || []).length;
  if (refCount === 0 && !currentConfig.aggregator) { showToast('没有可测试的模型', 'error'); return; }
  showToast('正在并行测试所有模型...', 'success');
  try { const data = await (await fetch('/api/test-all', {method:'POST'})).json();
    data.results.forEach((r, i) => {
      let el;
      if (i < refCount) el = document.getElementById(`test-ref-${i}`);
      else if (i === refCount) el = document.getElementById('test-agg-0');
      else el = document.getElementById('test-pass-0');
      if (el) { if (r.status === 'ok') { el.className = 'test-result ok'; el.textContent = `✓ ${r.name || '模型'} 成功`; } else { el.className = 'test-result error'; el.textContent = `✗ ${r.name || '模型'}: ${friendlyError(r.message || '失败')}`; } }
    });
    const ok = data.results.filter(r => r.status === 'ok').length;
    showToast(`测试完成: ${ok}/${data.results.length} 可用`, ok === data.results.length ? 'success' : 'error');
  } catch (e) { showToast('测试失败: ' + e.message, 'error'); }
}

async function loadCombos() {
  try { const data = await (await fetch('/api/recommended-combos')).json();
    document.getElementById('combosList').innerHTML = data.combos.map((c, i) => {
      const refHtml = c.references.map(r => `<span class="role ref">${r.vendor} ${r.model}</span> ${r.reason}`).join('<br>');
      return `<div class="combo-card"><div class="combo-name">${c.name}</div><div class="combo-desc">${c.desc}</div><div class="combo-models"><strong>参考:</strong> ${refHtml}<br><strong>聚合:</strong> <span class="role agg">${c.aggregator.vendor} ${c.aggregator.model}</span> ${c.aggregator.reason}<br><strong>透传:</strong> <span class="role pass">${c.passthrough.vendor} ${c.passthrough.model}</span> ${c.passthrough.reason}</div><button class="btn-primary btn-small" onclick="applyCombo(${i})">应用此组合</button></div>`;
    }).join('');
    window._combos = data.combos;
  } catch (e) { document.getElementById('combosList').innerHTML = '加载失败'; }
}
async function applyCombo(idx) {
  const c = window._combos[idx]; if (!c) return;
  const vfind = n => VENDORS.find(x => x.name === n);
  currentConfig.reference_models = c.references.map(r => { const v = vfind(r.vendor); return {_vendor: r.vendor, name:'', base_url: v?v.base_url:'', model: r.model, api_key:'', provider:'openai'}; });
  const av = vfind(c.aggregator.vendor), pv = vfind(c.passthrough.vendor);
  currentConfig.aggregator = {_vendor: c.aggregator.vendor, name:'', base_url: av?av.base_url:'', model: c.aggregator.model, api_key:''};
  currentConfig.default_passthrough = {_vendor: c.passthrough.vendor, name:'', base_url: pv?pv.base_url:'', model: c.passthrough.model, api_key:''};
  renderAll(); showToast('已应用组合，请填 API Key 后保存', 'success');
}

function runDemo() { document.getElementById('demoModal').classList.add('show'); }
function closeDemo() { document.getElementById('demoModal').classList.remove('show'); }
function formatContent(text) {
  // 转义 HTML 防注入，再渲染 ** 加粗，保留换行（CSS pre-wrap 配合）
  const div = document.createElement('div');
  div.textContent = text || '';
  let safe = div.innerHTML;
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  return safe;
}
async function executeDemo() {
  const prompt = document.getElementById('demoPrompt').value.trim(); if (!prompt) { showToast('请输入问题', 'error'); return; }
  document.getElementById('demoRunBtn').disabled = true; document.getElementById('demoLoading').style.display = 'block'; document.getElementById('demoResults').style.display = 'none';
  try { const data = await (await fetch('/api/demo', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})})).json();
    if (data.error) { showToast(data.error.message, 'error'); return; }
    const refHtml = data.references.map(r => `<div class="demo-ref"><div class="ref-name">${r.model}</div>${formatContent(r.content)}</div>`).join('');
    document.getElementById('demoResults').innerHTML = `<div class="demo-col"><h3>📚 参考模型（${data.references.length} 个）</h3>${refHtml}</div><div class="demo-col"><h3>🎯 聚合最终答案</h3><div class="demo-agg"><div class="ref-name">${data.aggregator.model}</div>${formatContent(data.aggregator.content)}</div></div>`;
    document.getElementById('demoResults').style.display = 'grid';
  } catch (e) { showToast('演示失败: ' + e.message, 'error'); }
  finally { document.getElementById('demoRunBtn').disabled = false; document.getElementById('demoLoading').style.display = 'none'; }
}

async function toggleKeyVisibility() { const data = await (await fetch('/api/key')).json(); document.getElementById('apiKey').textContent = keyVisible ? data.masked : data.key; keyVisible = !keyVisible; }
async function copyKey() { const data = await (await fetch('/api/key')).json(); try { await navigator.clipboard.writeText(data.key); showToast('Key 已复制', 'success'); } catch (e) { prompt('手动复制:', data.key); } }
async function copyBaseUrl() { const url = document.getElementById('baseUrlHint').textContent; try { await navigator.clipboard.writeText(url); showToast('URL 已复制', 'success'); } catch (e) { prompt('手动复制:', url); } }
async function regenerateKey() { if (!confirm('确定重新生成？旧 Key 立即失效。')) return; const data = await (await fetch('/api/regenerate-key', {method:'POST'})).json(); document.getElementById('apiKey').textContent = data.masked; showToast('Key 已重新生成', 'success'); }

function showToast(msg, type) { const t = document.getElementById('toast'); t.textContent = msg; t.className = `toast ${type} show`; setTimeout(() => t.className = 'toast', 3000); }

// ============ 调用记录 ============
let _logsRefreshTimer = null;
let _lastLogSignature = '';
function openLogs() { document.getElementById('logsModal').classList.add('show'); loadLogs(); _logsRefreshTimer = setInterval(loadLogs, 2000); }
function closeLogs() { document.getElementById('logsModal').classList.remove('show'); if (_logsRefreshTimer) { clearInterval(_logsRefreshTimer); _logsRefreshTimer = null; } }
function exportLogs(fmt) { window.open(`/api/logs/export?format=${fmt}`, '_blank'); }
async function loadLogs() {
  const el = document.getElementById('logsContent');
  if (el.innerHTML === '' || el.innerHTML === '加载中...') el.innerHTML = '加载中...';
  try {
    const data = await (await fetch('/api/logs')).json();
    if (!data.logs || !data.logs.length) { el.innerHTML = '<div style="color:var(--text-muted);padding:8px;">暂无调用记录</div>'; _lastLogSignature = ''; return; }
    // 反转：最新在底部
    const logs = data.logs.slice().reverse();
    // 对比签名（最新时间 + 数量），没变化不刷新 DOM
    const sig = logs[logs.length - 1].time + '_' + logs.length;
    if (sig === _lastLogSignature) return;
    _lastLogSignature = sig;
    el.innerHTML = '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
      '<tr style="border-bottom:2px solid var(--border);"><th style="text-align:left;padding:4px;">时间</th><th style="text-align:left;padding:4px;">来源</th><th style="text-align:left;padding:4px;">路由</th><th style="text-align:left;padding:4px;">实际模型</th><th style="text-align:left;padding:4px;">前缀</th><th style="text-align:left;padding:4px;">消息预览</th></tr>' +
      logs.map(l => {
        const rc = l.route === 'moa' ? 'color:var(--primary);font-weight:600;' : 'color:var(--success);';
        const rl = l.route === 'moa' ? 'MOA 聚合' : '透传';
        return `<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px;color:var(--text-muted);">${escapeHtml(l.time)}</td><td style="padding:4px;color:var(--text-muted);">${escapeHtml(l.client) || '—'}</td><td style="padding:4px;${rc}">${escapeHtml(rl)}</td><td style="padding:4px;">${escapeHtml(l.actual_model)}</td><td style="padding:4px;color:var(--text-muted);">${escapeHtml(l.prefix) || '无前缀'}</td><td style="padding:4px;color:var(--text-muted);max-width:200px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(l.prompt_preview)}</td></tr>`;
      }).join('') + '</table>';
    el.scrollTop = el.scrollHeight;
  } catch (e) { el.innerHTML = '加载失败: ' + e.message; }
}

// ============ 更新检查（REQ-P3） ============
async function checkUpdate() {
  try {
    const data = await (await fetch('/api/check-update')).json();
    if (data.has_update) {
      const banner = document.getElementById('updateBanner');
      document.getElementById('updateBannerText').textContent =
        `发现新版本 v${data.latest_version}（当前 v${data.current_version}）`;
      banner.classList.add('show');
      window._updateInfo = data;
    }
  } catch (e) { /* 静默失败，不影响主流程 */ }
}
function viewUpdateDetails() {
  const info = window._updateInfo;
  if (info && info.release_notes) {
    alert(`版本 ${info.latest_version} 更新内容：\n\n${info.release_notes}`);
  } else if (info && info.download_url) {
    window.open(info.download_url, '_blank');
  }
}
function downloadUpdate() {
  const info = window._updateInfo;
  if (info && info.download_url) { window.open(info.download_url, '_blank'); }
}
function dismissUpdate() {
  document.getElementById('updateBanner').classList.remove('show');
}

// ============ 用量统计（REQ-13 前端） ============
async function loadUsage() {
  const el = document.getElementById('usageTable');
  if (!el) return;
  el.innerHTML = '加载中...';
  try {
    const data = await (await fetch('/api/usage')).json();
    if (!data.daily || !data.daily.length) {
      el.innerHTML = '<div class="empty-state">暂无用量数据</div>';
      return;
    }
    let html = '<table class="usage-table"><thead><tr><th>日期</th><th>模型</th><th>路由</th><th>Prompt</th><th>Completion</th><th>总Tokens</th><th>成本(¥)</th></tr></thead><tbody>';
    data.daily.forEach(function (d) {
      html += '<tr><td>' + escapeHtml(d.date) + '</td><td>' + escapeHtml(d.model) + '</td><td>' + escapeHtml(d.route) + '</td>'
        + '<td>' + (d.prompt_tokens || 0) + '</td><td>' + (d.completion_tokens || 0) + '</td><td>' + (d.total_tokens || 0) + '</td>'
        + '<td>' + (d.cost || 0).toFixed(4) + '</td></tr>';
    });
    var t = data.total || {};
    html += '<tr class="total-row"><td colspan="3">总计</td><td>' + (t.prompt_tokens || 0) + '</td><td>'
      + (t.completion_tokens || 0) + '</td><td>' + (t.total_tokens || 0) + '</td><td>' + (t.cost || 0).toFixed(4) + '</td></tr>';
    html += '</tbody></table>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = '<div class="empty-state">加载失败: ' + escapeHtml(e.message) + '</div>';
  }
}
function exportUsageCsv() { window.open('/api/usage/export', '_blank'); }

// ============ 错误上报开关（REQ-P5 前端） ============
// ============ 健康红绿灯 ============
async function updateHealthLight() {
  const el = document.getElementById('healthLight');
  if (!el) return;
  try {
    const data = await (await fetch('/api/health-status')).json();
    const models = data.models || [];
    const healthy = models.filter(m => m.healthy);
    if (models.length === 0) { el.textContent = '⚪'; el.title = '未配置模型'; return; }
    if (healthy.length === models.length) { el.textContent = '🟢'; el.title = `全部健康（${healthy.length}/${models.length}）`; }
    else if (healthy.length === 0) { el.textContent = '🔴'; el.title = `全部不健康（0/${models.length}）`; }
    else { el.textContent = '🟡'; el.title = `部分不健康（${healthy.length}/${models.length}）`; }
  } catch (e) { el.textContent = '🔴'; el.title = '健康检查失败'; }
}

async function loadErrorReportingStatus() {
  try {
    var data = await (await fetch('/api/status')).json();
    var toggle = document.getElementById('errorReportingToggle');
    if (toggle) toggle.checked = !!data.error_reporting_enabled;
  } catch (e) { /* 静默失败 */ }
}
async function toggleErrorReporting() {
  var toggle = document.getElementById('errorReportingToggle');
  var enabled = toggle.checked;
  try {
    var resp = await fetch('/api/error-reporting/toggle', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: enabled })
    });
    var data = await resp.json();
    if (data.enabled !== undefined) {
      toggle.checked = data.enabled;
      showToast(data.enabled ? '错误上报已开启' : '错误上报已关闭', 'success');
    }
  } catch (e) {
    toggle.checked = !enabled;
    showToast('切换失败: ' + e.message, 'error');
  }
}

// ============ 首启引导向导（REQ-14 前端） ============
var wizardStepNum = 1;
var wizardSelectedComboIdx = -1;
var wizardConfig = null;

async function checkFirstRun() {
  try {
    var data = await (await fetch('/api/status')).json();
    if (data.is_first_run) { openWizard(); }
  } catch (e) { /* 静默失败 */ }
}
function openWizard() {
  document.getElementById('wizardModal').classList.add('show');
  wizardStepNum = 0; wizardSelectedComboIdx = -1; wizardConfig = null;
  showWizardStep(0);
}
function closeWizard() { document.getElementById('wizardModal').classList.remove('show'); }
function showWizardStep(step) {
  wizardStepNum = step;
  for (var i = 0; i <= 3; i++) {
    var el = document.getElementById('wizardStep' + i);
    if (el) el.classList.toggle('active', i === step);
    var indicator = document.getElementById('wizardStep' + i + 'Indicator');
    if (indicator) {
      indicator.classList.toggle('active', i === step);
      indicator.classList.toggle('done', i < step);
    }
  }
  // Step 0: concept explanation — hide progress bar, show only "我知道了"
  var progressEl = document.getElementById('wizardProgress');
  if (progressEl) progressEl.style.display = step === 0 ? 'none' : 'flex';
  document.getElementById('wizardPrevBtn').style.display = step > 1 ? 'inline-block' : 'none';
  document.getElementById('wizardNextBtn').textContent = step === 0 ? '我知道了' : (step === 3 ? '完成' : '下一步');
  document.getElementById('wizardCancelBtn').textContent = step === 0 ? '跳过' : (step === 1 ? '跳过' : '取消');
  // Step 1: load combos when first entering
  if (step === 1) loadWizardCombos();
}
async function loadWizardCombos() {
  try {
    var data = await (await fetch('/api/recommended-combos')).json();
    window._combos = data.combos;
    var el = document.getElementById('wizardCombos');
    el.innerHTML = data.combos.map(function (c, i) {
      var refHtml = c.references.map(function (r) { return '<span class="role ref">' + escapeHtml(r.vendor) + ' ' + escapeHtml(r.model) + '</span>'; }).join(' ');
      return '<div class="wizard-combo-card" id="wizardCombo' + i + '" onclick="selectWizardCombo(' + i + ')">'
        + '<div class="combo-name">' + escapeHtml(c.name) + '</div>'
        + '<div class="combo-desc">' + escapeHtml(c.desc) + '</div>'
        + '<div class="combo-models"><strong>参考:</strong> ' + refHtml + '<br>'
        + '<strong>聚合:</strong> <span class="role agg">' + escapeHtml(c.aggregator.vendor) + ' ' + escapeHtml(c.aggregator.model) + '</span><br>'
        + '<strong>透传:</strong> <span class="role pass">' + escapeHtml(c.passthrough.vendor) + ' ' + escapeHtml(c.passthrough.model) + '</span></div></div>';
    }).join('');
  } catch (e) {
    document.getElementById('wizardCombos').innerHTML = '<div class="empty-state">加载推荐组合失败</div>';
  }
}
function selectWizardCombo(idx) {
  wizardSelectedComboIdx = idx;
  var cards = document.querySelectorAll('.wizard-combo-card');
  cards.forEach(function (el, i) { el.classList.toggle('selected', i === idx); });
}
async function wizardNext() {
  if (wizardStepNum === 0) {
    showWizardStep(1);
    return;
  }
  if (wizardStepNum === 1) {
    if (wizardSelectedComboIdx < 0) { showToast('请选择一个组合', 'error'); return; }
    var c = window._combos[wizardSelectedComboIdx];
    var vfind = function (n) { return VENDORS.find(function (x) { return x.name === n; }); };
    wizardConfig = {
      gateway: currentConfig.gateway || { host: '127.0.0.1', port: 12345 },
      reference_models: c.references.map(function (r) {
        var v = vfind(r.vendor);
        return { _vendor: r.vendor, name: '', base_url: v ? v.base_url : '', model: r.model, api_key: '', trigger: r.vendor.toLowerCase().slice(0, 4) + '：' };
      }),
      aggregator: (function () {
        var av = vfind(c.aggregator.vendor);
        return { _vendor: c.aggregator.vendor, name: '', base_url: av ? av.base_url : '', model: c.aggregator.model, api_key: '', trigger: 'hh：' };
      })(),
      default_passthrough: (function () {
        var pv = vfind(c.passthrough.vendor);
        return { _vendor: c.passthrough.vendor, name: '', base_url: pv ? pv.base_url : '', model: c.passthrough.model, api_key: '' };
      })(),
      moa: currentConfig.moa || {}
    };
    renderWizardKeyInputs();
    showWizardStep(2);
  } else if (wizardStepNum === 2) {
    collectWizardKeys();
    try {
      var resp = await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(wizardConfig) });
      var data = await resp.json();
      if (resp.ok && data.status === 'ok') {
        currentConfig = wizardConfig;
        renderWizardComplete();
        showWizardStep(3);
      } else { showToast(data.error ? data.error.message : '保存失败', 'error'); }
    } catch (e) { showToast('保存失败: ' + e.message, 'error'); }
  } else if (wizardStepNum === 3) {
    closeWizard();
    location.reload();
  }
}
function wizardPrev() { if (wizardStepNum > 1) showWizardStep(wizardStepNum - 1); }
function renderWizardKeyInputs() {
  var el = document.getElementById('wizardKeyInputs');
  var html = '';
  wizardConfig.reference_models.forEach(function (r, i) {
    html += '<div class="form-row" style="grid-template-columns: 1fr 2fr auto;">'
      + '<div><label>参考模型 ' + (i + 1) + '</label><input type="text" value="' + escapeHtml(r.model) + '" disabled></div>'
      + '<div><label>API Key</label><input type="password" id="wizardKeyRef' + i + '" placeholder="输入 API Key" style="width:100%;"></div>'
      + '<div class="btn-col"><button class="btn-secondary btn-small" onclick="wizardTestModel(\'ref\', ' + i + ')">⚡ 测试</button><div class="test-result" id="wizardTestRef' + i + '"></div></div></div>';
  });
  html += '<div class="form-row" style="grid-template-columns: 1fr 2fr auto;">'
    + '<div><label>聚合模型</label><input type="text" value="' + escapeHtml(wizardConfig.aggregator.model) + '" disabled></div>'
    + '<div><label>API Key</label><input type="password" id="wizardKeyAgg" placeholder="输入 API Key" style="width:100%;"></div>'
    + '<div class="btn-col"><button class="btn-secondary btn-small" onclick="wizardTestModel(\'agg\', 0)">⚡ 测试</button><div class="test-result" id="wizardTestAgg0"></div></div></div>';
  if (wizardConfig.default_passthrough) {
    html += '<div class="form-row" style="grid-template-columns: 1fr 2fr auto;">'
      + '<div><label>透传模型</label><input type="text" value="' + escapeHtml(wizardConfig.default_passthrough.model) + '" disabled></div>'
      + '<div><label>API Key</label><input type="password" id="wizardKeyPass" placeholder="输入 API Key" style="width:100%;"></div>'
      + '<div class="btn-col"><button class="btn-secondary btn-small" onclick="wizardTestModel(\'pass\', 0)">⚡ 测试</button><div class="test-result" id="wizardTestPass0"></div></div></div>';
  }
  el.innerHTML = html;
}
function collectWizardKeys() {
  wizardConfig.reference_models.forEach(function (r, i) {
    var el = document.getElementById('wizardKeyRef' + i);
    if (el) r.api_key = el.value;
  });
  var aggEl = document.getElementById('wizardKeyAgg');
  if (aggEl) wizardConfig.aggregator.api_key = aggEl.value;
  var passEl = document.getElementById('wizardKeyPass');
  if (passEl && wizardConfig.default_passthrough) wizardConfig.default_passthrough.api_key = passEl.value;
}
async function wizardTestModel(type, idx) {
  var cfg, resultId;
  if (type === 'ref') {
    var r = wizardConfig.reference_models[idx];
    var keyEl = document.getElementById('wizardKeyRef' + idx);
    cfg = { base_url: r.base_url, api_key: keyEl ? keyEl.value : '', model: r.model };
    resultId = 'wizardTestRef' + idx;
  } else if (type === 'agg') {
    var a = wizardConfig.aggregator;
    var aggKeyEl = document.getElementById('wizardKeyAgg');
    cfg = { base_url: a.base_url, api_key: aggKeyEl ? aggKeyEl.value : '', model: a.model };
    resultId = 'wizardTestAgg0';
  } else {
    var p = wizardConfig.default_passthrough;
    var passKeyEl = document.getElementById('wizardKeyPass');
    cfg = { base_url: p.base_url, api_key: passKeyEl ? passKeyEl.value : '', model: p.model };
    resultId = 'wizardTestPass0';
  }
  await doTest(cfg, resultId);
}
function renderWizardComplete() {
  var el = document.getElementById('wizardCompleteInfo');
  var apiKey = document.getElementById('apiKey').textContent;
  var baseUrl = document.getElementById('baseUrlHint').textContent;
  var aggTrigger = wizardConfig.aggregator.trigger || 'hh：';
  var html = '<div class="wizard-info-box">';
  html += '<p><strong>Base URL:</strong> <code>' + escapeHtml(baseUrl) + '</code> <button class="btn-secondary btn-small" onclick="copyText(\'' + escapeHtml(baseUrl) + '\')">复制</button></p>';
  html += '<p><strong>API Key:</strong> <code>' + escapeHtml(apiKey) + '</code> <button class="btn-secondary btn-small" onclick="copyText(\'' + escapeHtml(apiKey) + '\')">复制</button></p>';
  html += '<p><strong>模型名:</strong> <code>SuperMOA</code></p>';
  html += '</div>';
  html += '<div class="wizard-info-box">';
  html += '<p><strong>触发词用法：</strong></p>';
  html += '<p>1. 默认（无前缀）→ 透传 <code>' + escapeHtml(wizardConfig.default_passthrough ? wizardConfig.default_passthrough.model : '未配置') + '</code></p>';
  html += '<p>2. <code>' + escapeHtml(aggTrigger) + '你的问题</code> → MOA 聚合引擎</p>';
  html += '</div>';
  html += '<p style="color:var(--text-muted);font-size:12px;margin-top:12px;">在智能体客户端中配置以上信息即可开始使用。点击「完成」进入配置页。</p>';
  el.innerHTML = html;
}
function copyText(text) {
  navigator.clipboard.writeText(text).then(function () { showToast('已复制', 'success'); }).catch(function () { prompt('手动复制:', text); });
}

// ============ Profile 管理（REQ-20 前端） ============
async function loadProfiles() {
  try {
    var data = await (await fetch('/api/profiles')).json();
    var select = document.getElementById('profileSelect');
    if (!select) return;
    select.innerHTML = (data.profiles || []).map(function (p) {
      var label = p.name === 'default' ? '默认' : p.name;
      return '<option value="' + escapeHtml(p.name) + '"' + (p.active ? ' selected' : '') + '>' + escapeHtml(label) + '</option>';
    }).join('');
  } catch (e) { /* 静默失败 */ }
}
async function switchProfile() {
  var select = document.getElementById('profileSelect');
  var name = select.value;
  if (!name) return;
  try {
    var resp = await fetch('/api/profiles/switch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }) });
    var data = await resp.json();
    if (data.success) { showToast('已切换到 Profile: ' + name, 'success'); location.reload(); }
    else { showToast('切换失败', 'error'); }
  } catch (e) { showToast('切换失败: ' + e.message, 'error'); }
}
async function saveNewProfile() {
  var name = prompt('请输入新 Profile 名称：');
  if (!name || !name.trim()) return;
  try {
    var resp = await fetch('/api/profiles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.trim() }) });
    var data = await resp.json();
    if (data.success) { showToast('Profile "' + name.trim() + '" 已保存', 'success'); await loadProfiles(); }
    else { showToast('保存失败', 'error'); }
  } catch (e) { showToast('保存失败: ' + e.message, 'error'); }
}
async function deleteProfile() {
  var select = document.getElementById('profileSelect');
  var name = select.value;
  if (!name) return;
  if (!confirm('确定删除 Profile "' + name + '"？')) return;
  try {
    var resp = await fetch('/api/profiles/' + encodeURIComponent(name), { method: 'DELETE' });
    var data = await resp.json();
    if (data.success) { showToast('Profile "' + name + '" 已删除', 'success'); await loadProfiles(); }
    else { showToast('删除失败', 'error'); }
  } catch (e) { showToast('删除失败: ' + e.message, 'error'); }
}

init();
