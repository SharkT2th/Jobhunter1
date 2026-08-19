# -*- coding: utf-8 -*-
"""BOSS直聘 数据源（尽力而为模式）。

BOSS直聘反爬极强：搜索接口必须携带 __zp_stoken__ 令牌 Cookie（由混淆 JS
在浏览器中实时生成，无法在纯 HTTP 环境伪造）。本模块策略：
  1. 若配置了环境变量 ZHIPIN_COOKIE（用户从浏览器复制的完整 Cookie），
     则携带 Cookie 抓取「校招/秋招」关键词职位；
  2. 否则尝试无 Cookie 访问一次，预期收到 code=37（环境异常），
     记录提示后返回空列表 —— 单源失败不影响整体流水线。

获取 Cookie 方法：浏览器登录 zhipin.com -> F12 -> Network -> 复制请求
Cookie 头 -> GitHub 仓库 Secrets 添加 ZHIPIN_COOKIE。
"""
import os
import time
import urllib.parse

from http_client import fetch, FetchError

SEARCH_API = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"

# 城市代码（BOSS直聘站内编码）：覆盖主要秋招城市
CITIES = {"101010100": "北京", "101020100": "上海", "101280100": "深圳",
          "101280600": "广州", "101210100": "杭州", "101270100": "成都",
          "101200100": "武汉", "101190100": "南京", "101030100": "天津",
          "101110100": "西安"}

KEYWORDS = ["秋招", "校招"]
PAGES_PER_QUERY = 2
PAGE_INTERVAL = 2.0

EDU_MAP = {101: "初中", 102: "高中", 103: "大专", 104: "本科",
           105: "硕士", 106: "博士"}


def _norm_salary(salary_desc):
    """'25-50K·16薪' -> ('25-50K/月·16薪', 25, 50)"""
    if not salary_desc or salary_desc in ("面议",):
        return "面议", None, None
    txt = salary_desc.replace("K", "K/月") if "K" in salary_desc and "K/月" not in salary_desc else salary_desc
    mn = mx = None
    try:
        core = salary_desc.split("K")[0]
        if "-" in core:
            a, b = core.split("-")
            mn, mx = float(a), float(b)
    except (ValueError, IndexError):
        pass
    return txt, mn, mx


def _parse_job(j, city_name):
    job_id = j.get("encryptJobId") or j.get("jobId")
    if not job_id:
        return None
    brand = j.get("brandName") or j.get("brandComName") or ""
    salary, mn, mx = _norm_salary(j.get("salaryDesc") or "")
    tags = ["校招"]
    if (j.get("jobType") or 0) == 0 and "校" not in (j.get("jobName") or ""):
        pass
    return {
        "id": f"zhipin:{job_id}",
        "source": "zhipin",
        "sourceName": "BOSS直聘",
        "entryType": "job",
        "title": (j.get("jobName") or "").strip(),
        "company": brand,
        "companyNature": j.get("companyNature") or "",
        "industry": j.get("industryName") or "",
        "jobCategory": (j.get("jobCategory") or {}).get("name1") or "其他",
        "salaryText": salary,
        "salaryMin": mn,
        "salaryMax": mx,
        "salaryMonths": None,
        "city": j.get("cityName") or city_name,
        "district": (j.get("areaDistrict") or "") + (j.get("businessDistrict") or ""),
        "education": EDU_MAP.get(j.get("jobDegree"), "学历不限"),
        "experience": j.get("jobExperience") or "应届",
        "recruitType": "校招",
        "graduationYear": "",
        "link": f"https://www.zhipin.com/job_detail/{job_id}.html",
        "applyLink": "",
        "deadline": "",
        "publishDate": "",
        "updateTime": "",
        "logo": j.get("brandLogo") or "",
        "tags": tags,
        "desc": (j.get("postDescription") or "")[:500],
    }


def crawl(logger):
    cookie = os.environ.get("ZHIPIN_COOKIE", "").strip()
    headers = {"Referer": "https://www.zhipin.com/web/geek/job",
               "Accept": "application/json, text/plain, */*"}
    if cookie:
        headers["Cookie"] = cookie
        logger.info("BOSS直聘：使用已配置的 Cookie 抓取")
    else:
        logger.warn("BOSS直聘：未配置 ZHIPIN_COOKIE（可选），仅尝试公开访问")

    results = {}
    blocked = False
    for city_code, city_name in CITIES.items():
        if blocked:
            break
        for kw in KEYWORDS:
            for page in range(1, PAGES_PER_QUERY + 1):
                params = {
                    "scene": "1", "query": kw, "city": city_code,
                    "page": str(page), "pageSize": "30",
                }
                url = SEARCH_API + "?" + urllib.parse.urlencode(params)
                try:
                    resp = fetch(url, headers=headers, timeout=15,
                                 retries=2, sleep=2.0)
                except FetchError as e:
                    logger.warn(f"BOSS直聘[{city_name}/{kw}] 第{page}页失败: {e}")
                    blocked = page == 1 and not results
                    break
                code = resp.get("code")
                if code == 37:
                    logger.warn("BOSS直聘：环境校验失败(code=37)，"
                                "需配置 ZHIPIN_COOKIE Secret 后才能抓取，跳过该源")
                    blocked = True
                    break
                if code != 0:
                    logger.warn(f"BOSS直聘接口 code={code}: {resp.get('message')}")
                    blocked = page == 1 and not results
                    break
                zp = resp.get("zpData") or {}
                jobs = (zp.get("jobList") or [])
                if not jobs:
                    break
                for j in jobs:
                    item = _parse_job(j, city_name)
                    if item and item["title"] and item["company"]:
                        results[item["id"]] = item
                more = zp.get("hasMore", True)
                if not more:
                    break
                time.sleep(PAGE_INTERVAL)
            if blocked:
                break
    logger.info(f"BOSS直聘抓取结束: {len(results)} 条"
                + ("（未配置Cookie，来源受限）" if not cookie else ""))
    return list(results.values())
