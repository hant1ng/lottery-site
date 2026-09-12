// 运行时冒烟测试：用最小 DOM mock 驱动 app.js，验证三个彩种都能完整渲染
import fs from "node:fs";
import path from "node:path";

const root = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));

function makeEl(id) {
  const e = {
    id, innerHTML: "", textContent: "", value: "", disabled: false,
    style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    setAttribute(k, v) { e["attr_" + k] = v; },
    appendChild(c) { e.children = e.children || []; e.children.push(c); },
    addEventListener() {}, scrollIntoView() {},
  };
  return e;
}
const els = {};
const svgAttr = {};
globalThis.document = {
  getElementById: (id) => els[id] || (els[id] = makeEl(id)),
  querySelectorAll: () => [],
  querySelector: () => makeEl("qs"),
  createElementNS: () => makeEl("svg-el"),
};
globalThis.fetch = async (url) => {
  const file = path.join(root, decodeURIComponent(url));
  const body = fs.readFileSync(file, "utf8");
  return { ok: true, json: async () => JSON.parse(body) };
};

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const appSrc = fs.readFileSync(path.join(root, "assets", "app.js"), "utf8")
  .replace('"use strict";', "");
const globalEval = eval;
globalEval(appSrc);

await sleep(500); // 等 switchGame('ssq') 完成
for (const code of ["dlt", "p5", "ssq"]) {
  await switchGame(code);
  const title = els["latest-title"].textContent;
  const rows = els["draw-tbody"].innerHTML;
  const frontSvg = els["trend-front"];
  const backSvg = els["trend-back"];
  const miss = els["miss-grid"].innerHTML;
  const pageInfo = els["page-info"].textContent;
  const checks = {
    "标题含期号": /第 \d+ 期/.test(title),
    "表格有数据行": (rows.match(/<tr/g) || []).length === 20,
    "分页文本": /共 \d+ 期/.test(pageInfo),
    "走势图viewBox": /^0 0 \d+ \d+/.test(String(frontSvg.attr_viewBox)),
    "后区走势(仅双色球/大乐透)": code === "p5" ? els["trend-back-wrap"].style.display === "none"
      : /^0 0 \d+ \d+/.test(String(backSvg.attr_viewBox || "")) && els["trend-back-wrap"].style.display !== "none",
    "遗漏统计有内容": miss.length > 100,
  };
  let pass = true;
  console.log("==", code.toUpperCase(), title);
  for (const [k, v] of Object.entries(checks)) {
    console.log("  ", v ? "✓" : "✗", k);
    if (!v) pass = false;
  }
  if (!pass) { console.error(code + " 冒烟测试失败"); process.exit(1); }
}
console.log("\n全部彩种运行时冒烟测试通过 ✅");
