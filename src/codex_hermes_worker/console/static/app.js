"use strict";

const token = document.querySelector('meta[name="console-token"]').content;
const titles = {
  overview: "工作台总览",
  analytics: "数据统计",
  jobs: "任务与结果",
  "new-task": "新建受限任务",
  trusted: "完整工具模式",
};
const statusLabels = {
  queued: "排队中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const state = {
  overview: null,
  health: null,
  jobStatus: "",
  view: "overview",
};

const byId = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const headers = {
    "X-Console-Token": token,
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };
  const response = await fetch(path, { ...options, headers });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = { error: `HTTP ${response.status}` };
  }
  if (!response.ok) {
    const detail = Array.isArray(payload.details)
      ? payload.details.map((item) => item.msg).join("；")
      : payload.error;
    throw new Error(detail || `请求失败：HTTP ${response.status}`);
  }
  return payload;
}

function showMessage(text, error = false) {
  const node = byId("global-message");
  node.textContent = text;
  node.classList.toggle("error", error);
  node.classList.remove("hidden");
  window.clearTimeout(showMessage.timer);
  showMessage.timer = window.setTimeout(() => node.classList.add("hidden"), 6000);
}

function setView(name) {
  state.view = name;
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    const active = button.dataset.view === name;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  byId("page-title").textContent = titles[name];
  if (name === "jobs") loadJobs();
  if (name === "overview") loadOverview();
  if (name === "analytics") loadAnalytics();
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function shortId(value) {
  return value ? value.slice(0, 8) : "—";
}

function statusBadge(status) {
  const badge = document.createElement("span");
  badge.className = `status-badge ${status}`;
  badge.textContent = statusLabels[status] || status;
  return badge;
}

function rowAction(jobId) {
  const button = document.createElement("button");
  button.className = "row-action";
  button.type = "button";
  button.title = "查看详情";
  button.setAttribute("aria-label", `查看任务 ${shortId(jobId)} 的详情`);
  button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9.3 6.7 1.4-1.4 6.7 6.7-6.7 6.7-1.4-1.4 5.3-5.3-5.3-5.3Z"/></svg>';
  button.addEventListener("click", () => openJob(jobId));
  return button;
}

function renderRecentJobs(jobs) {
  const container = byId("recent-jobs");
  container.replaceChildren();
  if (!jobs.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.style.minHeight = "160px";
    const strong = document.createElement("strong");
    strong.textContent = "还没有本地任务";
    const p = document.createElement("p");
    p.textContent = "从“新建任务”开始第一次委派。";
    empty.append(strong, p);
    container.append(empty);
    return;
  }
  jobs.forEach((job) => {
    const row = document.createElement("div");
    row.className = "job-row";

    const identity = document.createElement("div");
    identity.className = "job-identity";
    const name = document.createElement("strong");
    name.textContent = job.task_type;
    const id = document.createElement("small");
    id.textContent = shortId(job.job_id);
    identity.append(name, id);

    const progressCell = document.createElement("div");
    progressCell.className = "progress-cell";
    const track = document.createElement("div");
    track.className = "progress-track";
    const bar = document.createElement("div");
    bar.className = "progress-bar";
    bar.style.width = `${Math.round((job.progress || 0) * 100)}%`;
    track.append(bar);
    const label = document.createElement("span");
    label.className = "progress-label";
    label.textContent = `${Math.round((job.progress || 0) * 100)}%`;
    progressCell.append(track, label);

    const time = document.createElement("span");
    time.className = "job-time";
    time.textContent = formatDate(job.created_at);
    row.append(identity, statusBadge(job.status), progressCell, time, rowAction(job.job_id));
    container.append(row);
  });
}

function renderMetrics(metrics) {
  byId("metric-total").textContent = metrics.total_jobs ?? 0;
  byId("metric-active").textContent =
    (metrics.queued_jobs ?? 0) + (metrics.running_jobs ?? 0);
  byId("metric-completed").textContent = metrics.completed_jobs ?? 0;
  byId("metric-review").textContent = metrics.needs_review ?? 0;
}

async function loadOverview() {
  try {
    const overview = await api("/api/overview");
    state.overview = overview;
    renderRecentJobs(overview.recent_jobs);
    byId("model-name").textContent = overview.configuration.model;
    byId("work-directory").textContent = overview.configuration.work_directory;
    populatePresets(overview.presets);
    populateToolsets(overview.configuration.trusted_toolsets);
  } catch (error) {
    showMessage(`无法读取总览：${error.message}`, true);
  }
}

const numberFormatter = new Intl.NumberFormat("zh-CN");
const compactFormatter = new Intl.NumberFormat("zh-CN", {
  notation: "compact",
  maximumFractionDigits: 2,
});
const usdFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

function formatTokenCount(value) {
  const numeric = Number(value || 0);
  return numeric >= 1000000
    ? compactFormatter.format(numeric)
    : numberFormatter.format(numeric);
}

function formatAnalyticsPeriod(period) {
  if (!period?.first_seen || !period?.last_seen) return "暂无用量记录";
  const format = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return `${format.format(new Date(period.first_seen))} — ${format.format(
    new Date(period.last_seen)
  )}`;
}

function renderTokenChart(daily) {
  const chart = byId("token-chart");
  const tableContainer = byId("token-chart-table");
  chart.replaceChildren();
  tableContainer.replaceChildren();
  if (!daily.length) {
    const empty = document.createElement("div");
    empty.className = "chart-empty";
    empty.textContent = "还没有可显示的每日 Token 数据。";
    chart.append(empty);
    return;
  }
  const maximum = Math.max(
    ...daily.map((item) => item.input_tokens + item.output_tokens),
    1
  );
  daily.forEach((item) => {
    const row = document.createElement("div");
    row.className = "token-chart-row";
    row.setAttribute(
      "aria-label",
      `${item.date}，输入 ${numberFormatter.format(
        item.input_tokens
      )}，输出 ${numberFormatter.format(item.output_tokens)}`
    );
    const date = document.createElement("span");
    date.className = "chart-date";
    date.textContent = item.date.slice(5);
    const bars = document.createElement("div");
    bars.className = "chart-bars";
    const input = document.createElement("i");
    input.className = "chart-bar input";
    input.style.width = `${Math.max(
      1.5,
      (item.input_tokens / maximum) * 100
    )}%`;
    const output = document.createElement("i");
    output.className = "chart-bar output";
    output.style.width = `${Math.max(
      1.5,
      (item.output_tokens / maximum) * 100
    )}%`;
    bars.append(input, output);
    const value = document.createElement("strong");
    value.textContent = compactFormatter.format(
      item.input_tokens + item.output_tokens
    );
    row.append(date, bars, value);
    chart.append(row);
  });

  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "查看每日数字明细";
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["日期", "输入 Token", "输出 Token"].forEach((label) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    headRow.append(cell);
  });
  head.append(headRow);
  const body = document.createElement("tbody");
  daily.forEach((item) => {
    const row = document.createElement("tr");
    [item.date, item.input_tokens, item.output_tokens].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent =
        typeof value === "number" ? numberFormatter.format(value) : value;
      row.append(cell);
    });
    body.append(row);
  });
  table.append(head, body);
  details.append(summary, table);
  tableContainer.append(details);
}

function renderModeBreakdown(modes) {
  const container = byId("mode-breakdown");
  container.replaceChildren();
  const labels = {
    restricted_batch: ["受限批处理", "默认安全模式"],
    trusted_full: ["完整工具", "显式授权模式"],
  };
  modes.forEach((mode) => {
    const item = document.createElement("article");
    item.className = `mode-usage-card ${mode.mode}`;
    const heading = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = labels[mode.mode]?.[0] || mode.mode;
    const subtitle = document.createElement("small");
    subtitle.textContent = labels[mode.mode]?.[1] || "Execution mode";
    heading.append(title, subtitle);
    const total = document.createElement("b");
    total.textContent = formatTokenCount(mode.total_tokens);
    const totalLabel = document.createElement("span");
    totalLabel.textContent = "Token";
    const details = document.createElement("dl");
    [
      ["运行次数", numberFormatter.format(mode.runs)],
      ["输入", numberFormatter.format(mode.input_tokens)],
      ["输出", numberFormatter.format(mode.output_tokens)],
      ["Sol 等价", usdFormatter.format(mode.gpt56_sol_estimated_cost_usd)],
    ].forEach(([label, value]) => {
      const row = document.createElement("div");
      const term = document.createElement("dt");
      term.textContent = label;
      const description = document.createElement("dd");
      description.textContent = value;
      row.append(term, description);
      details.append(row);
    });
    item.append(heading, total, totalLabel, details);
    container.append(item);
  });
}

async function loadAnalytics() {
  try {
    const payload = await api("/api/analytics");
    renderMetrics(payload.jobs);
    const tokens = payload.tokens;
    byId("analytics-unavailable").classList.toggle("hidden", tokens.available);
    byId("analytics-period").textContent = formatAnalyticsPeriod(tokens.period);
    byId("token-input").textContent = formatTokenCount(tokens.total.input_tokens);
    byId("token-output").textContent = formatTokenCount(tokens.total.output_tokens);
    byId("token-total").textContent = formatTokenCount(tokens.total.total_tokens);
    byId("token-run-detail").textContent = `${numberFormatter.format(
      tokens.total.runs
    )} 次本地运行`;
    byId("token-cost").textContent = tokens.available
      ? usdFormatter.format(tokens.total.gpt56_sol_estimated_cost_usd)
      : "不可用";
    byId("estimated-cost-detail").textContent = tokens.available
      ? usdFormatter.format(tokens.total.gpt56_sol_estimated_cost_usd)
      : "Token 账本不可用";
    byId("pricing-rate-detail").textContent =
      `$${tokens.pricing.input_usd_per_million}/M 输入 · ` +
      `$${tokens.pricing.output_usd_per_million}/M 输出`;
    byId("actual-cost-detail").textContent = tokens.total.actual_cost_available
      ? usdFormatter.format(tokens.total.actual_cost_usd)
      : "提供方未报告";
    renderTokenChart(tokens.daily);
    renderModeBreakdown(tokens.modes);
  } catch (error) {
    showMessage(`无法读取数据统计：${error.message}`, true);
  }
}

function setNodeState(id, ok) {
  const node = byId(id);
  node.className = `node-state ${ok ? "ready" : "failed"}`;
}

async function loadHealth() {
  const chip = byId("service-chip");
  chip.className = "status-chip checking";
  byId("service-label").textContent = "正在检查";
  ["bridge-state", "hermes-state", "qwen-state"].forEach((id) => {
    byId(id).className = "node-state checking";
  });
  try {
    const health = await api("/api/health");
    state.health = health;
    chip.className = `status-chip ${health.ok ? "ready" : "failed"}`;
    byId("service-label").textContent = health.ok ? "链路正常" : "需要检查";
    setNodeState("bridge-state", health.bridge?.status === "ready");
    setNodeState("hermes-state", Boolean(health.hermes?.hermes_ok));
    setNodeState("qwen-state", Boolean(health.hermes?.qwen_ok));
    byId("hermes-version").textContent =
      health.hermes?.hermes_version || health.hermes?.error || "不可用";
    byId("network-policy").textContent = health.security?.allow_network
      ? "默认允许"
      : "默认关闭";
  } catch (error) {
    chip.className = "status-chip failed";
    byId("service-label").textContent = "控制台异常";
    ["bridge-state", "hermes-state", "qwen-state"].forEach((id) =>
      setNodeState(id, false)
    );
    showMessage(`健康检查失败：${error.message}`, true);
  }
}

function populatePresets(presets) {
  const select = byId("task-type");
  if (select.options.length) return;
  Object.entries(presets).forEach(([value, preset]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = `${preset.label} · ${value}`;
    select.append(option);
  });
}

function populateToolsets(toolsets) {
  const container = byId("toolset-options");
  if (container.children.length) return;
  const defaults = new Set(["terminal", "file", "code_execution", "skills"]);
  toolsets.forEach((toolset) => {
    const label = document.createElement("label");
    label.className = "tool-check";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = "toolsets";
    input.value = toolset;
    input.checked = defaults.has(toolset);
    const text = document.createElement("span");
    text.textContent = toolset;
    label.append(input, text);
    container.append(label);
  });
}

async function loadJobs() {
  try {
    const query = state.jobStatus
      ? `?status=${encodeURIComponent(state.jobStatus)}`
      : "";
    const payload = await api(`/api/jobs${query}`);
    renderJobsTable(payload.jobs);
  } catch (error) {
    showMessage(`无法读取任务：${error.message}`, true);
  }
}

function renderJobsTable(jobs) {
  const body = byId("jobs-table-body");
  const empty = byId("jobs-empty");
  body.replaceChildren();
  empty.classList.toggle("hidden", jobs.length > 0);
  jobs.forEach((job) => {
    const row = document.createElement("tr");
    const identity = document.createElement("td");
    identity.className = "job-identity";
    const name = document.createElement("strong");
    name.textContent = job.task_type;
    const id = document.createElement("small");
    id.textContent = job.job_id;
    identity.append(name, id);

    const status = document.createElement("td");
    status.append(statusBadge(job.status));

    const progress = document.createElement("td");
    const wrap = document.createElement("div");
    wrap.className = "table-progress";
    const track = document.createElement("div");
    track.className = "progress-track";
    const bar = document.createElement("div");
    bar.className = "progress-bar";
    const percentage = Math.round((job.progress || 0) * 100);
    bar.style.width = `${percentage}%`;
    track.append(bar);
    const progressLabel = document.createElement("span");
    progressLabel.className = "progress-label";
    progressLabel.textContent = `${percentage}%`;
    wrap.append(track, progressLabel);
    progress.append(wrap);

    const processed = document.createElement("td");
    processed.textContent = String(job.processed ?? 0);
    const created = document.createElement("td");
    created.textContent = formatDate(job.created_at);
    const action = document.createElement("td");
    action.append(rowAction(job.job_id));
    row.append(identity, status, progress, processed, created, action);
    body.append(row);
  });
}

function detailStat(label, value) {
  const node = document.createElement("div");
  node.className = "detail-stat";
  const name = document.createElement("span");
  name.textContent = label;
  const content = document.createElement("strong");
  content.textContent = value;
  node.append(name, content);
  return node;
}

function detailSection(title) {
  const section = document.createElement("section");
  section.className = "detail-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  section.append(heading);
  return section;
}

async function openJob(jobId) {
  const dialog = byId("job-dialog");
  const content = byId("dialog-content");
  byId("dialog-title").textContent = `任务 ${shortId(jobId)}`;
  content.textContent = "正在读取任务详情…";
  dialog.showModal();
  try {
    const payload = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    const summary = payload.summary;
    content.replaceChildren();

    const stats = document.createElement("div");
    stats.className = "detail-grid";
    stats.append(
      detailStat("状态", statusLabels[summary.status] || summary.status),
      detailStat("进度", `${Math.round((summary.progress || 0) * 100)}%`),
      detailStat("结果", String(summary.processed || 0)),
      detailStat("待复核", String(summary.needs_review || 0))
    );
    content.append(stats);

    if (summary.error) {
      const error = document.createElement("div");
      error.className = "message error";
      error.textContent = summary.error;
      content.append(error);
    }

    const eventsSection = detailSection("运行事件");
    const events = document.createElement("div");
    events.className = "event-list";
    payload.events.forEach((event) => {
      const item = document.createElement("div");
      item.className = "event-item";
      const strong = document.createElement("strong");
      strong.textContent = statusLabels[event.event_type] || event.event_type;
      const small = document.createElement("small");
      small.textContent = `${event.message} · ${formatDate(event.created_at)}`;
      item.append(strong, small);
      events.append(item);
    });
    eventsSection.append(events);
    content.append(eventsSection);

    const resultSection = detailSection(`结果预览（${payload.results.length}）`);
    const results = document.createElement("div");
    results.className = "result-list";
    if (!payload.results.length) {
      const item = document.createElement("div");
      item.className = "result-item";
      item.textContent = "当前没有可预览的结构化结果。";
      results.append(item);
    }
    payload.results.forEach((result) => {
      const item = document.createElement("div");
      item.className = "result-item";
      const strong = document.createElement("strong");
      strong.textContent = `${result.category} · ${Math.round(result.confidence * 100)}%`;
      const small = document.createElement("small");
      small.textContent = `${result.source_path} — ${result.summary}`;
      item.append(strong, small);
      results.append(item);
    });
    resultSection.append(results);
    content.append(resultSection);

    const artifacts = detailSection("本地文件");
    Object.entries(payload.artifacts).forEach(([label, path]) => {
      const code = document.createElement("code");
      code.className = "artifact-path";
      code.textContent = `${label}: ${path}`;
      artifacts.append(code);
    });
    content.append(artifacts);

    if (["queued", "running"].includes(summary.status)) {
      const cancel = document.createElement("button");
      cancel.className = "cancel-button";
      cancel.type = "button";
      cancel.textContent = "请求取消任务";
      cancel.addEventListener("click", async () => {
        cancel.disabled = true;
        try {
          await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
            method: "POST",
            body: "{}",
          });
          showMessage("已发送取消请求。");
          dialog.close();
          await Promise.all([loadOverview(), loadJobs()]);
        } catch (error) {
          showMessage(`取消失败：${error.message}`, true);
          cancel.disabled = false;
        }
      });
      content.append(cancel);
    }
  } catch (error) {
    content.textContent = `无法读取任务详情：${error.message}`;
  }
}

async function submitJob(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const preset = state.overview.presets[data.get("task_type")];
  const payload = {
    task_type: data.get("task_type"),
    instructions: data.get("instructions").trim(),
    input_paths: data
      .get("input_paths")
      .split(/\r?\n/)
      .map((value) => value.trim())
      .filter(Boolean),
    profile: preset.profile,
    output_schema: preset.output_schema,
    max_steps: Number(data.get("max_steps")),
  };
  const button = byId("submit-job");
  button.disabled = true;
  button.textContent = "正在提交…";
  try {
    const result = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showMessage(`任务已进入本地队列：${shortId(result.job_id)}`);
    form.reset();
    byId("steps-output").textContent = "8";
    await loadOverview();
    setView("jobs");
  } catch (error) {
    showMessage(`提交失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = "提交到本地队列";
  }
}

async function submitTrusted(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  if (!data.get("acknowledge")) {
    showMessage("必须先明确确认完整模式风险。", true);
    return;
  }
  const payload = {
    instructions: data.get("instructions").trim(),
    working_directory: data.get("working_directory").trim(),
    toolsets: data.getAll("toolsets"),
    allow_network: Boolean(data.get("allow_network")),
    include_optional_tools: false,
    max_steps: 20,
    timeout_seconds: Number(data.get("timeout_seconds")),
    authorization: "explicit_user_authorized",
    risk_acknowledgement: "trusted_full",
  };
  const button = byId("submit-trusted");
  const result = byId("trusted-result");
  button.disabled = true;
  button.textContent = "Hermes 正在执行…";
  result.textContent = "任务正在本机执行。请保持此页面开启；完成前不要重复提交。";
  result.classList.remove("hidden");
  try {
    const response = await api("/api/trusted-tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    result.textContent = [
      `任务：${response.task_id}`,
      `模型：${response.model}`,
      `耗时：${response.runtime_seconds} 秒`,
      `工具：${response.toolsets.join(", ")}`,
      `审计：${response.audit_log}`,
      "",
      response.result,
    ].join("\n");
    showMessage("完整模式任务已完成。");
  } catch (error) {
    result.textContent = `执行失败：${error.message}`;
    showMessage(`完整模式失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = "授权并执行";
  }
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  document.querySelectorAll("[data-go]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.go));
  });
  document.querySelectorAll(".filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".filter-button").forEach((item) =>
        item.classList.remove("active")
      );
      button.classList.add("active");
      state.jobStatus = button.dataset.status;
      loadJobs();
    });
  });
  byId("refresh-button").addEventListener("click", () =>
    Promise.all([loadOverview(), loadHealth(), loadJobs(), loadAnalytics()])
  );
  byId("health-refresh").addEventListener("click", loadHealth);
  byId("job-form").addEventListener("submit", submitJob);
  byId("trusted-form").addEventListener("submit", submitTrusted);
  byId("job-form").elements.max_steps.addEventListener("input", (event) => {
    byId("steps-output").textContent = event.target.value;
  });
  byId("dialog-close").addEventListener("click", () => byId("job-dialog").close());
  byId("job-dialog").addEventListener("click", (event) => {
    if (event.target === byId("job-dialog")) byId("job-dialog").close();
  });
}

async function init() {
  bindEvents();
  await loadOverview();
  await loadHealth();
  window.setInterval(() => {
    if (state.view === "overview") loadOverview();
    if (state.view === "analytics") loadAnalytics();
    if (state.view === "jobs") loadJobs();
  }, 5000);
  window.setInterval(loadHealth, 30000);
}

init();
