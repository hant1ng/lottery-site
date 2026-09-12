# 彩票开奖数据站点

双色球 / 大乐透 / 排列五 历史开奖数据查询站，纯静态页面，零依赖、零构建。

## 功能

- **最新开奖**：号码、奖池、销售额、一/二等奖注数与奖金
- **开奖记录**：全量历史数据分页浏览，支持期号搜索定位
- **走势图**：近 30/50/100 期，各位次折线连线（经典走势图样式）
- **号码统计**：全量历史出现频率、当前遗漏、冷热号

## 数据

| 彩种 | 期数 | 起始 | 来源 |
|---|---|---|---|
| 双色球 | 3500+ | 2003-02-23 | 500 彩票网（福彩官方数据） |
| 大乐透 | 2900+ | 2007-05-30 | 500 彩票网（体彩官方数据） |
| 排列五 | 7700+ | 2004-11-14 | 中国体彩官网 API |

数据文件在 `data/*.json`，由 `scripts/fetch_data.py` 生成（仅用 Python 标准库）。

## AI / 程序读取接口（静态 JSON API）

部署后（假设域名为 `https://your-domain.com`），AI 助手或任何程序直接 GET 以下 URL 即可，无需密钥、无跨域限制：

| 端点 | 内容 | 大小 |
|---|---|---|
| `/api/latest.json` | 三个彩种**最新一期**开奖（含奖池/销售额/奖级），带规则说明 | ~2 KB |
| `/api/recent.json` | 三个彩种**最新 10 期**（新→旧） | ~12 KB |
| `/api/stats.json` | **预计算统计**：全部历史的号码频率、当前遗漏、历史最大遗漏、和值、奇偶比、卡方检验（p值） | ~16 KB |
| `/api/history.json` | 按年切片历史的索引（列出各彩种可用年份） | ~2 KB |
| `/api/history/<code>/<year>.json` | 某彩种**某一年**的完整开奖（如 `api/history/ssq/2025.json`），AI 可直接放进上下文逐条分析 | ~30 KB/年 |
| `/api/ssq.json` `/api/dlt.json` `/api/p5.json` | 单彩种最新 30 期 | 4–7 KB |
| `/api/compact/ssq.txt` | **双色球全部 3502 期原始号码**，一期一行纯文本，AI 一次性读取自行运算 | 126 KB |
| `/api/compact/dlt.txt` | **大乐透全部 2921 期原始号码**，同上 | 104 KB |
| `/api/compact/p5.txt` | **排列五全部 7719 期原始号码**，同上 | 211 KB |
| `/data/ssq_all.json` 等 | 全部历史含奖池/销售额（约 1MB，适合程序下载） | ~1 MB |

**让 AI 一次性读取全量历史并运算 → 用 `/api/compact/*.txt`。**
JSON 全量文件 1MB 塞不进 AI 上下文，是因为键名、引号、括号占了大头；compact 格式把每期压成一行裸数字（体积缩到 1/8），配合 200K 上下文的 AI 可以整读：

```
26105 2026-09-10 2 4 13 14 15 30 8      ← 期号 日期 红球6个 蓝球
04001 2004-11-14 9 2 8 8 2             ← 排列五: 期号 日期 5位号码
```

文件头部自带 `#` 注释说明格式和规则，时间升序排列，解析只需按行 split。给 AI 的提示词示例：

```
读取 https://your-domain.com/api/compact/ssq.txt（双色球全部历史开奖，
每行格式：期号 日期 红球6个 蓝球，# 开头是注释）。
请基于全部数据计算：红蓝球频率、当前遗漏、和值分布。
```

**根据 AI 的能力选接口：**

- AI **只能读网页/文本**（无代码执行）→ 读 `/api/stats.json`，统计已经算好了（频率排名、遗漏、卡方检验）；要具体某年数据再读 `/api/history/<code>/<year>.json`（每年仅 ~30KB，可完整放进上下文）
- AI **上下文够大**（200K+）→ 直接整读 `/api/compact/<code>.txt` 拿全量原始号码自己运算
- AI **能跑代码** → 直接让它下载 `/data/*_all.json` 自己分析（含奖池/销售额等完整字段）
- 所有 API 文件随每日自动更新一起重新生成，无需维护

`latest.json` 返回示例（AI 可直接理解，字段自解释）：

```json
{
  "_readme": "中国彩票开奖数据API。latest=每彩种最新一期; ...",
  "_updated": "2026-09-12 18:55",
  "games": {
    "ssq": {
      "name": "双色球",
      "rule": "6个号码(1-33) + 1个号码(1-16)",
      "latest": {
        "issue": "26105", "date": "2026-09-10",
        "numbers": [2,4,13,14,15,30,8],
        "front_numbers": [2,4,13,14,15,30], "back_numbers": [8],
        "pool": "833007469", "sales": "333874688",
        "p1c": "1", "p1a": "10000000", "p2c": "100", "p2a": "148168"
      }
    }
  }
}
```

**给 AI 的提示词写法**：让 AI 抓取 `https://your-domain.com/api/latest.json` 并按需解析即可；查询历史走势再让它读 `/data/{彩种}_all.json`。

这些文件由 `fetch_data.py` 在每次更新数据时自动重新生成，随每日自动更新一起部署，无需额外维护。

## 手动更新数据

```bash
python scripts/fetch_data.py                # 全量重建
python scripts/fetch_data.py --incremental  # 只追加最新一期
python scripts/fetch_data.py --lottery ssq # 只更新某个彩种 ssq / dlt / p5
```

## 自动更新（GitHub Actions）

`.github/workflows/update.yml` 已配置每天北京时间 22:00 / 23:30 自动运行
`fetch_data.py --incremental`，如有新数据自动 commit + push。推送后托管平台自动重新部署。

注意：仓库 Actions 需在 Settings → Actions → General 中允许 workflow 读写（默认即可）。

## 部署到 Cloudflare Pages（推荐）

1. 把本项目推到 GitHub 仓库
2. Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git
3. 选择仓库，构建配置：
   - Framework preset: **None**
   - Build command: **留空**
   - Build output directory: **/**（根目录）
4. 点 Save and Deploy，完成。之后每次 push 自动部署

绑定自定义域名：Custom domains → Set up a custom domain（自动配 HTTPS）。

## 部署到 GitHub Pages（备选）

1. Settings → Pages → Source: Deploy from a branch → 选 `main` / `(root)`
2. 或者用 action：`actions/deploy-pages@v4`

## 本地预览

```bash
cd lottery-site
python -m http.server 8000
# 浏览器打开 http://localhost:8000
```

> ⚠️ 直接双击 index.html 打开会因 CORS 无法加载 JSON，需要走本地 HTTP 服务。

## 免责声明

数据来自公开渠道，仅供参考，请以福彩/体彩官方公告为准。理性购彩，量力而行。
