// api.js —— 统一请求封装：错误抛后端 error 字段，供 list.js / dashboard.js 共用
export async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  // 先读取文本，空响应或非 JSON 内容都可回退到统一的状态码提示。
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = {}; }
  if (!res.ok) {
    throw new Error(data.error || `请求失败 (${res.status})`);
  }
  return data;
}
