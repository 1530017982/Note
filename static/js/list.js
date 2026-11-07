// list.js —— 6号：列表渲染、筛选、删除
// 导入 dashboard 的 refreshDashboard，不重复写统计逻辑
// 筛选状态唯一维护，事件只触发一次刷新
// 切换筛选过快时通过请求序号防止旧响应覆盖新结果

import { refreshDashboard } from './dashboard.js';

const state = { filters: {}, listLimit: 10 };
let listReqId = 0;

function yuan(cents) {
  return ((Number(cents) || 0) / 100).toFixed(2);
}

// ---------- 筛选控件注入 #filter-panel ----------
function buildFilterPanel() {
  const panel = document.getElementById('filter-panel');
  if (!panel || panel.dataset.bound) return;
  panel.dataset.bound = '1';

  const startInput = document.createElement('input');
  startInput.type = 'date';
  startInput.id = 'f-start';
  startInput.className = 'filter-input';

  const endInput = document.createElement('input');
  endInput.type = 'date';
  endInput.id = 'f-end';
  endInput.className = 'filter-input';

  const typeSelect = document.createElement('select');
  typeSelect.id = 'f-type';
  typeSelect.className = 'filter-input';
  typeSelect.innerHTML = '<option value="">全部</option><option value="income">收入</option><option value="expense">支出</option>';

  const catInput = document.createElement('input');
  catInput.type = 'text';
  catInput.id = 'f-cat';
  catInput.className = 'filter-input';
  catInput.placeholder = '类别';

  const applyBtn = document.createElement('button');
  applyBtn.type = 'button';
  applyBtn.id = 'f-apply';
  applyBtn.className = 'btn btn-primary';
  applyBtn.textContent = '筛选';

  const resetBtn = document.createElement('button');
  resetBtn.type = 'button';
  resetBtn.id = 'f-reset';
  resetBtn.className = 'btn btn-ghost';
  resetBtn.textContent = '重置';

  const grid = document.createElement('div');
  grid.className = 'filter-grid';
  grid.append(startInput, endInput, typeSelect, catInput, applyBtn, resetBtn);
  panel.appendChild(grid);

  applyBtn.addEventListener('click', () => {
    state.filters = readFilters();
    refreshAll();
  });

  resetBtn.addEventListener('click', () => {
    state.filters = {};
    ['f-start', 'f-end', 'f-type', 'f-cat'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    refreshAll();
  });
}

function readFilters() {
  const f = {};
  const v = id => document.getElementById(id)?.value?.trim();
  const s = v('f-start'); if (s) f.start_date = s;
  const e = v('f-end');   if (e) f.end_date = e;
  const t = v('f-type');  if (t) f.type = t;
  const c = v('f-cat');   if (c) f.category = c;
  return f;
}

// ---------- 列表加载与渲染 ----------
async function loadRecords() {
  const myId = ++listReqId;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(state.filters)) if (v) params.append(k, v);
  params.append('limit', String(state.listLimit));

  const listMsg = document.getElementById('list-message');
  if (listMsg) { listMsg.textContent = '加载中…'; listMsg.className = 'message'; }

  try {
    const res = await fetch(`/api/records?${params.toString()}`);
    if (myId !== listReqId) return;
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `LIST_${res.status}`);
    }
    const json = await res.json();
    if (myId !== listReqId) return;
    const records = (json && json.data) ? json.data : [];
    renderList(records);
    if (listMsg) { listMsg.textContent = ''; listMsg.className = 'message'; }
  } catch (err) {
    if (myId !== listReqId) return;
    console.warn(err);
    if (listMsg) { listMsg.textContent = err.message || '账单加载失败，请核对后重试'; listMsg.className = 'message error'; }
  }
}

function renderList(records) {
  const host = document.getElementById('record-list');
  if (!host) return;
  host.replaceChildren();

  if (!records.length) {
    const p = document.createElement('p');
    p.className = 'empty-tip';
    p.textContent = '暂无符合条件的账单';
    host.appendChild(p);
    return;
  }

  const ul = document.createElement('ul');
  ul.className = 'record-list';

  records.forEach(r => {
    const li = document.createElement('li');
    li.className = 'record-item';

    const info = document.createElement('div');
    info.className = 'record-info';

    const dateSpan = document.createElement('span');
    dateSpan.className = 'record-date';
    dateSpan.textContent = r.date;

    const catSpan = document.createElement('span');
    catSpan.className = 'record-cat';
    catSpan.textContent = r.category;

    info.appendChild(dateSpan);
    info.appendChild(catSpan);

    if (r.note) {
      const noteSpan = document.createElement('span');
      noteSpan.className = 'record-note';
      noteSpan.textContent = r.note;
      info.appendChild(noteSpan);
    }

    const right = document.createElement('div');
    right.className = 'record-amount-box';

    const amt = document.createElement('span');
    amt.className = `record-amount ${r.type}`;
    amt.textContent = (r.type === 'income' ? '+' : '-') + yuan(r.amount);

    const delBtn = document.createElement('button');
    delBtn.className = 'del-btn';
    delBtn.type = 'button';
    delBtn.textContent = '删除';
    delBtn.addEventListener('click', () => deleteRecord(r.id));

    right.appendChild(amt);
    right.appendChild(delBtn);

    li.appendChild(info);
    li.appendChild(right);
    ul.appendChild(li);
  });

  host.appendChild(ul);
}

// ---------- 删除 ----------
async function deleteRecord(id) {
  if (!confirm('确定删除这条记录？')) return;
  try {
    const res = await fetch(`/api/records/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (res.ok) {
      document.dispatchEvent(new CustomEvent('records-changed', {
        detail: { action: 'deleted', id }
      }));
    } else if (res.status === 404) {
      alert('该记录已不存在');
      refreshAll();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.error || '删除失败');
    }
  } catch {
    alert('网络错误，删除失败');
  }
}

// ---------- 统一刷新 ----------
function refreshAll() {
  loadRecords();
  refreshDashboard(state.filters);
}

// 监听 records-changed（5号新增成功也会触发）
document.addEventListener('records-changed', refreshAll);

// 初始化
window.addEventListener('DOMContentLoaded', () => {
  buildFilterPanel();
  refreshAll();
});