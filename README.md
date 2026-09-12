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
