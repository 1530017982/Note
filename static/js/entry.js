/**
 * 5号：录入界面交互（templates/index.html + static/css/main.css + 本文件）
 *
 * 职责范围：
 * 1. 日期默认取浏览器本地“今天”，避免 UTC 偏移；
 * 2. 收入 / 支出切换；
 * 3. 金额“元”文本 → 整数“分”的字符串换算，不经过浮点乘法；
 * 4. 提交前做与后端一致的轻量校验，失败保留已填内容并展示原因；
 * 5. 成功后派发 records-changed 事件，通知列表与统计刷新。
 *
 * 接口与事件约定见 README 3.2、3.6、3.9。
 */

const MAX_AMOUNT_CENTS = 999999999;
const MAX_NOTE_LENGTH = 200;
const MAX_CATEGORY_LENGTH = 20;
const CATEGORY_OPTIONS = {
  income: ["饮食", "交通", "购物", "住房", "其他"],
  expense: ["工资", "其他"],
};

const form = document.querySelector("#record-form");
const messageBox = document.querySelector("#record-message");
const submitButton = document.querySelector("#record-submit");
const dateInput = form ? form.querySelector('[name="date"]') : null;
const amountInput = form ? form.querySelector('[name="amount"]') : null;
const categoryInput = form ? form.querySelector('[name="category"]') : null;
const noteInput = form ? form.querySelector('[name="note"]') : null;

/** 正在提交时忽略重复点击，避免同一笔被记两次 */
let submitting = false;

/** 按 Unicode 码点计数，与后端校验口径一致 */
function codePointLength(text) {
  return Array.from(text).length;
}

/** 本地日期 YYYY-MM-DD，不使用 toISOString，避免时区偏移到前一天 */
function localToday() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** 校验是否为 10 字符的真实日期（含闰年、月末天数） */
function isRealDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const [year, month, day] = value.split("-").map(Number);
  if (year < 1000) {
    return false;
  }
  const probe = new Date(Date.UTC(year, month - 1, day));
  return (
    probe.getUTCFullYear() === year &&
    probe.getUTCMonth() === month - 1 &&
    probe.getUTCDate() === day
  );
}

/**
 * “元”文本 → 整数“分”。
 * 按字符串拆分整数位与小数位，不用 parseFloat(text) * 100，避免 19.99 → 1998。
 * @returns {{cents: number} | {error: string}}
 */
function toCents(text) {
  const raw = String(text == null ? "" : text).trim();
  if (raw === "") {
    return { error: "请填写金额" };
  }
  if (!/^\d+(\.\d{1,2})?$/.test(raw)) {
    return { error: "金额只能包含数字，最多两位小数，例如 12.50" };
  }
  const [yuanPart, fractionPart = ""] = raw.split(".");
  const cents = Number(yuanPart) * 100 + Number((fractionPart + "00").slice(0, 2));
  if (!Number.isSafeInteger(cents) || cents < 1 || cents > MAX_AMOUNT_CENTS) {
    return { error: "金额需在 0.01 元到 9,999,999.99 元之间" };
  }
  return { cents };
}

/** 分 → 显示用两位小数字符串 */
function formatCents(cents) {
  return (cents / 100).toFixed(2);
}

function setMessage(text, kind) {
  if (!messageBox) {
    return;
  }
  messageBox.textContent = text || "";
  messageBox.className = "message";
  if (text && kind) {
    messageBox.classList.add(`message--${kind}`);
  }
}

function markInvalid(input, invalid) {
  if (!input) {
    return;
  }
  if (invalid) {
    input.setAttribute("aria-invalid", "true");
  } else {
    input.removeAttribute("aria-invalid");
  }
}

function clearMarks() {
  [dateInput, amountInput, categoryInput, noteInput].forEach((input) => markInvalid(input, false));
}

/** 收支类型使用各自的类别；切换时清除不属于新类型的已选类别。 */
function syncCategoryOptions() {
  if (!form || !categoryInput) return;
  const type = form.querySelector('input[name="type"]:checked')?.value;
  const categories = CATEGORY_OPTIONS[type] || [];
  const previous = categoryInput.value;
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "请选择类别";
  categoryInput.replaceChildren(placeholder);
  categories.forEach((category) => {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    categoryInput.appendChild(option);
  });
  categoryInput.value = categories.includes(previous) ? previous : "";
  markInvalid(categoryInput, false);
}

/**
 * 读取表单并做提交前校验，返回 { payload } 或 { error, field, input }。
 * 后端仍是最终校验依据，这里只是减少无效请求。
 */
function readForm() {
  const date = dateInput ? dateInput.value.trim() : "";
  const checkedType = form.querySelector('input[name="type"]:checked');
  const type = checkedType ? checkedType.value : "";
  const category = categoryInput ? categoryInput.value.trim() : "";
  const note = noteInput ? noteInput.value.trim() : "";

  if (!isRealDate(date)) {
    return { error: "请选择有效日期，格式为 YYYY-MM-DD", field: "date", input: dateInput };
  }
  if (type !== "income" && type !== "expense") {
    return { error: "请选择收入或支出", field: "type", input: null };
  }

  const money = toCents(amountInput ? amountInput.value : "");
  if (money.error) {
    return { error: money.error, field: "amount", input: amountInput };
  }

  if (codePointLength(category) < 1) {
    return { error: "请选择类别", field: "category", input: categoryInput };
  }
  if (!CATEGORY_OPTIONS[type].includes(category)) {
    return { error: "请选择当前收支类型对应的类别", field: "category", input: categoryInput };
  }
  if (codePointLength(category) > MAX_CATEGORY_LENGTH) {
    return { error: `类别最多 ${MAX_CATEGORY_LENGTH} 个字符`, field: "category", input: categoryInput };
  }
  if (codePointLength(note) > MAX_NOTE_LENGTH) {
    return { error: `备注最多 ${MAX_NOTE_LENGTH} 个字符`, field: "note", input: noteInput };
  }

  const payload = { date, type, amount: money.cents, category };
  if (note !== "") {
    payload.note = note;
  }
  return { payload };
}

/** 提交成功后清空录入内容，保留日期与收支类型，方便连续记账 */
function resetEntryFields() {
  [amountInput, categoryInput, noteInput].forEach((input) => {
    if (input) {
      input.value = "";
    }
  });
  if (amountInput) {
    amountInput.focus();
  }
}

async function handleSubmit(event) {
  event.preventDefault();
  if (submitting) {
    return;
  }

  clearMarks();
  const result = readForm();
  if (result.error) {
    markInvalid(result.input, true);
    setMessage(result.error, "error");
    if (result.input) {
      result.input.focus();
    }
    return;
  }

  submitting = true;
  const originalLabel = submitButton ? submitButton.textContent : "";
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "保存中…";
  }

  try {
    const response = await fetch("/api/records", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result.payload),
    });

    let body = null;
    try {
      body = await response.json();
    } catch (parseError) {
      body = null;
    }

    if (!response.ok) {
      // 失败时保留已填写内容，提示后端的 error 文案
      const reason =
        body && typeof body.error === "string" && body.error.trim() !== ""
          ? body.error
          : `保存失败（HTTP ${response.status}）`;
      if (body && body.field) {
        const fieldMap = {
          date: dateInput,
          amount: amountInput,
          category: categoryInput,
          note: noteInput,
        };
        markInvalid(fieldMap[body.field], true);
      }
      setMessage(reason, "error");
      return;
    }

    const record = body && body.data ? body.data : null;
    const recordId = record && record.id ? record.id : "";
    const typeLabel = result.payload.type === "income" ? "收入" : "支出";
    setMessage(
      `已记录${typeLabel} ${formatCents(result.payload.amount)} 元 · ${result.payload.category}`,
      "success",
    );
    resetEntryFields();
    clearMarks();

    // 通知列表与统计刷新；action 固定为 created
    document.dispatchEvent(
      new CustomEvent("records-changed", {
        detail: { action: "created", id: recordId },
      }),
    );
  } catch (networkError) {
    setMessage("网络异常，暂时无法确认保存结果。请先刷新账单核对，再决定是否重试。", "error");
  } finally {
    submitting = false;
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
    }
  }
}

function initEntryForm() {
  if (!form) {
    return;
  }
  if (dateInput && dateInput.value === "") {
    dateInput.value = localToday();
  }
  syncCategoryOptions();
  form.querySelectorAll('input[name="type"]').forEach((input) => {
    input.addEventListener("change", syncCategoryOptions);
  });
  form.addEventListener("submit", handleSubmit);
  [dateInput, amountInput, categoryInput, noteInput].forEach((input) => {
    if (input) {
      input.addEventListener("input", () => markInvalid(input, false));
    }
  });
  if (categoryInput) {
    categoryInput.addEventListener("change", () => markInvalid(categoryInput, false));
  }
}

initEntryForm();
