/* ═══════════════════════════════════════════════
   Zhui115 — 前端 SPA
   ═══════════════════════════════════════════════ */

const API_BASE = '/api';

// ── Utility ──
const $ = (s, p = document) => p.querySelector(s);
const $$ = (s, p = document) => [...p.querySelectorAll(s)];
const escapeHtml = s => {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
};
const formatDate = s => {
  if (!s) return '-';
  try {
    const d = new Date(s.endsWith('Z') ? s : s + 'Z');
    return d.toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return s; }
};

// ── Toast ──
function toast(msg, type = 'success') {
  const c = $('#toastContainer');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

// ── Modal ──
function openModal(title, bodyHtml, footerHtml = '') {
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = bodyHtml;
  $('#modalFooter').innerHTML = footerHtml;
  $('#modalOverlay').style.display = 'flex';
}
function closeModal() { $('#modalOverlay').style.display = 'none'; }
$('#modalClose').onclick = closeModal;
$('#modalOverlay').onclick = e => { if (e.target === e.currentTarget) closeModal(); };

// ── API call ──
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) {
    opts.body = JSON.stringify(body);
    opts.headers['Content-Type'] = 'application/json';
  }
  const resp = await fetch(API_BASE + path, opts);
  let data;
  const ct = resp.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    data = await resp.json();
  } else {
    const text = await resp.text();
    if (!resp.ok) throw new Error(text || `HTTP ${resp.status}`);
    try { data = JSON.parse(text); } catch { data = { message: text }; }
  }
  if (!resp.ok && data.error) throw new Error(data.error);
  return data;
}

// ── Navigation ──
const pages = {};

function navigate(page) {
  $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.page === page));
  const titleMap = {
    dashboard: '总览', sources: 'RSS 源管理', tasks: '离线任务',
    retry: '重试队列', history: '操作日志', settings: '设置',
  };
  $('#pageTitle').textContent = titleMap[page] || '总览';
  renderPage(page);
}

function renderPage(page) {
  if (pages[page]) pages[page]();
}

$$('.nav-item').forEach(el => {
  el.onclick = e => {
    e.preventDefault();
    navigate(el.dataset.page);
  };
});

// ── Sidebar toggle (mobile) ──
$('#menuToggle').onclick = () => $('#sidebar').classList.toggle('open');
document.addEventListener('click', e => {
  if (window.innerWidth <= 768 && !e.target.closest('.sidebar') && !e.target.closest('#menuToggle')) {
    $('#sidebar').classList.remove('open');
  }
});

// ── Page: Dashboard ──
pages.dashboard = async function() {
  const c = $('#content');
  c.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⏳</div><div>加载中...</div></div>';

  try {
    const [stats, sched, conn, quota] = await Promise.all([
      api('GET', '/tasks/stats'),
      api('GET', '/scheduler/status'),
      api('GET', '/115/status'),
      api('GET', '/global'),
    ]);

    const total = stats.total || 0;
    const done = stats['已完成'] || 0;
    const failed = stats['失败'] || 0;
    const pending = stats['等待提交'] || 0;
    const submitted = stats['已提交'] || 0;
    const pendingRetry = stats.pending_retry || 0;

    let quotaHtml = '';
    if (conn.connected && conn.quota && conn.quota.ok) {
      const q = conn.quota.data;
      quotaHtml = `<div class="card">
        <div class="card-title">离线配额</div>
        <div class="card-value" style="font-size:1rem">剩余 ${q.quota || 0} / 总数 ${q.total_quota || '-'}</div>
      </div>`;
    }

    c.innerHTML = `
      <div class="stats-grid">
        <div class="card">
          <div class="card-header"><span class="card-title">总链接</span></div>
          <div class="card-value">${total}</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">已完成</span></div>
          <div class="card-value" style="color:var(--success)">${done}</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">等待提交</span></div>
          <div class="card-value" style="color:var(--accent)">${pending}</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">已提交</span></div>
          <div class="card-value">${submitted}</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">失败</span></div>
          <div class="card-value" style="color:var(--danger)">${failed}</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">等待重试</span></div>
          <div class="card-value" style="color:var(--warning)">${pendingRetry}</div>
        </div>
        ${quotaHtml}
      </div>

      <div class="section">
        <div class="section-title">⚙️ 系统状态</div>
        <table>
          <tr><td>调度器</td><td><span class="tag ${sched.running ? 'tag-done' : 'tag-failed'}">${sched.running ? '运行中' : '已停止'}</span></td></tr>
          <tr><td>115 连接</td><td><span class="tag ${conn.connected ? 'tag-done' : 'tag-failed'}">${conn.connected ? '已连接' : '未连接'}</span></td></tr>
          <tr><td>RSS 源数</td><td>${(await api('GET', '/sources')).length}</td></tr>
        </table>
      </div>
    `;

    // 更新侧边栏状态
    updateSidebarStatus(conn, sched);
  } catch (e) {
    c.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div>加载失败: ${escapeHtml(e.message)}</div></div>`;
  }
};

function updateSidebarStatus(conn, sched) {
  const cs = $('#conn-status');
  const ss = $('#sched-status');
  if (conn.connected) {
    cs.innerHTML = '<span class="dot on"></span> 115 已连接';
  } else {
    cs.innerHTML = `<span class="dot off"></span> 115 ${conn.message || '未连接'}`;
  }
  ss.innerHTML = sched.running
    ? '<span class="dot on"></span> 调度运行中'
    : '<span class="dot off"></span> 调度已停止';
}

// ── Page: Sources ──
let sourceFilterTerm = '';

pages.sources = async function() {
  const c = $('#content');
  c.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⏳</div><div>加载中...</div></div>';

  try {
    const sources = await api('GET', '/sources');

    c.innerHTML = `
      <div class="section">
        <div class="card-header">
          <span class="section-title" style="margin:0">📡 RSS 源 (${sources.length})</span>
          <button class="btn btn-primary btn-sm" onclick="showAddSource()">＋ 添加源</button>
        </div>
        <div class="card" style="padding:0">
          <div style="padding:8px 12px;border-bottom:1px solid var(--border)">
            <input class="form-input" type="text" placeholder="搜索源名称..." id="sourceFilter"
                   value="${escapeHtml(sourceFilterTerm)}" style="max-width:300px">
          </div>
          <div id="sourceList">
            ${renderSourceList(sources, sourceFilterTerm)}
          </div>
        </div>
      </div>
    `;

    $('#sourceFilter').oninput = function() {
      sourceFilterTerm = this.value;
      renderSourceListFilter(sources, sourceFilterTerm);
    };
  } catch (e) {
    c.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div>${escapeHtml(e.message)}</div></div>`;
  }
};

function renderSourceList(sources, filter) {
  const filtered = filter
    ? sources.filter(s => s.name.toLowerCase().includes(filter.toLowerCase()))
    : sources;

  if (!filtered.length) {
    return `<div class="empty-state" style="padding:24px">
      <div class="empty-state-title">没有 RSS 源</div>
      <div class="empty-state-desc">点击上方按钮添加第一个源</div>
    </div>`;
  }

  return filtered.map(s => {
    const enabled = s.enabled !== false;
    return `<div class="source-item">
      <div class="source-info">
        <div class="source-name">${escapeHtml(s.name)}
          <span class="tag ${enabled ? 'tag-enabled' : 'tag-disabled'}" style="margin-left:8px">
            ${enabled ? '已启用' : '已禁用'}
          </span>
        </div>
        <div class="source-url" title="${escapeHtml(s.url)}">${escapeHtml(s.url)}</div>
        <div class="source-meta">
          ${s.show_name ? `<span>🎬 ${escapeHtml(s.show_name)}</span>` : ''}
          ${s.season ? `<span>第${s.season}季</span>` : ''}
          ${s.episode_from || s.episode_to ? `<span>📺 ${s.episode_from || 1}~${s.episode_to || '∞'}集</span>` : ''}
          ${s.filter_keywords && s.filter_keywords.length ? `<span>🔑 ${s.filter_keywords.join(', ')}</span>` : ''}
        </div>
      </div>
      <div class="source-actions">
        <button class="btn btn-sm btn-ghost" onclick="showTestSource('${escapeHtml(s.url)}')">测试</button>
        <button class="btn btn-sm btn-ghost" onclick="showEditSource('${escapeHtml(s.name)}')">编辑</button>
        <button class="btn btn-sm ${enabled ? 'btn-ghost' : 'btn-success'}" onclick="toggleSource('${escapeHtml(s.name)}', ${!enabled})">
          ${enabled ? '⏹ 停用' : '▶ 启用'}
        </button>
        <button class="btn btn-sm btn-danger" onclick="deleteSource('${escapeHtml(s.name)}')">✕ 删除</button>
      </div>
    </div>`;
  }).join('');
}

function renderSourceListFilter(sources, filter) {
  const list = $('#sourceList');
  if (list) list.innerHTML = renderSourceList(sources, filter);
}

// ── Source CRUD ──
function emptySource() {
  return {
    name: '', url: '', enabled: true, show_name: '', season: 0,
    filter_keywords: [], filter_exclude: [], episode_pattern: '',
    auto_episode: false, last_episode: 0, check_interval: 0,
    episode_from: 0, episode_to: 0, regex_filter: false,
    dedup_group: '', description: '',
  };
}

function sourceFormHtml(s, edit = false) {
  return `
    <div class="form-group">
      <label class="form-label">源名称 *</label>
      <input class="form-input" id="sf_name" value="${escapeHtml(s.name)}" placeholder="如: 动漫花园-动画">
    </div>
    <div class="form-group">
      <label class="form-label">RSS URL *</label>
      <input class="form-input" id="sf_url" value="${escapeHtml(s.url)}" placeholder="RSS 订阅地址">
      <div class="form-hint">支持标准 RSS 2.0 / Atom 格式</div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">剧名</label>
        <input class="form-input" id="sf_show" value="${escapeHtml(s.show_name || '')}" placeholder="如: 凡人修仙传">
      </div>
      <div class="form-group">
        <label class="form-label">季数</label>
        <input class="form-input" id="sf_season" type="number" value="${s.season || 0}" placeholder="0=不限">
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">起始集数</label>
        <input class="form-input" id="sf_ep_from" type="number" value="${s.episode_from || 0}" placeholder="0=不限" min="0">
        <div class="form-hint">只下载 ≥ 此集数的</div>
      </div>
      <div class="form-group">
        <label class="form-label">结束集数</label>
        <input class="form-input" id="sf_ep_to" type="number" value="${s.episode_to || 0}" placeholder="0=不限" min="0">
        <div class="form-hint">只下载 ≤ 此集数的</div>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">包含关键词</label>
      <input class="form-input" id="sf_kw" value="${(s.filter_keywords || []).join(', ')}" placeholder="多个用逗号分隔">
      <div class="form-hint">留空=不限制</div>
    </div>
    <div class="form-group">
      <label class="form-label">排除关键词</label>
      <input class="form-input" id="sf_exclude" value="${(s.filter_exclude || []).join(', ')}" placeholder="多个用逗号分隔">
    </div>
    <div class="form-group">
      <label class="form-label">描述</label>
      <input class="form-input" id="sf_desc" value="${escapeHtml(s.description || '')}" placeholder="备注说明">
    </div>
    <div class="checkbox-group">
      <label class="checkbox-label">
        <input type="checkbox" id="sf_enabled" ${s.enabled !== false ? 'checked' : ''}>
        启用
      </label>
      <label class="checkbox-label">
        <input type="checkbox" id="sf_auto" ${s.auto_episode ? 'checked' : ''}>
        自动跟进集数
      </label>
      <label class="checkbox-label">
        <input type="checkbox" id="sf_regex" ${s.regex_filter ? 'checked' : ''}>
        关键词用正则匹配
      </label>
    </div>
    ${edit ? '' : `<div class="form-group">
      <button class="btn btn-sm" onclick="testSourceUrl()">🔍 测试 RSS</button>
      <span id="testResult" style="font-size:0.82rem;margin-left:8px;color:var(--text-muted)"></span>
    </div>`}
  `;
}

function collectSourceForm() {
  const kws = $('#sf_kw').value.split(',').map(s => s.trim()).filter(Boolean);
  const exc = $('#sf_exclude').value.split(',').map(s => s.trim()).filter(Boolean);
  return {
    name: $('#sf_name').value.trim(),
    url: $('#sf_url').value.trim(),
    enabled: $('#sf_enabled').checked,
    show_name: $('#sf_show').value.trim(),
    season: parseInt($('#sf_season').value) || 0,
    episode_from: parseInt($('#sf_ep_from').value) || 0,
    episode_to: parseInt($('#sf_ep_to').value) || 0,
    filter_keywords: kws,
    filter_exclude: exc,
    episode_pattern: '',
    auto_episode: $('#sf_auto').checked,
    regex_filter: $('#sf_regex').checked,
    check_interval: 0,
    dedup_group: '',
    description: $('#sf_desc').value.trim(),
  };
}

async function testSourceUrl() {
  const url = $('#sf_url').value.trim();
  if (!url) { toast('请输入 RSS URL', 'warning'); return; }
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '测试中...';
  $('#testResult').textContent = '';
  try {
    const res = await api('POST', '/sources/test', { url });
    $('#testResult').textContent = `✅ 获取到 ${res.total} 条，前 ${Math.min(10, res.total)} 条已展示`;
    toast(`RSS 解析成功，共 ${res.total} 条`, 'success');
    // 显示前几条
    if (res.items && res.items.length) {
      const preview = res.items.map(i =>
        `<div style="padding:4px 0;font-size:0.82rem;border-bottom:1px solid var(--border)">${escapeHtml(i.title)}</div>`
      ).join('');
      $('#testResult').innerHTML += `<div class="card" style="margin-top:8px;max-height:200px;overflow:auto;font-size:0.82rem">${preview}</div>`;
    }
  } catch (e) {
    $('#testResult').textContent = `❌ ${escapeHtml(e.message)}`;
    toast('RSS 测试失败', 'error');
  }
  btn.disabled = false;
  btn.textContent = '🔍 测试 RSS';
}

async function showAddSource() {
  const s = emptySource();
  openModal('添加 RSS 源', sourceFormHtml(s), `
    <button class="btn btn-ghost" onclick="closeModal()">取消</button>
    <button class="btn btn-primary" onclick="confirmAddSource()">添加</button>
  `);
}

async function showTestSource(url) {
  try {
    const res = await api('POST', '/sources/test', { url });
    openModal('RSS 测试结果', `
      <div style="margin-bottom:12px">共 <strong>${res.total}</strong> 条</div>
      ${res.items.map(i =>
        `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:0.85rem">
          <div style="font-weight:500">${escapeHtml(i.title)}</div>
          <div style="font-size:0.75rem;color:var(--text-muted)">${escapeHtml(i.link)}</div>
        </div>`
      ).join('') || '<div class="empty-state-desc">无条目</div>'}
    `, `<button class="btn btn-ghost" onclick="closeModal()">关闭</button>`);
  } catch (e) {
    toast('RSS 测试失败: ' + e.message, 'error');
  }
}

async function confirmAddSource() {
  const data = collectSourceForm();
  if (!data.name) { toast('请输入源名称', 'warning'); return; }
  if (!data.url) { toast('请输入 RSS URL', 'warning'); return; }
  try {
    await api('POST', '/sources', data);
    toast('源已添加', 'success');
    closeModal();
    pages.sources();
  } catch (e) {
    toast('添加失败: ' + e.message, 'error');
  }
}

async function showEditSource(name) {
  try {
    const sources = await api('GET', '/sources');
    const s = sources.find(x => x.name === name);
    if (!s) { toast('源不存在', 'error'); return; }
    openModal(`编辑源: ${escapeHtml(name)}`, sourceFormHtml(s, true), `
      <button class="btn btn-ghost" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" onclick="confirmEditSource('${escapeHtml(name)}')">保存</button>
    `);
  } catch (e) {
    toast('加载失败: ' + e.message, 'error');
  }
}

async function confirmEditSource(origName) {
  const data = collectSourceForm();
  if (!data.name) { toast('请输入源名称', 'warning'); return; }
  try {
    await api('PUT', `/sources/${encodeURIComponent(origName)}`, data);
    toast('源已更新', 'success');
    closeModal();
    pages.sources();
  } catch (e) {
    toast('更新失败: ' + e.message, 'error');
  }
}

async function toggleSource(name, enable) {
  try {
    await api('PUT', `/sources/${encodeURIComponent(name)}`, { enabled: enable });
    toast(enable ? '已启用' : '已禁用', 'success');
    pages.sources();
  } catch (e) {
    toast('操作失败: ' + e.message, 'error');
  }
}

async function deleteSource(name) {
  if (!confirm(`确定删除 "${name}"？`)) return;
  try {
    await api('DELETE', `/sources/${encodeURIComponent(name)}`);
    toast('已删除', 'success');
    pages.sources();
  } catch (e) {
    toast('删除失败: ' + e.message, 'error');
  }
}

// ── Page: Tasks ──
let taskPage = 1;
let taskStatus = '';
let taskSource = '';

pages.tasks = async function() {
  const c = $('#content');
  c.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⏳</div><div>加载中...</div></div>';

  try {
    const [tasks, stats, sources] = await Promise.all([
      api('GET', `/tasks?page=${taskPage}&page_size=30&status=${taskStatus}&source=${taskSource}`),
      api('GET', '/tasks/stats'),
      api('GET', '/sources'),
    ]);

    const statusCss = {
      '等待提交': 'pending', '已提交': 'submitted', '失败': 'failed', '已完成': 'done',
    };

    c.innerHTML = `
      <div class="section">
        <div class="card-header">
          <span class="section-title" style="margin:0">📥 离线任务 (${tasks.total})</span>
        </div>
        <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
          <select class="form-select" id="taskStatusFilter" style="width:auto;min-width:120px">
            <option value="">全部状态</option>
            <option value="等待提交" ${taskStatus === '等待提交' ? 'selected' : ''}>等待提交</option>
            <option value="已提交" ${taskStatus === '已提交' ? 'selected' : ''}>已提交</option>
            <option value="失败" ${taskStatus === '失败' ? 'selected' : ''}>失败</option>
            <option value="已完成" ${taskStatus === '已完成' ? 'selected' : ''}>已完成</option>
          </select>
          <select class="form-select" id="taskSourceFilter" style="width:auto;min-width:150px">
            <option value="">全部源</option>
            ${sources.map(s =>
              `<option value="${escapeHtml(s.name)}" ${taskSource === s.name ? 'selected' : ''}>${escapeHtml(s.name)}</option>`
            ).join('')}
          </select>
        </div>
        <div class="card" style="padding:0">
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>标题</th>
                <th>源</th>
                <th>状态</th>
                <th>重试</th>
                <th>时间</th>
              </tr></thead>
              <tbody>
                ${tasks.items.map(t => `
                  <tr>
                    <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis" title="${escapeHtml(t.title)}">${escapeHtml(t.title)}</td>
                    <td><span class="tag" style="background:var(--bg-hover)">${escapeHtml(t.source_name)}</span></td>
                    <td><span class="tag tag-${statusCss[t.status] || 'pending'}">${t.status}</span></td>
                    <td>${t.retry_count || 0}</td>
                    <td style="font-size:0.8rem;color:var(--text-secondary)">${formatDate(t.created_at)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
          ${tasks.total > tasks.page_size ? `
            <div class="pagination">
              <button class="btn btn-sm btn-ghost" ${taskPage <= 1 ? 'disabled' : ''} onclick="changeTaskPage(${taskPage - 1})">←</button>
              <span class="page-info">第 ${taskPage} / ${Math.ceil(tasks.total / tasks.page_size)} 页 (共 ${tasks.total})</span>
              <button class="btn btn-sm btn-ghost" ${taskPage * tasks.page_size >= tasks.total ? 'disabled' : ''} onclick="changeTaskPage(${taskPage + 1})">→</button>
            </div>
          ` : ''}
        </div>
      </div>
    `;

    $('#taskStatusFilter').onchange = function() {
      taskStatus = this.value;
      taskPage = 1;
      pages.tasks();
    };
    $('#taskSourceFilter').onchange = function() {
      taskSource = this.value;
      taskPage = 1;
      pages.tasks();
    };
  } catch (e) {
    c.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div>${escapeHtml(e.message)}</div></div>`;
  }
};

function changeTaskPage(p) {
  taskPage = p;
  pages.tasks();
}

// ── Page: Retry Queue ──
pages.retry = async function() {
  const c = $('#content');
  c.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⏳</div><div>加载中...</div></div>';

  try {
    const retries = await api('GET', '/retry');

    c.innerHTML = `
      <div class="section">
        <div class="card-header">
          <span class="section-title" style="margin:0">🔄 重试队列 (${retries.length})</span>
        </div>
        ${retries.length === 0 ? `
          <div class="empty-state">
            <div class="empty-state-icon">✅</div>
            <div class="empty-state-title">队列为空</div>
            <div class="empty-state-desc">当前没有需要重试的离线任务</div>
          </div>
        ` : `
        <div class="card" style="padding:0">
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>标题</th>
                <th>源</th>
                <th>重试次数</th>
                <th>下次重试</th>
                <th>状态</th>
              </tr></thead>
              <tbody>
                ${retries.map(t => `
                  <tr>
                    <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis">${escapeHtml(t.title)}</td>
                    <td>${escapeHtml(t.source_name)}</td>
                    <td>${t.r_count || 0} / ${t.max_retries || 5}</td>
                    <td style="font-size:0.8rem;color:var(--text-secondary)">${formatDate(t.retry_after)}</td>
                    <td><span class="tag tag-pending">等待重试</span></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
        `}
      </div>
    `;
  } catch (e) {
    c.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div>${escapeHtml(e.message)}</div></div>`;
  }
};

// ── Page: History ──
let historyPage = 1;

pages.history = async function() {
  const c = $('#content');
  c.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⏳</div><div>加载中...</div></div>';

  try {
    const h = await api('GET', `/history?page=${historyPage}&page_size=50`);

    c.innerHTML = `
      <div class="section">
        <div class="card-header">
          <span class="section-title" style="margin:0">📋 操作日志 (${h.total})</span>
        </div>
        <div class="card" style="padding:0">
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>时间</th>
                <th>事件</th>
                <th>详情</th>
              </tr></thead>
              <tbody>
                ${h.items.map(i => `
                  <tr>
                    <td style="font-size:0.8rem;color:var(--text-secondary);white-space:nowrap">${formatDate(i.created_at)}</td>
                    <td><span class="tag" style="background:var(--bg-hover)">${escapeHtml(i.event)}</span></td>
                    <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis">${escapeHtml(i.detail || '')}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
          ${h.total > h.page_size ? `
            <div class="pagination">
              <button class="btn btn-sm btn-ghost" ${historyPage <= 1 ? 'disabled' : ''} onclick="changeHistoryPage(${historyPage - 1})">←</button>
              <span class="page-info">第 ${historyPage} / ${Math.ceil(h.total / h.page_size)} 页</span>
              <button class="btn btn-sm btn-ghost" ${historyPage * h.page_size >= h.total ? 'disabled' : ''} onclick="changeHistoryPage(${historyPage + 1})">→</button>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  } catch (e) {
    c.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div>${escapeHtml(e.message)}</div></div>`;
  }
};

function changeHistoryPage(p) {
  historyPage = p;
  pages.history();
}

// ── Page: Settings ──
pages.settings = async function() {
  const c = $('#content');

  try {
    const [cfg, sched, conn] = await Promise.all([
      api('GET', '/global'),
      api('GET', '/scheduler/status'),
      api('GET', '/115/status'),
    ]);
    // 单独获取完整 cookie（/global 返回的是截断版，用于编辑必须走 /cookie）
    let fullCookie = '';
    try {
      const cr = await api('GET', '/cookie');
      fullCookie = cr.cookie_115 || '';
    } catch { /* fallback */ }

    c.innerHTML = `
      <div class="section">
        <div class="section-title">⚙️ 基本设置</div>
        <div class="card">
          <div class="form-group">
            <label class="form-label">115 Cookie</label>
            <textarea class="form-textarea" id="set_cookie" rows="3"
              placeholder="UID=...; CID=...; SEID=...; KID=...">${escapeHtml(fullCookie)}</textarea>
            <button class="btn btn-sm" onclick="saveCookie()" style="margin-top:8px">💾 保存 Cookie</button>
            <span id="cookieStatus" style="margin-left:8px;font-size:0.82rem"></span>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">保存目录名</label>
              <input class="form-input" id="set_dir" value="${escapeHtml(cfg.save_dir_name || '/追剧')}">
            </div>
            <div class="form-group">
              <label class="form-label">RSS 检查间隔（分钟）</label>
              <input class="form-input" id="set_interval" type="number" value="${cfg.check_interval || 30}" min="1">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">最大重试次数</label>
              <input class="form-input" id="set_retries" type="number" value="${cfg.max_retries || 5}" min="0">
            </div>
            <div class="form-group">
              <label class="form-label">历史保留天数</label>
              <input class="form-input" id="set_keep" type="number" value="${cfg.history_keep_days || 60}" min="1">
            </div>
          </div>
          <button class="btn btn-primary" onclick="saveSettings()">💾 保存设置</button>
          <span id="settingsStatus" style="margin-left:8px;font-size:0.82rem"></span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">🔔 通知设置</div>
        <div class="card">
          <div class="form-group">
            <label class="form-label">Telegram Bot Token</label>
            <input class="form-input" id="set_telegram_token" type="password"
              placeholder="123456:ABC-def_ghI" value="${escapeHtml(cfg.telegram_bot_token || '')}">
          </div>
          <div class="form-group">
            <label class="form-label">Telegram Chat ID</label>
            <input class="form-input" id="set_telegram_chat" type="text"
              placeholder="123456789 或 @username" value="${escapeHtml(cfg.telegram_chat_id || '')}">
          </div>
          <div class="form-row" style="margin-bottom:12px">
            <label class="checkbox-label">
              <input type="checkbox" id="set_notify_success"
                ${cfg.notify_on_success !== false ? 'checked' : ''}>
              离线任务成功时通知
            </label>
            <label class="checkbox-label">
              <input type="checkbox" id="set_notify_failure"
                ${cfg.notify_on_failure !== false ? 'checked' : ''}>
              离线任务失败时通知
            </label>
            <label class="checkbox-label">
              <input type="checkbox" id="set_notify_rss"
                ${cfg.notify_on_rss_failure !== false ? 'checked' : ''}>
              RSS 源失效时通知
            </label>
          </div>
          <div class="form-group">
            <label class="form-label">TMDB API Key <span class="text-muted" style="font-size:0.75rem">（可选，无封面图时自动搜索）</span></label>
            <input class="form-input" id="set_tmdb_key" type="password"
              placeholder="https://www.themoviedb.org/settings/api" value="${escapeHtml(cfg.tmdb_api_key || '')}">
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <button class="btn btn-primary btn-sm" onclick="saveNotification()">💾 保存通知设置</button>
            <button class="btn btn-sm" onclick="testNotification()">📤 发送测试通知</button>
            <span id="notifyStatus" style="font-size:0.82rem;color:var(--text-muted)"></span>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">🔄 调度控制</div>
        <div class="card" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <span>调度器: <span class="tag ${sched.running ? 'tag-done' : 'tag-failed'}">${sched.running ? '运行中' : '已停止'}</span></span>
          <button class="btn btn-sm" onclick="runCheckNow(this)">🔄 立即检查</button>
          <span id="checkStatus" style="font-size:0.82rem;color:var(--text-muted)"></span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">💾 数据管理</div>
        <div class="card" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <button class="btn btn-sm" onclick="doBackup()">📦 备份数据</button>
          <button class="btn btn-sm" onclick="showRestore()">📂 恢复数据</button>
          <button class="btn btn-sm" onclick="showVacuum()">🧹 清理数据</button>
          <span id="dataStatus" style="font-size:0.82rem;color:var(--text-muted)"></span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">📊 115 状态</div>
        <div class="card">
          ${conn.connected ? `
            <table>
              <tr><td>连接状态</td><td><span class="tag tag-done">已连接</span></td></tr>
              ${conn.quota && conn.quota.ok ? `
                <tr><td>剩余配额</td><td>${conn.quota.data.quota || 0}</td></tr>
                <tr><td>总配额</td><td>${conn.quota.data.total_quota || '-'}</td></tr>
              ` : ''}
            </table>
          ` : `
            <div class="empty-state-desc">${conn.message || '未连接，请先配置 115 Cookie'}</div>
          `}
        </div>
      </div>

      <div class="section">
        <div class="section-title">ℹ️ 关于</div>
        <div class="card" style="font-size:0.85rem;color:var(--text-secondary)">
          <p>Zhui115 v1.0 — 基于 p115client 的自动追剧离线下载工具</p>
          <p style="margin-top:4px">定时检查 RSS 源，自动提交磁力/ED2K 链接到 115 网盘离线下载</p>
        </div>
      </div>
    `;

    updateSidebarStatus(conn, sched);
  } catch (e) {
    c.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div>${escapeHtml(e.message)}</div></div>`;
  }
};

async function saveCookie() {
  const cookie = $('#set_cookie').value.trim();
  if (!cookie) { toast('请输入 Cookie', 'warning'); return; }
  try {
    await api('PUT', '/cookie', { cookie_115: cookie });
    $('#cookieStatus').textContent = '✅ 已保存';
    toast('Cookie 已保存', 'success');
  } catch (e) {
    $('#cookieStatus').textContent = '❌ ' + e.message;
    toast('保存失败', 'error');
  }
}

async function saveSettings() {
  try {
    await api('PUT', '/global', {
      save_dir_name: $('#set_dir').value.trim(),
      check_interval: parseInt($('#set_interval').value) || 30,
      max_retries: parseInt($('#set_retries').value) || 5,
      history_keep_days: parseInt($('#set_keep').value) || 60,
    });
    $('#settingsStatus').textContent = '✅ 已保存（间隔已生效）';
    toast('设置已保存', 'success');
  } catch (e) {
    $('#settingsStatus').textContent = '❌ ' + e.message;
    toast('保存失败', 'error');
  }
}

async function saveNotification() {
  try {
    await api('PUT', '/global', {
      telegram_bot_token: $('#set_telegram_token').value.trim(),
      telegram_chat_id: $('#set_telegram_chat').value.trim(),
      notify_on_success: $('#set_notify_success').checked,
      notify_on_failure: $('#set_notify_failure').checked,
      notify_on_rss_failure: $('#set_notify_rss').checked,
      tmdb_api_key: $('#set_tmdb_key').value.trim(),
    });
    $('#notifyStatus').textContent = '✅ 已保存';
    toast('通知设置已保存', 'success');
  } catch (e) {
    $('#notifyStatus').textContent = '❌ ' + e.message;
    toast('保存失败', 'error');
  }
}

async function testNotification() {
  const token = $('#set_telegram_token').value.trim();
  const chatId = $('#set_telegram_chat').value.trim();
  if (!token || !chatId) {
    toast('请先填写 Bot Token 和 Chat ID', 'warning');
    return;
  }
  $('#notifyStatus').textContent = '⏳ 发送中...';
  try {
    const res = await api('POST', '/notify/test', {
      telegram_bot_token: token,
      telegram_chat_id: chatId,
    });
    $('#notifyStatus').textContent = '✅ ' + (res.message || '已发送');
    toast('测试通知已发送', 'success');
  } catch (e) {
    $('#notifyStatus').textContent = '❌ ' + e.message;
    toast('测试发送失败: ' + e.message, 'error');
  }
}

async function runCheckNow(btn) {
  if (btn) btn.disabled = true;
  $('#checkStatus').textContent = '检查中...';
  try {
    const res = await api('POST', '/scheduler/run-now');
    $('#checkStatus').textContent = '✅ ' + (res.message || '已触发');
    toast('已触发检查', 'success');
  } catch (e) {
    $('#checkStatus').textContent = '❌ ' + e.message;
    toast('触发失败: ' + e.message, 'error');
  }
  if (btn) btn.disabled = false;
}

async function doBackup() {
  $('#dataStatus').textContent = '备份中...';
  try {
    // 触发文件下载，浏览器弹出"另存为"对话框
    const a = document.createElement('a');
    a.href = API_BASE + '/data/backup';
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    $('#dataStatus').textContent = '✅ 备份文件已下载';
    toast('备份文件已下载', 'success');
  } catch (e) {
    $('#dataStatus').textContent = '❌ ' + e.message;
    toast('备份失败', 'error');
  }
}

async function showRestore() {
  try {
    const backups = await api('GET', '/data/backups');
    if (!backups.length) {
      toast('没有备份文件', 'warning');
      return;
    }
    const list = backups.map(b =>
      `<div style="padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;justify-content:space-between"
            onclick="doRestore('${b.name}')">
        <span>📦 ${escapeHtml(b.name)}</span>
        <span style="color:var(--text-muted);font-size:0.82rem">${(b.size / 1024).toFixed(1)} KB · ${formatDate(b.mtime)}</span>
      </div>`
    ).join('');
    openModal('恢复数据', `
      <p style="margin-bottom:12px;color:var(--text-secondary);font-size:0.85rem">
        点击备份文件恢复数据（当前数据将被覆盖）
      </p>
      ${list}
    `, `<button class="btn btn-ghost" onclick="closeModal()">取消</button>`);
  } catch (e) {
    toast('加载备份列表失败: ' + e.message, 'error');
  }
}

async function doRestore(name) {
  if (!confirm(`确定从 "${name}" 恢复？当前数据将被覆盖！`)) return;
  closeModal();
  try {
    await api('POST', '/data/restore', { name });
    toast('恢复成功，请刷新页面', 'success');
  } catch (e) {
    toast('恢复失败: ' + e.message, 'error');
  }
}

function showVacuum() {
  openModal('数据清理', `
    <div class="form-group">
      <label class="form-label">保留天数</label>
      <input class="form-input" id="vacuum_days" type="number" value="60" min="1">
      <div class="form-hint">将删除超过此天数的历史记录和剧集记录</div>
    </div>
  `, `
    <button class="btn btn-ghost" onclick="closeModal()">取消</button>
    <button class="btn btn-danger" onclick="doVacuum()">执行清理</button>
  `);
}

async function doVacuum() {
  const days = parseInt($('#vacuum_days').value) || 60;
  closeModal();
  $('#dataStatus').textContent = '清理中...';
  try {
    await api('POST', '/data/vacuum', { keep_days: days });
    $('#dataStatus').textContent = `✅ 清理完成（保留${days}天）`;
    toast('清理完成', 'success');
  } catch (e) {
    $('#dataStatus').textContent = '❌ ' + e.message;
    toast('清理失败', 'error');
  }
}

// ── Init ──
window.addEventListener('DOMContentLoaded', () => {
  // 路由
  const hash = location.hash.slice(1) || 'dashboard';
  navigate(hash);
  window.addEventListener('hashchange', () => {
    const p = location.hash.slice(1) || 'dashboard';
    navigate(p);
  });
});

// 暴露到全局供 onclick 使用
window.showAddSource = showAddSource;
window.showTestSource = showTestSource;
window.showEditSource = showEditSource;
window.confirmAddSource = confirmAddSource;
window.confirmEditSource = confirmEditSource;
window.toggleSource = toggleSource;
window.deleteSource = deleteSource;
window.changeTaskPage = changeTaskPage;
window.changeHistoryPage = changeHistoryPage;
window.saveCookie = saveCookie;
window.saveSettings = saveSettings;
window.saveNotification = saveNotification;
window.testNotification = testNotification;
window.runCheckNow = runCheckNow;
window.doBackup = doBackup;
window.showRestore = showRestore;
window.doRestore = doRestore;
window.showVacuum = showVacuum;
window.doVacuum = doVacuum;
window.closeModal = closeModal;
window.testSourceUrl = testSourceUrl;
