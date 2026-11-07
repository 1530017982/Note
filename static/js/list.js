// list.js —— 6号：列表渲染、筛选、删除
// 导入 dashboard 的 refreshDashboard，不重复写统计逻辑
// 维护唯一筛选状态；初次加载、筛选/重置、records-changed 事件时同时刷新列表与看板
// 列表加载全部匹配记录，limit 仅传给列表，不传给统计
// 切换筛选过快时通过请求序号防止旧响应覆盖新结果

import { fetchJSON } from './api.js';
import { refreshDashboard } from './dashboard.js';

const state = { filters: {} };
let reqId = 0;

function yuan(cents) {
  return ((Number(cents) || 0) / 100).toFixed(2);
}

// 保留原生日期选择器，用中文覆盖浏览器自带的空日期占位文字。
function createDateFilter(id, label) {
  const wrapper = document.createElement('div');
  wrapper.className = 'date-filter is-empty';
  const input = document.createElement('input');
  input.type = 'date'; input.id = id;
  input.className = 'filter-input filter-date-input';
  input.setAttribute('aria-label', label);
  const placeholder = document.createElement('span');
  placeholder.className = 'date-filter-placeholder';
  placeholder.textContent = '年/月/日';
  placeholder.setAttribute('aria-hidden', 'true');
  const syncPlaceholder = () => wrapper.classList.toggle('is-empty', !input.value);
  input.addEventListener('input', syncPlaceholder);
  input.addEventListener('change', syncPlaceholder);
  wrapper.append(input, placeholder);
  return { wrapper, input, syncPlaceholder };
}

// ---------- 筛选控件注入 #filter-panel ----------
function buildFilterPanel() {
  const panel = document.getElementById('filter-panel');
  if (!panel || panel.dataset.bound) return;
  panel.dataset.bound = '1';

  const startDate = createDateFilter('f-start', '开始日期');
  const endDate = createDateFilter('f-end', '结束日期');
  const typeSelect = document.createElement('select');
  typeSelect.id = 'f-type'; typeSelect.className = 'filter-input';
  typeSelect.innerHTML = '<option value="">全部</option><option value="income">收入</option><option value="expense">支出</option>';
  const catInput = document.createElement('input');
  catInput.type = 'text'; catInput.id = 'f-cat'; catInput.className = 'filter-input'; catInput.placeholder = '类别';

  // 最低 / 最高金额（单位元，提交时转分）
  const minInput = document.createElement('input');
  minInput.type = 'text'; minInput.inputMode = 'decimal'; minInput.id = 'f-min'; minInput.className = 'filter-input';
  minInput.placeholder = '最低金额(元)';
  const maxInput = document.createElement('input');
  maxInput.type = 'text'; maxInput.inputMode = 'decimal'; maxInput.id = 'f-max'; maxInput.className = 'filter-input';
  maxInput.placeholder = '最高金额(元)';

  const applyBtn = document.createElement('button');
  applyBtn.type = 'button'; applyBtn.id = 'f-apply'; applyBtn.className = 'btn btn-primary'; applyBtn.textContent = '筛选';
  const resetBtn = document.createElement('button');
  resetBtn.type = 'button'; resetBtn.id = 'f-reset'; resetBtn.className = 'btn btn-ghost'; resetBtn.textContent = '重置';

  const grid1 = document.createElement('div'); grid1.className = 'filter-grid';
  grid1.append(startDate.wrapper, endDate.wrapper, typeSelect, catInput);
  const grid2 = document.createElement('div'); grid2.className = 'filter-grid';
  grid2.append(minInput, maxInput, applyBtn, resetBtn);
  panel.append(grid1, grid2);

  applyBtn.addEventListener('click', () => {
    let filters;
    try {
      filters = readFilters();
    } catch (error) {
      const message = document.getElementById('list-message');
      if (message) {
        message.textContent = error.message;
        message.className = 'message error';
      }
      return; // 保留上次有效筛选，不发送错误请求
    }
    state.filters = filters;
    refreshAll();
  });

  resetBtn.addEventListener('click', () => {
    state.filters = {};
    ['f-start','f-end','f-type','f-cat','f-min','f-max'].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = '';
    });
    startDate.syncPlaceholder();
    endDate.syncPlaceholder();
    refreshAll();
  });
}

// 通过拼接整数位与小数位精确换算为分，不舍入、不做浮点乘法。
function parseFilterAmount(raw, label) {
  const text = String(raw ?? '').trim();
  if (text === '') return null;
  if (!/^[0-9]+(?:\.[0-9]{1,2})?$/.test(text)) {
    throw new Error(label + '须为非负金额，最多两位小数，例如 12.50');
  }
  const [whole, fraction = ''] = text.split('.');
  const digits = (whole + fraction.padEnd(2, '0')).replace(/^0+/, '') || '0';
  if (digits.length > 9 || Number(digits) > 999999999) {
    throw new Error(label + '须在 0 到 9,999,999.99 元之间');
  }
  return digits;
}

function readFilters() {
  const f = {};
  const v = id => document.getElementById(id)?.value?.trim();
  const s = v('f-start'); if (s) f.start_date = s;
  const e = v('f-end');   if (e) f.end_date = e;
  const t = v('f-type');  if (t) f.type = t;
  const c = v('f-cat');   if (c) f.category = c;
  // 筛选金额允许0；非空值精确换算为整数分。
  const minimum = parseFilterAmount(v('f-min'), '最低金额');
  const maximum = parseFilterAmount(v('f-max'), '最高金额');
  if (minimum !== null) f.min_amount = minimum;
  if (maximum !== null) f.max_amount = maximum;
  if (minimum !== null && maximum !== null && Number(minimum) > Number(maximum)) {
    throw new Error('最高金额不能小于最低金额');
  }
  return f;
}

// ---------- 列表加载与渲染 ----------
async function loadRecords() {
  const myId = ++reqId;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(state.filters)) if (v) params.append(k, v);
  // limit 单独给列表，不进统计
  params.append('limit', 'all');

  const listMsg = document.getElementById('list-message');
  if (listMsg) { listMsg.textContent = '加载中…'; listMsg.className = 'message'; }

  try {
    const json = await fetchJSON(`/api/records?${params.toString()}`);
    if (myId !== reqId) return;
    const records = (json && json.data) ? json.data : [];
    renderList(records);
    if (listMsg) { listMsg.textContent = ''; listMsg.className = 'message'; }
  } catch (err) {
    if (myId !== reqId) return;
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

    // 备注用 textContent，不拼 innerHTML
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
    // 闭包绑定，不拼 onclick，UUID 无引号问题
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
      // 6号删除成功触发 records-changed，action=deleted，保持当前筛选
      document.dispatchEvent(new CustomEvent('records-changed', { detail: { action: 'deleted', id } }));
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
  refreshDashboard(state.filters); // 统计不带 limit
}

// 监听 records-changed（5号新增 / 6号删除 均触发，只触发一次刷新）
document.addEventListener('records-changed', refreshAll);

// ---------- 初始化 ----------
window.addEventListener('DOMContentLoaded', () => {
  buildFilterPanel();

  refreshAll();
});
