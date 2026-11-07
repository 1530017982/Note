// dashboard.js —— 6号：统计看板 + 图表
// 导出 refreshDashboard(filters)，由 list.js 调用
// 刷新由 list.js 统一发起，本模块不自行初始化请求或绑定事件
// filters：六键可选筛选（start_date/end_date/type/category/min_amount/max_amount），缺失/空值不发送
// 金额为整数分；列表的 limit 不传给统计

import { fetchJSON } from './api.js';

let catChartInst = null;
let monChartInst = null;
let reqId = 0;

function yuan(cents) {
  return ((Number(cents) || 0) / 100).toFixed(2);
}

function destroyCharts() {
  // 重绘前释放旧实例，避免同一画布重复绑定图表。
  try { catChartInst?.destroy(); catChartInst = null; } catch {}
  try { monChartInst?.destroy(); monChartInst = null; } catch {}
}

export async function refreshDashboard(filters = {}) {
  const myId = ++reqId;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== '' && v != null) params.append(k, v);
  }

  const statsPanel = document.getElementById('stats-panel');
  const statsMsg = document.getElementById('stats-message');

  try {
    const data = await fetchJSON(`/api/stats?${params.toString()}`);
    if (myId !== reqId) return; // 旧请求丢弃，防过快切换覆盖

    const d = data.data || {}; // 统一接口将统计对象放在 data 字段中。
    const income = d.income || 0;
    const expense = d.expense || 0;
    const balance = d.balance ?? (income - expense);

    // KPI 写入 stats-panel
    if (statsPanel) {
      statsPanel.innerHTML = '';
      const wrap = document.createElement('div');
      wrap.className = 'kpi-card-wrapper';
      wrap.innerHTML = `
        <div class="kpi income"><span>总收入</span><strong>${yuan(income)}</strong></div>
        <div class="kpi expense"><span>总支出</span><strong>${yuan(expense)}</strong></div>
        <div class="kpi balance"><span>结余</span><strong>${yuan(balance)}</strong></div>
      `;
      statsPanel.appendChild(wrap);
    }

    if (statsMsg) { statsMsg.textContent = ''; statsMsg.className = 'message'; }

    // 图表：按后端返回 data.by_category / data.by_month
    renderCategoryChart(d.by_category || []);
    renderMonthlyChart(d.by_month || []);

  } catch (err) {
    if (myId !== reqId) return;
    console.warn('统计加载失败', err);
    if (statsMsg) {
      statsMsg.textContent = err.message || '统计加载失败，请核对后重试';
      statsMsg.className = 'message error';
    }
  }
}

function renderCategoryChart(byCategory) {
  const canvas = document.getElementById('category-chart');
  if (!canvas) return;
  destroyCharts();

  const labels = byCategory.map(i => i.category || '未分类');
  const data = byCategory.map(i => (Number(i.expense) || 0) / 100); // 图表展示元。

  if (!labels.length || data.every(v => v === 0)) {
    canvas.style.display = 'none';
    const box = canvas.parentElement;
    if (box && !box.querySelector('.chart-empty')) {
      const tip = document.createElement('p');
      tip.className = 'empty-tip chart-empty';
      tip.textContent = '暂无分类支出数据';
      box.appendChild(tip);
    }
    return;
  }

  const empty = canvas.parentElement?.querySelector('.chart-empty');
  if (empty) empty.remove();
  canvas.style.display = '';

  catChartInst = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data, backgroundColor: ['#ef4444','#f59e0b','#10b981','#6366f1','#8b5cf6','#ec4899','#14b8a6'] }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { title: { display: true, text: '分类支出占比' } }
    }
  });
}

function renderMonthlyChart(byMonth) {
  const canvas = document.getElementById('monthly-chart');
  if (!canvas) return;

  const labels = byMonth.map(i => i.month || '');
  const inc = byMonth.map(i => (Number(i.income) || 0) / 100);
  const exp = byMonth.map(i => (Number(i.expense) || 0) / 100);

  if (!labels.length) {
    canvas.style.display = 'none';
    const box = canvas.parentElement;
    if (box && !box.querySelector('.chart-empty')) {
      const tip = document.createElement('p');
      tip.className = 'empty-tip chart-empty';
      tip.textContent = '暂无月度数据';
      box.appendChild(tip);
    }
    return;
  }

  const empty = canvas.parentElement?.querySelector('.chart-empty');
  if (empty) empty.remove();
  canvas.style.display = '';

  monChartInst = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: '收入', data: inc, backgroundColor: '#10b981' },
        { label: '支出', data: exp, backgroundColor: '#ef4444' }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { title: { display: true, text: '月度收支' } }
    }
  });
}
