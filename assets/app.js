/* ============ 彩票开奖数据 - 主脚本 ============ */
"use strict";

const GAME_CONF = {
  ssq: {
    file: "data/ssq_all.json", frontColor: "red", backColor: "blue",
    frontLabel: "红球", backLabel: "蓝球",
  },
  dlt: {
    file: "data/dlt_all.json", frontColor: "red", backColor: "blue",
    frontLabel: "前区", backLabel: "后区",
  },
  p5: {
    file: "data/p5_all.json", frontColor: "red", backColor: null,
    frontLabel: "开奖号码", backLabel: null,
  },
};

const POS_COLORS = ["#e23131", "#d97a1a", "#1f8a4c", "#2b6cb0", "#7c3aed", "#c2185b"];
const SVGNS = "http://www.w3.org/2000/svg";

const state = {
  code: "ssq",
  data: null,
  cache: {},
  page: 0,
  pageSize: 20,
  trendN: 30,
  highlightIssue: null,
};

/* ---------------- 工具函数 ---------------- */
function el(id) { return document.getElementById(id); }
function fmtMoney(v) {
  const n = Number(String(v).replace(/,/g, ""));
  if (!isFinite(n) || !v) return "--";
  if (n >= 1e8) return (n / 1e8).toFixed(2) + " 亿";
  if (n >= 1e4) return (n / 1e4).toFixed(1) + " 万";
  return String(n);
}
function pad2(n) { return n < 10 ? "0" + n : String(n); }
function svgEl(tag, attrs) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

/* ---------------- 数据加载 ---------------- */
async function loadGame(code) {
  if (state.cache[code]) return state.cache[code];
  const rsp = await fetch(GAME_CONF[code].file);
  if (!rsp.ok) throw new Error("加载失败: " + GAME_CONF[code].file);
  const json = await rsp.json();
  state.cache[code] = json;
  return json;
}

async function switchGame(code) {
  state.code = code;
  state.page = 0;
  state.highlightIssue = null;
  el("search-input").value = "";
  el("search-hint").textContent = "";
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.game === code));
  try {
    state.data = await loadGame(code);
  } catch (e) {
    alert("数据加载失败：" + e.message);
    return;
  }
  renderLatest();
  renderTable();
  renderTrend();
  renderStats();
}

/* ---------------- 最新开奖 ---------------- */
function renderLatest() {
  const d = state.data, conf = GAME_CONF[state.code];
  const last = d.draws[d.draws.length - 1];
  const fc = d.rule.front[0], bc = d.rule.back[0];

  el("latest-title").textContent = d.name + " 第 " + last.i + " 期";
  el("latest-date").textContent = "开奖日期 " + last.d + " ｜ 共 " + d.count + " 期历史数据";

  const balls = [];
  for (let i = 0; i < fc; i++)
    balls.push('<span class="ball ' + conf.frontColor + '">' + last.n[i] + "</span>");
  if (bc) {
    balls.push('<span class="ball plus">+</span>');
    for (let i = fc; i < fc + bc; i++)
      balls.push('<span class="ball ' + conf.backColor + '">' + last.n[i] + "</span>");
  }
  el("latest-balls").innerHTML = balls.join("");

  const items = [
    ["奖池金额", fmtMoney(last.pool)],
    ["本期销售额", fmtMoney(last.sales)],
  ];
  if (last.p1c !== "") {
    items.push(["一等奖注数", last.p1c + " 注"]);
    if (last.p1a) items.push(["一等奖单注奖金", fmtMoney(last.p1a) + " 元"]);
    if (last.p2c) items.push(["二等奖注数", last.p2c + " 注"]);
    if (last.p2a) items.push(["二等奖单注奖金", fmtMoney(last.p2a) + " 元"]);
  }
  el("latest-info").innerHTML = items.map(x =>
    '<div class="info-item"><div class="label">' + x[0] +
    '</div><div class="value">' + x[1] + "</div></div>").join("");
}

/* ---------------- 开奖记录表 ---------------- */
function drawRow(x, conf, fc, bc, highlight) {
  let nums = "";
  for (let i = 0; i < fc; i++)
    nums += '<span class="mini-ball ' + conf.frontColor + '">' + x.n[i] + "</span>";
  if (bc) {
    nums += '<span style="color:#7b8794">+ </span>';
    for (let i = fc; i < fc + bc; i++)
      nums += '<span class="mini-ball ' + conf.backColor + '">' + x.n[i] + "</span>";
  }
  const p1 = x.p1c ? (x.p1c + " 注 / " + fmtMoney(x.p1a)) : "--";
  return "<tr" + (highlight ? ' class="highlight"' : "") + "><td>" + x.i + "</td><td>" +
    x.d + "</td><td>" + nums + "</td><td>" + fmtMoney(x.pool) +
    "</td><td>" + fmtMoney(x.sales) + "</td><td>" + p1 + "</td></tr>";
}

function renderTable() {
  const d = state.data, conf = GAME_CONF[state.code];
  const fc = d.rule.front[0], bc = d.rule.back[0];
  const len = d.draws.length;
  const pages = Math.max(1, Math.ceil(len / state.pageSize));
  if (state.page >= pages) state.page = pages - 1;
  if (state.page < 0) state.page = 0;

  // 从最新往前取一页
  const end = len - state.page * state.pageSize;
  const start = Math.max(0, end - state.pageSize);
  const rows = [];
  for (let i = end - 1; i >= start; i--) {
    rows.push(drawRow(d.draws[i], conf, fc, bc, d.draws[i].i === state.highlightIssue));
  }
  el("draw-tbody").innerHTML = rows.join("");
  el("page-info").textContent = "第 " + (state.page + 1) + " / " + pages + " 页（共 " + len + " 期）";
  el("prev-btn").disabled = state.page === 0;
  el("next-btn").disabled = state.page >= pages - 1;
}

function searchDraw() {
  const q = el("search-input").value.trim();
  const hint = el("search-hint");
  if (!q) { hint.textContent = ""; return; }
  const draws = state.data.draws;
  const len = draws.length;
  let idx = -1;
  for (let i = 0; i < len; i++) {
    if (draws[i].i === q || draws[i].i === q.replace(/^(20)/, "")) { idx = i; break; }
  }
  if (idx < 0) {
    hint.textContent = "未找到期号 " + q;
    hint.style.color = "#e23131";
    return;
  }
  hint.textContent = "";
  state.highlightIssue = draws[idx].i;
  // 定位到该期所在页（新->旧分页）
  state.page = Math.floor((len - 1 - idx) / state.pageSize);
  renderTable();
  document.querySelector(".draw-table").scrollIntoView({ behavior: "smooth" });
}

/* ---------------- 走势图 ---------------- */
function renderTrendGrid(svg, draws, numMin, numMax, positionCount, offset) {
  // draws: 旧->新; 每个 position 一条折线
  const n = draws.length;
  const rowH = 22, labelW = 30, rightPad = 16, bottomPad = 26, topPad = 8;
  const cellW = n > 60 ? 13 : (n > 40 ? 18 : 26);
  const rows = numMax - numMin + 1;
  const W = labelW + n * cellW + rightPad;
  const H = rows * rowH + bottomPad + topPad;
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.innerHTML = "";

  const X = (i) => labelW + i * cellW + cellW / 2;
  const Y = (num) => topPad + (numMax - num) * rowH + rowH / 2;

  // 横向网格线 + 号码标签
  for (let num = numMax; num >= numMin; num--) {
    const y = topPad + (numMax - num) * rowH;
    svg.appendChild(svgEl("line", {
      x1: labelW, x2: W - rightPad, y1: y, y2: y,
      class: num % 5 === 0 ? "trend-grid-bold" : "trend-grid",
    }));
    const t = svgEl("text", { x: labelW - 6, y: y + rowH / 2 + 4, "text-anchor": "end", class: "trend-label" });
    t.textContent = num;
    svg.appendChild(t);
  }
  // 竖向网格 + 期号
  const step = Math.max(1, Math.round(n / 12));
  for (let i = 0; i < n; i += step) {
    svg.appendChild(svgEl("line", {
      x1: X(i), x2: X(i), y1: topPad, y2: H - bottomPad, class: "trend-grid",
    }));
    const t = svgEl("text", { x: X(i), y: H - 8, "text-anchor": "middle", class: "trend-issue" });
    t.textContent = draws[i].i.slice(-3);
    svg.appendChild(t);
  }

  // 各位次折线
  for (let p = 0; p < positionCount; p++) {
    const pts = draws.map((x, i) => X(i) + "," + Y(x.n[offset + p]));
    svg.appendChild(svgEl("polyline", {
      points: pts.join(" "), fill: "none",
      stroke: POS_COLORS[p % POS_COLORS.length], "stroke-width": 1.4, opacity: 0.85,
    }));
    draws.forEach((x, i) => {
      svg.appendChild(svgEl("circle", {
        cx: X(i), cy: Y(x.n[offset + p]), r: 5.5,
        fill: POS_COLORS[p % POS_COLORS.length], class: "trend-dot", opacity: .9,
      }));
    });
  }
}

function renderTrend() {
  const d = state.data;
  const fc = d.rule.front[0], bc = d.rule.back[0];
  const draws = d.draws.slice(-state.trendN);
  renderTrendGrid(el("trend-front"), draws, d.rule.front[1] < 10 ? 0 : 1, d.rule.front[1], fc, 0);

  const backWrap = el("trend-back-wrap");
  const backTitle = el("freq-back-title");
  if (bc) {
    backWrap.style.display = "";
    renderTrendGrid(el("trend-back"), draws, 1, d.rule.back[1], bc, fc);
  } else {
    backWrap.style.display = "none";
    backTitle.style.display = "none";
  }

  // 图例
  const legend = [];
  for (let p = 0; p < fc; p++)
    legend.push('<span style="color:' + POS_COLORS[p % POS_COLORS.length] + '">●</span> 第' + (p + 1) + "位");
  if (bc) legend.push("（下方为" + GAME_CONF[state.code].backLabel + "走势）");
  el("trend-legend").innerHTML = "折线连接相邻期同一位置号码，横轴为期号后三位（" +
    draws[0].i + " ~ " + draws[draws.length - 1].i + "）：" + legend.join("　");
}

/* ---------------- 号号统计 ---------------- */
function renderFreq(svg, counts, misses, colorClass) {
  const nums = Object.keys(counts).map(Number).sort((a, b) => a - b);
  const barW = 26, gap = 2, labelW = 10, bottomPad = 26, topPad = 24;
  const W = labelW + nums.length * (barW + gap) + 10;
  const H = 230;
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.innerHTML = "";
  const maxC = Math.max.apply(null, nums.map(k => counts[k]));
  const chartH = H - bottomPad - topPad;
  nums.forEach((num, i) => {
    const c = counts[num];
    const h = Math.max(2, Math.round(c / maxC * chartH));
    const x = labelW + i * (barW + gap);
    const rect = svgEl("rect", {
      x: x, y: H - bottomPad - h, width: barW, height: h, rx: 3,
      class: "freq-bar " + colorClass,
    });
    const title = svgEl("title", {});
    title.textContent = "号码 " + num + "：出现 " + c + " 次，当前遗漏 " + misses[num] + " 期";
    rect.appendChild(title);
    svg.appendChild(rect);
    // 次数
    const t1 = svgEl("text", { x: x + barW / 2, y: H - bottomPad - h - 5, "text-anchor": "middle", class: "freq-count" });
    t1.textContent = c;
    svg.appendChild(t1);
    // 号码
    const t2 = svgEl("text", { x: x + barW / 2, y: H - 8, "text-anchor": "middle", class: "trend-label" });
    t2.textContent = num;
    svg.appendChild(t2);
  });
}

function renderStats() {
  const d = state.data, conf = GAME_CONF[state.code];
  const fc = d.rule.front[0], bc = d.rule.back[0];
  const draws = d.draws;
  const len = draws.length;

  const fCounts = {}, fMiss = {};
  const bCounts = {}, bMiss = {};
  for (let i = 0; i < fc; i++) {
    const min = d.rule.front[1] < 10 ? 0 : 1, max = d.rule.front[1];
    for (let v = min; v <= max; v++) { fCounts[v] = 0; fMiss[v] = -1; }
  }
  if (bc) for (let v = 1; v <= d.rule.back[1]; v++) { bCounts[v] = 0; bMiss[v] = -1; }

  // 从旧到新扫描，fMiss 记录最后出现位置
  for (let i = 0; i < len; i++) {
    const seen = new Set(draws[i].n.slice(0, fc));
    for (const v in fCounts) {
      const num = Number(v);
      if (seen.has(num)) { fCounts[num]++; fMiss[num] = i; }
    }
    if (bc) {
      const seenB = new Set(draws[i].n.slice(fc));
      for (const v in bCounts) {
        const num = Number(v);
        if (seenB.has(num)) { bCounts[num]++; bMiss[num] = i; }
      }
    }
  }
  // 遗漏 = 距最新期数
  for (const v in fCounts) fMiss[v] = fMiss[v] < 0 ? len : len - 1 - fMiss[v];
  for (const v in bCounts) bMiss[v] = bMiss[v] < 0 ? len : len - 1 - bMiss[v];

  el("stats-meta").textContent = "共 " + len + " 期（" + draws[0].d + " ~ " + draws[len - 1].d + "）";
  el("freq-front-title").textContent = conf.frontLabel + "出现频率";
  renderFreq(el("freq-front"), fCounts, fMiss, "");

  const backWrap = el("freq-back-wrap"), backTitle = el("freq-back-title");
  if (bc) {
    backWrap.style.display = "";
    backTitle.style.display = "";
    backTitle.textContent = conf.backLabel + "出现频率";
    renderFreq(el("freq-back"), bCounts, bMiss, "back");
  } else {
    backWrap.style.display = "none";
    backTitle.style.display = "none";
  }

  // 遗漏榜（前区）
  const entries = Object.keys(fCounts).map(k => ({ num: Number(k), miss: fMiss[k] }));
  entries.sort((a, b) => b.miss - a.miss);
  const cold = entries.slice(0, 10);
  const hot = entries.filter(x => x.miss <= 2).slice(0, 10);
  let html = "";
  if (cold.length) {
    html += '<div style="grid-column:1/-1;font-size:13px;color:#7b8794;margin-top:6px">⚠️ 冷号（遗漏最多）</div>';
    html += cold.map(x =>
      '<div class="miss-item"><span class="num cold">' + x.num +
      '</span><span>遗漏 <b>' + x.miss + "</b> 期</span></div>").join("");
  }
  if (hot.length) {
    html += '<div style="grid-column:1/-1;font-size:13px;color:#7b8794;margin-top:6px">🔥 热号（近3期内开出）</div>';
    html += hot.map(x =>
      '<div class="miss-item"><span class="num hot">' + x.num +
      '</span><span>遗漏 ' + x.miss + " 期</span></div>").join("");
  }
  el("miss-grid").innerHTML = html;
}

/* ---------------- 事件绑定 & 启动 ---------------- */
document.querySelectorAll(".tab").forEach(t =>
  t.addEventListener("click", () => switchGame(t.dataset.game)));
el("prev-btn").addEventListener("click", () => { state.page--; renderTable(); });
el("next-btn").addEventListener("click", () => { state.page++; renderTable(); });
el("search-btn").addEventListener("click", searchDraw);
el("search-input").addEventListener("keydown", e => { if (e.key === "Enter") searchDraw(); });
document.querySelectorAll("#trend-range .seg-btn").forEach(b =>
  b.addEventListener("click", () => {
    document.querySelectorAll("#trend-range .seg-btn").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    state.trendN = Number(b.dataset.n);
    renderTrend();
  }));

switchGame("ssq").then(() => {
  const u = state.data.updated;
  if (u) el("updated-info").textContent = "数据更新至：" + u + "（每日自动更新）";
});
