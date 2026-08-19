# -*- coding: utf-8 -*-
"""国聘(iguopin.com) 数据源 —— 央国企官方招聘平台。

接口：POST https://gp-api.iguopin.com/api/jobs/v3/list（需 HMAC-SHA256 签名）
性质码：校招 115xW5oQ / 实习 11bTac9（源自 /api/base/category/v1/by-alias）
"""
import os
import time

from http_client import fetch
from signer import make_headers

API_BASE = "https://gp-api.iguopin.com"
LIST_PATH = "/api/jobs/v3/list"

NATURE_CODE = {"校招": "115xW5oQ", "实习": "11bTac9"}

# 单次运行抓取页数上限（每页20条），可通过环境变量调整
MAX_PAGES = int(os.environ.get("IGUOPIN_MAX_PAGES", "30"))
PAGE_SIZE = 20
PAGE_INTERVAL = 1.2   # 每页间隔（秒），礼貌抓取


def _norm_salary(job):
    """把国聘薪资字段标准化为展示文本 + 数值区间（K/月）"""
    mn, mx = job.get("min_wage") or 0, job.get("max_wage") or 0
    unit = job.get("wage_unit_cn") or ""
    months = job.get("months") or 12
    if job.get("is_negotiable") or (mn <= 0 and mx <= 0):
        return "面议", None, None, months
    # 单位归一：统一换算为 K/月
    if "K" in unit or "k" in unit:
        kmn, kmx = mn, mx
    elif "万" in unit:
        kmn, kmx = mn * 10, mx * 10
    else:  # 元/月 或 元/天
        if mx >= 1000:
            kmn, kmx = round(mn / 1000, 1), round(mx / 1000, 1)
        else:  # 小数值按日薪处理，标注原样
            txt = f"{mn}-{mx}{unit}"
            if unit == "元/天" and months and months > 1:
                txt += f"·{months}月"
            return txt, None, None, months
    txt = f"{kmn:g}-{kmx:g}K/月"
    if months and months > 12:
        txt += f"·{months}薪"
    return txt, kmn, kmx, months


def _parse_job(raw):
    job_id = raw.get("job_id")
    if not job_id:
        return None
    comp = raw.get("company_info") or {}
    districts = raw.get("district_list") or []
    area = districts[0].get("area_cn", "") if districts else ""
    city = area.split("-")[0] if area else "全国"
    salary, smin, smax, months = _norm_salary(raw)

    nature = raw.get("nature_cn") or "校招"
    tags = [nature]
    comp_nature = comp.get("nature_cn") or ""
    if comp_nature in ("国企", "央企", "事业单位", "国家机关", "国有控股"):
        tags.append("央国企")

    end = (raw.get("end_time") or "")[:10]
    return {
        "id": f"iguopin:{job_id}",
        "source": "iguopin",
        "sourceName": "国聘",
        "entryType": "job",                      # job=具体职位
        "title": (raw.get("job_name") or "").strip(),
        "company": (raw.get("company_name") or comp.get("name") or "").strip(),
        "companyNature": comp_nature,
        "industry": comp.get("industry_cn") or "",
        "jobCategory": raw.get("category_cn") or "其他职位",
        "salaryText": salary,
        "salaryMin": smin,
        "salaryMax": smax,
        "salaryMonths": months if months > 12 else None,
        "city": city,
        "district": area,
        "education": raw.get("education_cn") or "学历不限",
        "experience": raw.get("experience_cn") or "",
        "recruitType": nature,
        "graduationYear": "应届" if raw.get("is_graduates") else "",
        "link": f"https://www.iguopin.com/job/detail?id={job_id}",
        "applyLink": "",
        "deadline": end,
        "publishDate": (raw.get("start_time") or "")[:10],
        "updateTime": (raw.get("update_time") or "")[:19],
        "logo": comp.get("show_logo") or "",
        "tags": tags,
        "desc": (raw.get("contents") or "")[:500],
    }


def _fetch_page(page, nature_code, keyword=""):
    body = {
        "search": {
            "page": page, "page_size": PAGE_SIZE, "keyword": keyword,
            "nature": [nature_code], "with_offline": True,
            "content_type": ["job"], "view_type": ["card"],
        }
    }
    headers = make_headers("POST", LIST_PATH)
    headers.update({"Origin": "https://www.iguopin.com",
                    "Referer": "https://www.iguopin.com/"})
    resp = fetch(API_BASE + LIST_PATH, method="POST", data=body, headers=headers)
    if resp.get("code") != 200:
        raise RuntimeError(f"国聘接口返回异常: {resp.get('code')} {resp.get('msg')}")
    data = resp.get("data") or {}
    return data.get("list") or [], data.get("total") or 0


def crawl(logger):
    """抓取国聘「校招 + 实习」职位，返回统一结构列表"""
    results = {}
    for nature_name, code in NATURE_CODE.items():
        total = 0
        pages = MAX_PAGES
        for page in range(1, pages + 1):
            try:
                jobs, total = _fetch_page(page, code)
            except Exception as e:
                logger.warn(f"国聘[{nature_name}] 第{page}页失败: {e}")
                if page == 1:
                    raise        # 首页失败视为源故障，触发重试/告警
                break
            if not jobs:
                break
            for raw in jobs:
                item = _parse_job(raw)
                if item and item["title"]:
                    results[item["id"]] = item
            if page * PAGE_SIZE >= total:
                break
            time.sleep(PAGE_INTERVAL)
        logger.info(f"国聘[{nature_name}] 抓取完成: 本源累计 {len(results)} 条 (服务端总量 {total})")
    return list(results.values())
