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
| `/api/ssq.json` | 双色球最新 30 期 | ~7 KB |
| `/api/dlt.json` | 大乐透最新 30 期 | ~7 KB |
| `/api/p5.json` | 排列五最新 30 期 | ~4 KB |
| `/data/ssq_all.json` 等 | 全部历史（数千期） | ~1 MB |

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
