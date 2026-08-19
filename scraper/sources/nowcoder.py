# -*- coding: utf-8 -*-
"""牛客网(nowcoder.com) 数据源：校招职位 + 校招日程（公司网申时间线）。

接口（均需完整浏览器头，否则触发阿里云 WAF）：
  POST /np-api/u/job/square-search          校招职位（form 编码）
  POST /np-api/u/school-schedule/list-card  校招日程（form 编码）
  GET  /completeness/all-career-jobs        职位类别树（id -> 名称）
"""
import os
import time
from datetime import datetime

from http_client import fetch

NC_BASE = "https://www.nowcoder.com"

JOB_SEARCH = NC_BASE + "/np-api/u/job/square-search"
SCHEDULE_API = NC_BASE + "/np-api/u/school-schedule/list-card"
CAREER_TREE = NC_BASE + "/completeness/all-career-jobs"

EDU_MAP = {0: "学历不限", 1000: "初中", 2000: "高中", 3000: "大专",
           4000: "本科", 5000: "硕士", 6000: "博士", 7000: "MBA/EMBA"}

# 多关键词查询扩大覆盖（每次查询独立分页，服务端每查询最多返回10页）
SEARCH_KEYWORDS = ["", "秋招", "校招", "2027届", "应届", "实习"]
PAGE_SIZE = 20
MAX_PAGES_PER_QUERY = 5
PAGE_INTERVAL = 1.0
SCHEDULE_PAGES = int(os.environ.get("NC_SCHEDULE_PAGES", "15"))


def _ms_to_date(ms):
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return ""


def _ms_to_datetime(ms):
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, OverflowError):
        return ""


def _load_career_map():
    """加载职位类别树，展平为 id -> (顶级类, 二级类) 映射"""
    mapping = {}
    try:
        resp = fetch(CAREER_TREE, timeout=15, retries=2)
        tree = (resp.get("data") or {}).get("allJobs") or []
        for l1 in tree:
            i1 = l1.get("jobInfo") or {}
            name1 = i1.get("name") or ""
            for l2 in l1.get("subJobs") or []:
                i2 = l2.get("jobInfo") or {}
                name2 = i2.get("name") or ""
                mapping[i2.get("id")] = (name1, name2)
                for l3 in l2.get("subJobs") or []:
                    i3 = l3.get("jobInfo") or {}
                    mapping[i3.get("id")] = (name1, name2 or i3.get("name") or "")
            mapping[i1.get("id")] = (name1, name1)
    except Exception:
        pass
    return mapping


def _norm_salary(d):
    mn, mx = d.get("salaryMin") or 0, d.get("salaryMax") or 0
    months = d.get("salaryMonth") or 12
    if mx >= 9999999 or (mn <= 0 and mx <= 0):
        return "面议", None, None, None
    txt = f"{mn}-{mx}K/月"
    if months and months > 12:
        txt += f"·{months}薪"
    return txt, mn, mx, (months if months > 12 else None)


def _norm_exp(d):
    """jobExpInfo 可能为对象（含 expTag）或字符串"""
    exp = d.get("jobExpInfo")
    if isinstance(exp, dict):
        return (exp.get("expTag") or "").strip() or "应届"
    if isinstance(exp, str) and exp.strip():
        return exp.strip()
    return "应届"


def _norm_desc(d):
    """ext 字段为 JSON 字符串（含 requirements/description/infos），解析提取文本"""
    from processing import extract_desc
    ext = (d.get("ext") or "").strip()
    return extract_desc(ext) if ext else ""


def _parse_job(d, career_map):
    jid = d.get("id")
    if not jid:
        return None
    user = d.get("user") or {}
    identity = (user.get("identity") or [{}])[0]
    comp_name = identity.get("companyName") or ""
    cat1, cat2 = career_map.get(d.get("careerJobId"), ("", ""))
    salary, smin, smax, smonths = _norm_salary(d)
    grad = d.get("graduationYear") or ""
    tags = ["校招"] if d.get("recruitType") == 1 else ["实习"]
    if grad and grad != "毕业不限":
        tags.append(grad)
    ext_keys = (d.get("jobKeys") or "").strip()
    return {
        "id": f"nowcoder:{jid}",
        "source": "nowcoder",
        "sourceName": "牛客网",
        "entryType": "job",
        "title": (d.get("jobName") or "").strip(),
        "company": comp_name,
        "companyNature": identity.get("companyNature") or "",
        "industry": d.get("industryName") or "",
        "jobCategory": f"{cat1}/{cat2}" if cat2 and cat2 != cat1 else (cat1 or "其他"),
        "salaryText": salary,
        "salaryMin": smin,
        "salaryMax": smax,
        "salaryMonths": smonths,
        "city": d.get("jobCity") or "全国",
        "district": d.get("jobAddress") or "",
        "education": EDU_MAP.get(d.get("eduLevel"), "学历不限"),
        "experience": _norm_exp(d),
        "recruitType": tags[0],
        "graduationYear": grad if grad != "毕业不限" else "",
        "link": f"https://www.nowcoder.com/jobs/detail/{jid}",
        "applyLink": d.get("redirectExternalUrl") or "",
        "deadline": _ms_to_date(d.get("deliverEnd")),
        "publishDate": _ms_to_date(d.get("createTime")),
        "updateTime": _ms_to_datetime(d.get("updateTime")),
        "logo": "",
        "tags": tags,
        "desc": _norm_desc(d),
    }


def crawl_jobs(logger):
    """按关键词抓取牛客校招职位广场"""
    career_map = _load_career_map()
    logger.info(f"牛客职位类别映射加载 {len(career_map)} 项")
    results = {}
    for kw in SEARCH_KEYWORDS:
        total = 0
        for page in range(1, MAX_PAGES_PER_QUERY + 1):
            form = {
                "careerJobId": "", "jobCity": "", "page": page, "query": kw,
                "random": "true", "recommend": "false", "recruitType": "1",
                "salaryType": "2", "pageSize": PAGE_SIZE, "requestFrom": "1",
                "order": "0", "pageSource": "5001",
            }
            try:
                resp = fetch(JOB_SEARCH, method="POST", form=form,
                             headers={"Referer": f"{NC_BASE}/jobs/school/jobs",
                                      "Origin": NC_BASE})
                data = resp.get("data") or {}
                total = data.get("totalCount") or 0
                datas = data.get("datas") or []
            except Exception as e:
                logger.warn(f"牛客职位[query={kw!r}] 第{page}页失败: {e}")
                if page == 1:
                    raise
                break
            if not datas:
                break
            for wrapper in datas:
                item = _parse_job(wrapper.get("data") or {}, career_map)
                if item and item["title"] and item["company"]:
                    results[item["id"]] = item
            if page * PAGE_SIZE >= total:
                break
            time.sleep(PAGE_INTERVAL)
        logger.info(f"牛客职位[query={kw!r}] 完成: 累计 {len(results)} 条 (该查询总量 {total})")
    return list(results.values())


def _parse_schedule(d):
    """解析校招日程条目（公司级）"""
    comp_name = (d.get("name") or "").strip()
    if not comp_name:
        return None
    comp_id = d.get("companyId")
    batch = d.get("batchName") or ""
    cities = d.get("cityList") or []
    link = d.get("customWangshenLink") or d.get("sourceInformation") or ""
    start = _ms_to_date(d.get("wangshenBeginDate"))
    end = _ms_to_date(d.get("wangshenEndDate"))
    batch_key = batch or (start or "unknown")
    tags = ["校招日程", batch] if batch else ["校招日程"]
    careers = d.get("careerNameList") or []
    industries = d.get("industryList") or []
    return {
        "id": f"ncschedule:{comp_id}:{batch_key}",
        "source": "nowcoder",
        "sourceName": "牛客网",
        "entryType": "schedule",                # schedule=公司级校招日程
        "title": f"{comp_name}{('·' + batch) if batch else ''} 校招",
        "company": comp_name,
        "companyNature": "",
        "industry": "/".join(industries[:3]),
        "jobCategory": "/".join(careers[:6]) or "多岗位",
        "salaryText": "",
        "salaryMin": None,
        "salaryMax": None,
        "salaryMonths": None,
        "city": "、".join(cities[:5]) if cities else "全国",
        "district": "、".join(cities),
        "education": "",
        "experience": "",
        "recruitType": "校招日程",
        "graduationYear": batch.replace("届", "届 ") if "届" in batch else batch,
        "link": link or "https://www.nowcoder.com/jobs/school/schedule",
        "applyLink": link,
        "deadline": end,
        "applyStart": start,
        "applyEnd": end,
        "wangshenTime": d.get("wangshenTime") or "",
        "publishDate": _ms_to_date(d.get("wangshenUpdateTime")),
        "updateTime": _ms_to_datetime(d.get("updateTime")),
        "logo": d.get("homeLogo") or "",
        "tags": [t for t in tags if t],
        "desc": (d.get("companyEvaluation") or "")[:300],
    }


def crawl_schedule(logger):
    """抓取牛客校招日程（公司网申时间线）"""
    results = {}
    for page in range(1, SCHEDULE_PAGES + 1):
        form = {"query": "", "propertyId": "", "page": page,
                "pageSize": PAGE_SIZE, "tab": "1"}
        try:
            resp = fetch(SCHEDULE_API, method="POST", form=form,
                         headers={"Referer": f"{NC_BASE}/jobs/school/schedule",
                                  "Origin": NC_BASE})
            data = resp.get("data") or {}
            total = data.get("totalCount") or 0
            datas = data.get("datas") or []
        except Exception as e:
            logger.warn(f"牛客日程 第{page}页失败: {e}")
            if page == 1:
                raise
            break
        if not datas:
            break
        for d in datas:
            item = _parse_schedule(d)
            if item:
                results[item["id"]] = item
        if page * PAGE_SIZE >= total:
            break
        time.sleep(PAGE_INTERVAL)
    logger.info(f"牛客校招日程抓取完成: {len(results)} 条")
    return list(results.values())
