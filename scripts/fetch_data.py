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
import os
import re
import sys
import time
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


# ---------------------------------------------------------------- 500彩票网(双色球/大乐透)
def fetch_500(code, start, end):
    """按期号区间抓取 500 彩票网历史页, 返回期号升序的 draw 列表"""
    url = ("https://datachart.500.com/%s/history/newinc/history.php"
           "?start=%d&end=%d" % (code, start, end))
    html = http_get(url)
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
    """抓取体彩官网排列五 API 指定页数(每页100条), 返回期号升序列表"""
    draws = []
    for page in range(1, pages + 1):
        url = ("https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
               "?gameNo=350133&provinceId=0&pageSize=100&isVerify=1&pageNo=%d" % page)
        try:
            data = json.loads(http_get(url))
        except Exception as e:
            print("  第 %d 页抓取失败: %s" % (page, e))
            break
        lst = (data.get("value") or {}).get("list") or []
        if not lst:
            break
        for it in lst:
            nums = [int(x) for x in it["lotteryDrawResult"].split()]
            if len(nums) != 5:
                continue
            pl = it.get("prizeLevelList") or []
            p1 = pl[0] if pl else {}
            draws.append({
                "i": it["lotteryDrawNum"], "d": it["lotteryDrawTime"], "n": nums,
                "pool": str(it.get("poolBalanceAfterdraw") or "").replace(",", ""),
                "sales": str(it.get("totalSaleAmount") or "").replace(",", ""),
                "p1c": str(p1.get("stakeCount") or "").replace(",", ""),
                "p1a": str(p1.get("stakeAmountFormat") or "").replace(",", ""),
                "p2c": "", "p2a": "",
            })
        print("  已抓取 %d 页 / %d 期" % (page, len(draws)))
        if len(lst) < 100:
            break
        time.sleep(0.4)
    draws.sort(key=lambda x: x["i"])
    return draws


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


def write_api_files():
    """根据 data/*.json 生成 api/ 下的轻量 JSON 端点(供 AI/程序直接 GET)"""
    os.makedirs(API_DIR, exist_ok=True)
    latest, recent = {}, {}
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
    stamp = time.strftime("%Y-%m-%d %H:%M")
    header = {
        "_readme": "中国彩票开奖数据API。latest=每彩种最新一期; recent=每彩种最新10期(新→旧)。"
                   "单彩种30期: api/ssq.json, api/dlt.json, api/p5.json; "
                   "全部历史: data/{ssq,dlt,p5}_all.json (字段: i=期号,d=日期,n=号码,pool=奖池,sales=销售额,p1c/p1a/p2c/p2a=奖级注数与奖金)。",
        "_updated": stamp,
    }
    with open(os.path.join(API_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump({**header, "games": latest}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(API_DIR, "recent.json"), "w", encoding="utf-8") as f:
        json.dump({**header, "games": recent}, f, ensure_ascii=False, indent=1)
    print("API 文件已生成 -> api/latest.json, api/recent.json, api/{ssq,dlt,p5}.json (%s)" % stamp)


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
