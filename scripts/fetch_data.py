# -*- coding: utf-8 -*-
"""
彩票历史开奖数据抓取脚本（双色球 / 大乐透 / 排列五）

用法:
    python scripts/fetch_data.py                # 全量抓取，重建 data/*.json
    python scripts/fetch_data.py --incremental  # 增量更新（供 GitHub Actions 每日调用）
    python scripts/fetch_data.py --lottery ssq # 只抓某个彩种 ssq / dlt / p5

数据来源:
    双色球/大乐透: 500彩票网历史数据接口 datachart.500.com
    排列五:       中国体彩官网 API webapi.sporttery.cn

输出: data/<code>_all.json，格式:
{
  "code": "ssq", "name": "双色球",
  "rule": {"front": [个数, 最大值], "back": [个数, 最大值]},
  "updated": "2026-09-12",
  "draws": [ {"i":期号, "d":日期, "n":[号码...], "pool":奖池, "sales":销售额,
              "p1c":一等奖注数, "p1a":一等奖奖金, "p2c":..., "p2a":...}, ... ]  # 旧→新
}
仅依赖 Python 标准库。
"""
import json
import math
import os
import re
import sys
import time
import tempfile
import subprocess
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
API_DIR = os.path.join(BASE_DIR, "api")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

GAMES = {
    "ssq": {"name": "双色球",   "front": [6, 33], "back": [1, 16], "first_issue": 301},
    "dlt": {"name": "大乐透",   "front": [5, 35], "back": [2, 12], "first_issue": 7001},
    "p5":  {"name": "排列五",   "front": [5, 9],  "back": [0, 0],  "first_issue": 4001},
}


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.sporttery.cn/" if "sporttery" in url else "https://datachart.500.com/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("gb18030", errors="ignore")



MOBILE_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")


def curl_get(url, referer, timeout=30, cookie_file=None, save_cookies=False):
    """用系统 curl 请求。GitHub Runner 访问部分彩票源时 urllib 容易被 WAF/SSL 拦截。"""
    cmd = [
        "curl", "-fsSLk",
        "--max-time", str(timeout),
        "--retry", "2",
        "--retry-delay", "2",
        url,
        "-H", "User-Agent: %s" % MOBILE_UA,
        "-H", "Accept: application/json,text/plain,*/*",
        "-H", "Referer: %s" % referer,
    ]
    if cookie_file:
        if save_cookies:
            cmd.extend(["-c", cookie_file])
        else:
            cmd.extend(["-b", cookie_file])
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, timeout=timeout + 15)
    if p.returncode != 0:
        raise RuntimeError("curl失败(%d): %s" % (p.returncode, p.stderr.strip()[-300:]))
    if not p.stdout.strip():
        raise RuntimeError("curl返回空内容")
    return p.stdout


def normalize_ssq_issue(issue):
    """福彩官网 2026109 -> 26109，与仓库现有 5 位期号保持一致。"""
    issue = str(issue).strip()
    if len(issue) == 7 and issue.startswith("20"):
        return issue[2:]
    return issue


def fetch_ssq_cwl():
    """从中国福彩网公开接口抓取双色球最近100期，供增量更新。"""
    api = ("https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
           "?name=ssq&issueCount=&issueStart=&issueEnd=&dayStart=&dayEnd="
           "&pageNo=1&pageSize=100&week=&systemType=PC")
    landing = "https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/"
    cookie_path = os.path.join(tempfile.gettempdir(), "lottery_cwl_cookie.txt")
    try:
        # 先访问历史开奖页取得站点 Cookie；部分节点直调 API 会被 WAF 拦截。
        try:
            curl_get(landing, landing, timeout=20,
                     cookie_file=cookie_path, save_cookies=True)
        except Exception as e:
            print("  福彩Cookie预热失败，继续直连API: %s" % e)
        raw = curl_get(api, landing, timeout=30,
                       cookie_file=cookie_path if os.path.exists(cookie_path) else None)
        data = json.loads(raw, strict=False)
        if data.get("state") not in (0, None):
            raise RuntimeError("福彩API异常: %s" % data.get("message"))
        items = data.get("result") or []
        if not items:
            raise RuntimeError("福彩API未返回开奖记录")

        draws = []
        for it in items:
            try:
                reds = [int(x) for x in str(it.get("red") or "").split(",") if x.strip()]
                blue = [int(str(it.get("blue") or "").strip())]
                nums = reds + blue
                if len(reds) != 6 or len(nums) != 7:
                    continue
                prizes = it.get("prizegrades") or []
                p1 = next((p for p in prizes if str(p.get("type")) == "1"), {})
                p2 = next((p for p in prizes if str(p.get("type")) == "2"), {})

                def clean(v):
                    return str(v or "").replace(",", "").replace("元", "").strip()

                draws.append({
                    "i": normalize_ssq_issue(it.get("code")),
                    "d": str(it.get("date") or "")[:10],
                    "n": nums,
                    "pool": clean(it.get("poolmoney")),
                    "sales": clean(it.get("sales")),
                    "p1c": clean(p1.get("typenum")),
                    "p1a": clean(p1.get("typemoney")),
                    "p2c": clean(p2.get("typenum")),
                    "p2a": clean(p2.get("typemoney")),
                })
            except (TypeError, ValueError):
                continue
        if not draws:
            raise RuntimeError("福彩API数据无法解析")
        draws.sort(key=lambda x: x["i"])
        return draws
    finally:
        try:
            os.remove(cookie_path)
        except OSError:
            pass


# ---------------------------------------------------------------- 500彩票网(双色球/大乐透)
def fetch_500(code, start, end):
    """按期号区间抓取 500 彩票网历史页, 返回期号升序的 draw 列表"""
    url = ("https://datachart.500.com/%s/history/newinc/history.php"
           "?start=%d&end=%d" % (code, start, end))
    try:
        html = http_get(url)
    except Exception as e:
        print("  urllib访问500数据源失败，改用curl: %s" % e)
        html = curl_get(url, "https://datachart.500.com/%s/history/" % code, timeout=30)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S).replace("\n", "")
    rows = re.findall(r'<tr class="t_tr1">(.*?)</tr>', html)
    draws = []
    front_count = GAMES[code]["front"][0]
    back_count = GAMES[code]["back"][0]
    # 双色球多一列"快乐星期天", 两种彩种列位置不同
    if code == "ssq":
        col = {"pool": 9, "p1c": 10, "p1a": 11, "p2c": 12, "p2a": 13, "sales": 14, "date": 15}
    else:
        col = {"pool": 8, "p1c": 9, "p1a": 10, "p2c": 11, "p2a": 12, "sales": 13, "date": 14}
    need = max(col.values()) + 1
    for r in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r)
        cells = [re.sub(r"<[^>]+>|&nbsp;|\s", "", t).replace(",", "") for t in tds]
        if len(cells) < need or not cells[0].isdigit():
            continue
        nums = [int(x) for x in cells[1:8] if x.isdigit()]
        if len(nums) != front_count + back_count:
            continue
        draws.append({
            "i": cells[0], "d": cells[col["date"]], "n": nums,
            "pool": cells[col["pool"]], "sales": cells[col["sales"]],
            "p1c": cells[col["p1c"]], "p1a": cells[col["p1a"]],
            "p2c": cells[col["p2c"]], "p2a": cells[col["p2a"]],
        })
    draws.sort(key=lambda x: x["i"])
    return draws


# ---------------------------------------------------------------- 体彩官网(排列五)
def fetch_p5_pages(pages):
    """抓取排列五。优先使用可从GitHub Runner访问的500历史页，体彩官网作备用。"""
    # 500 的排列五 HTML 与双色球/大乐透位于同一可达域名。
    # 每次取当前年份即可覆盖自动更新期间可能漏掉的期数。
    try:
        yy = int(time.strftime("%y"))
        start_issue = yy * 1000 + 1
        end_issue = yy * 1000 + 999
        url = ("https://datachart.500.com/plw/history/inc/history.php"
               "?start=%d&end=%d" % (start_issue, end_issue))
        try:
            html = http_get(url, timeout=35)
        except Exception as e:
            print("  排列五500 urllib失败，改用curl: %s" % e)
            html = curl_get(url, "https://datachart.500.com/plw/history/", timeout=30)

        html = re.sub(r"<!--.*?-->", "", html, flags=re.S).replace("\n", "")
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I)
        mirror = []
        for row in rows:
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)
            cells = []
            for td in tds:
                cell = re.sub(r"<[^>]+>", "", td)
                cell = cell.replace("&nbsp;", " ").strip()
                cells.append(cell)
            if len(cells) < 5:
                continue
            issue = re.sub(r"\D", "", cells[0])
            nums_text = re.sub(r"\D", "", cells[1])
            if len(issue) != 5 or len(nums_text) != 5:
                continue
            date = next((c[:10] for c in reversed(cells)
                         if re.match(r"^\d{4}-\d{2}-\d{2}", c)), "")
            if not date:
                continue
            nums = [int(x) for x in nums_text]
            sales = re.sub(r"[^0-9.]", "", cells[3]) if len(cells) > 3 else ""
            mirror.append({
                "i": issue, "d": date, "n": nums,
                "pool": "", "sales": sales, "p1c": "", "p1a": "",
                "p2c": "", "p2a": "",
            })
        if mirror:
            mirror.sort(key=lambda x: x["i"])
            print("  排列五500 HTML源已抓取 %d 期，最新 %s" %
                  (len(mirror), mirror[-1]["i"]))
            return mirror
        print("  排列五500 HTML源未解析到数据，尝试体彩官网")
    except Exception as e:
        print("  排列五500 HTML源失败: %s，尝试体彩官网" % e)

    last_error = None
    for game_no in ("350133", "37"):
        draws = []
        failed_first_page = False
        for page in range(1, pages + 1):
            url = ("https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
                   "?gameNo=%s&provinceId=0&pageSize=100&isVerify=1&pageNo=%d"
                   % (game_no, page))
            try:
                raw = curl_get(url, "https://m.lottery.gov.cn/", timeout=25)
                data = json.loads(raw, strict=False)
                lst = (data.get("value") or {}).get("list") or []
                if page == 1 and not lst:
                    raise RuntimeError("体彩API返回空列表")
                if not lst:
                    break
            except Exception as e:
                last_error = e
                print("  排列五 gameNo=%s 第%d页抓取失败: %s" % (game_no, page, e))
                if page == 1:
                    failed_first_page = True
                break

            for it in lst:
                try:
                    nums = [int(x) for x in str(it.get("lotteryDrawResult") or "").split()]
                except ValueError:
                    continue
                if len(nums) != 5:
                    continue
                pl = it.get("prizeLevelList") or []
                p1 = pl[0] if pl else {}
                draws.append({
                    "i": str(it.get("lotteryDrawNum") or ""),
                    "d": str(it.get("lotteryDrawTime") or "")[:10],
                    "n": nums,
                    "pool": str(it.get("poolBalanceAfterdraw") or "").replace(",", ""),
                    "sales": str(it.get("totalSaleAmount") or it.get("drawMoney") or "").replace(",", ""),
                    "p1c": str(p1.get("stakeCount") or p1.get("awardLevelNum") or "").replace(",", ""),
                    "p1a": str(p1.get("stakeAmountFormat") or p1.get("awardMoney") or "").replace(",", ""),
                    "p2c": "", "p2a": "",
                })
            print("  排列五 gameNo=%s 已抓取 %d 页 / %d 期" % (game_no, page, len(draws)))
            if len(lst) < 100:
                break
            time.sleep(0.8)

        if draws and not failed_first_page:
            draws.sort(key=lambda x: x["i"])
            return draws

    # 体彩接口在 GitHub Runner 上可能被 WAF 返回 567，改走500开奖 XML 镜像。
    try:
        from xml.etree import ElementTree as ET
        url = "https://datachart.500.com/static/info/kaijiang/xml/plw/list.xml"
        raw = curl_get(url, "https://datachart.500.com/plw/history/", timeout=25)
        root = ET.fromstring(raw)
        fallback = []
        for row in root.findall("row"):
            issue = str(row.get("expect") or "").strip()
            date = str(row.get("opentime") or "")[:10]
            parts = str(row.get("opencode") or "").replace(",", " ").split()
            try:
                nums = [int(x) for x in parts]
            except ValueError:
                continue
            if not issue or len(nums) != 5 or not all(0 <= x <= 9 for x in nums):
                continue
            fallback.append({
                "i": issue, "d": date, "n": nums,
                "pool": "", "sales": "", "p1c": "", "p1a": "",
                "p2c": "", "p2a": "",
            })
            if len(fallback) >= max(100, pages * 100):
                break
        if not fallback:
            raise RuntimeError("500排列五XML未解析到数据")
        fallback.sort(key=lambda x: x["i"])
        print("  排列五 500 XML备用源已抓取 %d 期" % len(fallback))
        return fallback
    except Exception as fallback_error:
        raise RuntimeError("排列五官方接口失败(%s)，500备用源也失败(%s)"
                           % (last_error, fallback_error))


# ---------------------------------------------------------------- 数据文件读写
def data_path(code):
    return os.path.join(DATA_DIR, "%s_all.json" % code)


def load_data(code):
    if os.path.exists(data_path(code)):
        with open(data_path(code), encoding="utf-8") as f:
            return json.load(f)
    return None


def save_data(code, draws):
    g = GAMES[code]
    os.makedirs(DATA_DIR, exist_ok=True)
    obj = {
        "code": code, "name": g["name"],
        "rule": {"front": g["front"], "back": g["back"]},
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "count": len(draws),
        "draws": draws,
    }
    with open(data_path(code), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print("%s: 共 %d 期, %s ~ %s -> %s"
          % (g["name"], len(draws), draws[0]["d"], draws[-1]["d"], data_path(code)))


def validate(code, draws):
    g = GAMES[code]
    fc, fmax, bc, bmax = g["front"][0], g["front"][1], g["back"][0], g["back"][1]
    fmin = 0 if code == "p5" else 1  # 排列五每位的取值范围是 0-9
    bad = 0
    for x in draws:
        nums = x["n"]
        if len(nums) != fc + bc:
            bad += 1
            continue
        if any(not (fmin <= v <= fmax) for v in nums[:fc]):
            bad += 1
            continue
        if bc and any(not (1 <= v <= bmax) for v in nums[fc:]):
            bad += 1
    if bad:
        raise ValueError("%s 有 %d 条数据校验失败" % (g["name"], bad))


# ---------------------------------------------------------------- AI 友好 API 文件
def api_draw(raw, g):
    """把内部精简格式转成 AI 易读的完整字段"""
    fc = g["front"][0]
    nums = raw["n"]
    out = {
        "issue": raw["i"],                      # 期号, 如 26105
        "date": raw["d"],                       # 开奖日期
        "numbers": nums,                        # 全部号码(升序排列)
    }
    if g["back"][0]:                           # 有后区/蓝球的彩种拆分展示
        out["front_numbers"] = nums[:fc]        # 前区/红球
        out["back_numbers"] = nums[fc:]         # 后区/蓝球
    for k, label in [("pool", "奖池金额(元)"), ("sales", "销售额(元)"),
                     ("p1c", "一等奖注数"), ("p1a", "一等奖单注奖金(元)"),
                     ("p2c", "二等奖注数"), ("p2a", "二等奖单注奖金(元)")]:
        if raw.get(k):
            out[k] = raw[k]
    return out


def number_pool(code, part):
    """返回 (最小号码, 最大号码) — part: front/back"""
    g = GAMES[code]
    if part == "front":
        lo = 0 if code == "p5" else 1
        return lo, g["front"][1]
    return 1, g["back"][1]


def chi2_pvalue(chi2, df):
    """卡方分布右尾概率的 Wilson-Hilferty 正态近似(无需 scipy)"""
    if df <= 0:
        return None
    z = (chi2 / df) ** (1.0 / 3) - (1 - 2.0 / (9 * df))
    z /= math.sqrt(2.0 / (9 * df))
    return 0.5 * math.erfc(z / math.sqrt(2))


def compute_stats(code, draws):
    """全量历史统计: 频率/遗漏/和值/奇偶/卡方检验 — 让只读文本的AI也能拿到分析结果"""
    g = GAMES[code]
    fc, bc = g["front"][0], g["back"][0]
    n = len(draws)
    parts = {"front": fc}
    if bc:
        parts["back"] = bc

    out = {"total_draws": n}
    for part, cnt in parts.items():
        lo, hi = number_pool(code, part)
        counts = {v: 0 for v in range(lo, hi + 1)}
        last_seen = {}                 # 号码 -> 期索引
        max_miss = {v: 0 for v in range(lo, hi + 1)}
        prev = {v: None for v in range(lo, hi + 1)}
        for idx, x in enumerate(draws):
            nums = x["n"][:fc] if part == "front" else x["n"][fc:]
            for v in nums:
                counts[v] += 1
                if prev[v] is not None:
                    max_miss[v] = max(max_miss[v], idx - prev[v] - 1)
                prev[v] = idx
                last_seen[v] = idx
        rows = []
        for v in range(lo, hi + 1):
            cur_miss = (n - 1 - last_seen[v]) if v in last_seen else n
            if prev[v] is not None:
                max_miss[v] = max(max_miss[v], cur_miss)
            rows.append({
                "number": v, "count": counts[v],
                "percent": round(counts[v] * 100.0 / (n * cnt), 2),
                "current_miss": cur_miss,          # 当前遗漏期数
                "max_miss": max_miss[v],           # 历史最大遗漏
            })
        # 卡方检验: 实际频率 vs 均匀分布期望
        k = hi - lo + 1
        expected = n * cnt / k
        chi2 = sum((r["count"] - expected) ** 2 / expected for r in rows)
        out[part] = {
            "numbers": sorted(rows, key=lambda r: -r["count"]),
            "expected_percent": round(100.0 / k, 2),
            "chi2_test": {"chi2": round(chi2, 2), "df": k - 1,
                          "p_value_approx": round(chi2_pvalue(chi2, k - 1), 4),
                          "note": "p>0.05 表示与均匀分布无显著差异(随机性正常)"},
        }
    # 和值/奇偶(前区)
    sums = [sum(x["n"][:fc]) for x in draws]
    odds = [sum(1 for v in x["n"][:fc] if v % 2) for x in draws]
    out["sum"] = {"min": min(sums), "max": max(sums),
                  "mean": round(sum(sums) / n, 1),
                  "current": sums[-1], "current_date": draws[-1]["d"]}
    out["odd_even"] = {"avg_odd_in_front": round(sum(odds) / n, 2)}
    return out


def write_history_files(code, draws):
    """按年份切片写 api/history/<code>/<year>.json — 单年约20KB, AI可直接放进上下文"""
    g = GAMES[code]
    years = {}
    for x in draws:
        years.setdefault(x["d"][:4], []).append(api_draw(x, g))
    outdir = os.path.join(API_DIR, "history", code)
    os.makedirs(outdir, exist_ok=True)
    # 先清掉旧年份文件(数据修正时可能变化)
    for fn in os.listdir(outdir):
        os.remove(os.path.join(outdir, fn))
    for y, lst in sorted(years.items()):
        with open(os.path.join(outdir, "%s.json" % y), "w", encoding="utf-8") as f:
            json.dump({"game": g["name"], "year": y, "count": len(lst),
                       "draws": lst}, f, ensure_ascii=False, separators=(",", ":"))
    return sorted(years)


def write_compact_files(code, draws):
    """写 api/compact/<code>.txt — 全量原始号码, 一期一行纯文本, 供 AI 一次性读取运算。

    格式(空格分隔): 期号 日期 红球/前区号码... [蓝球/后区号码]
    例: 26105 2026-09-10 1 7 12 19 25 33 8
    """
    g = GAMES[code]
    outdir = os.path.join(API_DIR, "compact")
    os.makedirs(outdir, exist_ok=True)
    fc, bc = g["front"][0], g["back"][0]
    lines = []
    for x in draws:
        nums = x["n"]
        front = " ".join(str(v) for v in nums[:fc])
        back = " ".join(str(v) for v in nums[fc:]) if bc else ""
        lines.append("%s %s %s%s" % (x["i"], x["d"], front, (" " + back) if back else ""))
    header = (
        "# %s 全量开奖数据(时间升序, 一期一行)\n"
        "# 期号 日期 %s%s\n"
        "# 共%d期 %s~%s 更新于%s\n"
        % (g["name"],
           "前区%d个(%d-%d)" % (fc, 0 if code == "p5" else 1, g["front"][1]),
           (" 后区%d个(%d-%d)" % (bc, 1, g["back"][1])) if bc else " 单区",
           len(draws), draws[0]["d"], draws[-1]["d"], time.strftime("%Y-%m-%d %H:%M"))
    )
    path = os.path.join(outdir, "%s.txt" % code)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    return path


def write_api_files():
    """根据 data/*.json 生成 api/ 下的轻量 JSON 端点(供 AI/程序直接 GET)"""
    os.makedirs(API_DIR, exist_ok=True)
    latest, recent, stats, history_index = {}, {}, {}, {}
    for code, g in GAMES.items():
        data = load_data(code)
        if not data or not data.get("draws"):
            continue
        draws = data["draws"]
        latest[code] = {
            "name": g["name"],
            "rule": ("%d个号码(%d-%d)" % (g["front"][0], 1 if code != "p5" else 0, g["front"][1])
                    + ((" + %d个号码(%d-%d)" % (g["back"][0], 1, g["back"][1])) if g["back"][0] else "")),
            "latest": api_draw(draws[-1], g),
        }
        recent[code] = {
            "name": g["name"],
            "rule": latest[code]["rule"],
            "recent": [api_draw(x, g) for x in draws[-10:]],  # 最新10期, 新→旧在前
        }
        # 每个彩种单独的端点: api/<code>.json = 最新30期
        with open(os.path.join(API_DIR, "%s.json" % code), "w", encoding="utf-8") as f:
            json.dump({**recent[code],
                       "recent": [api_draw(x, g) for x in draws[-30:][::-1]],
                       "total_draws": len(draws),
                       "full_history_url": "data/%s_all.json" % code},
                      f, ensure_ascii=False, separators=(",", ":"))
        # 预计算统计端点 + 按年切片历史
        stats[code] = {"name": g["name"], "rule": latest[code]["rule"],
                       **compute_stats(code, draws)}
        years = write_history_files(code, draws)
        history_index[code] = {"name": g["name"], "years": years,
                               "url_pattern": "api/history/%s/<year>.json" % code}
        # 全量紧凑文本 — AI 可一次性读取全部号码自行运算
        compact_path = write_compact_files(code, draws)
        size_kb = os.path.getsize(compact_path) / 1024
        print("  compact: api/compact/%s.txt (%d期, %.0f KB)" % (code, len(draws), size_kb))
    stamp = time.strftime("%Y-%m-%d %H:%M")
    header = {
        "_readme": "中国彩票开奖数据API。latest=每彩种最新一期; recent=每彩种最新10期(新→旧)。"
                   "单彩种30期: api/ssq.json, api/dlt.json, api/p5.json; "
                   "预计算统计(频率/遗漏/卡方): api/stats.json; "
                   "按年切片历史: api/history.json; "
                   "全部历史: data/{ssq,dlt,p5}_all.json (字段: i=期号,d=日期,n=号码,pool=奖池,sales=销售额,p1c/p1a/p2c/p2a=奖级注数与奖金)。",
        "_updated": stamp,
    }
    with open(os.path.join(API_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump({**header, "games": latest}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(API_DIR, "recent.json"), "w", encoding="utf-8") as f:
        json.dump({**header, "games": recent}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(API_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump({**header, "games": stats}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(API_DIR, "history.json"), "w", encoding="utf-8") as f:
        json.dump({**header, "games": history_index}, f, ensure_ascii=False, indent=1)
    print("API 文件已生成 -> latest/recent/stats/history + api/history/<code>/<year>.json (%s)" % stamp)


def next_issue(issue):
    """03001 -> 03002, 26105 -> 26106"""
    return "%05d" % (int(issue) + 1)


# ---------------------------------------------------------------- 主流程
def full_fetch(code):
    """全量重建"""
    if code == "p5":
        draws = fetch_p5_pages(pages=200)
    else:
        draws = fetch_500(code, GAMES[code]["first_issue"], 99999)
    if not draws:
        raise RuntimeError("%s 未抓到任何数据" % GAMES[code]["name"])
    validate(code, draws)
    save_data(code, draws)


def incremental_fetch(code):
    """增量更新: 只抓本地最后一起之后的新数据"""
    old = load_data(code)
    if not old or not old.get("draws"):
        print("%s: 本地无数据, 转全量抓取" % GAMES[code]["name"])
        return full_fetch(code)
    old_draws = old["draws"]
    last = old_draws[-1]["i"]
    have = {x["i"] for x in old_draws}

    if code == "p5":
        new = fetch_p5_pages(pages=3)
    elif code == "ssq":
        try:
            new = fetch_500(code, int(next_issue(last)), 99999)
        except Exception as e:
            print("  500双色球数据源失败，回退福彩官网: %s" % e)
            new = fetch_ssq_cwl()
    else:
        new = fetch_500(code, int(next_issue(last)), 99999)

    added = [x for x in new if x["i"] not in have]
    if not added:
        print("%s: 已是最新 (期号 %s)" % (GAMES[code]["name"], last))
        return
    # 校验并合并
    validate(code, added)
    merged = old_draws + added
    save_data(code, merged)
    print("%s: 新增 %d 期 (%s)" % (GAMES[code]["name"], len(added),
                                    ", ".join(x["i"] for x in added)))


def main():
    args = sys.argv[1:]
    incremental = "--incremental" in args
    codes = []
    for a in args:
        if a in GAMES and a != "--incremental":
            codes.append(a)
    if not codes:
        codes = list(GAMES)
    for code in codes:
        try:
            if incremental:
                incremental_fetch(code)
            else:
                full_fetch(code)
        except Exception as e:
            print("%s 抓取失败: %s" % (GAMES[code]["name"], e))
            if not incremental:
                raise
    # 无论全量/增量, 只要任一彩种数据文件存在就刷新 API 端点
    try:
        write_api_files()
    except Exception as e:
        print("API 文件生成失败: %s" % e)


if __name__ == "__main__":
    main()
