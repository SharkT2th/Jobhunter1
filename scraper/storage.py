# -*- coding: utf-8 -*-
"""存储系统：增量合并、去重、每日归档、统计趋势。

文件布局（均相对于仓库根目录 docs/data/）：
  jobs.json     全量数据（含 active 标记 + 首见/最近见到日期），前端直接加载
  stats.json    每日统计历史（趋势图用）
  archive/      每日快照（按日期归档，保留历史）
"""
import json
import os
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "data")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")

# 连续 N 天未抓到即视为「已下线」
STALE_DAYS = 14
# 归档保留天数（超过则清理，避免仓库无限膨胀）
ARCHIVE_KEEP_DAYS = 90


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def load_existing():
    """读取现有全量数据：返回 {id: job}"""
    data = _read_json(os.path.join(DATA_DIR, "jobs.json"), {"jobs": []})
    return {j["id"]: j for j in data.get("jobs", []) if "id" in j}


def merge(existing, fresh, today):
    """增量合并：新数据补 firstSeen；旧数据更新字段与 lastSeen"""
    merged = dict(existing)
    new_count = 0
    for job in fresh:
        jid = job["id"]
        if jid in merged:
            old = merged[jid]
            # 保留首次发现时间，其余字段以最新抓取为准
            job["firstSeen"] = old.get("firstSeen", today)
            job["isNew"] = False
        else:
            job["firstSeen"] = today
            job["isNew"] = True
            new_count += 1
        job["lastSeen"] = today
        merged[jid] = job

    # 标记疑似下线：连续多天未见到且已过截止日
    for jid, job in merged.items():
        last = job.get("lastSeen", today)
        days_unseen = (time.mktime(time.strptime(today, "%Y-%m-%d")) -
                       time.mktime(time.strptime(last, "%Y-%m-%d"))) / 86400
        deadline = job.get("deadline") or ""
        if days_unseen >= STALE_DAYS or (deadline and deadline < today):
            job["active"] = False
        else:
            job["active"] = True
    return merged, new_count


def save(merged, today, source_stats):
    """写 jobs.json / stats.json / 当日归档，并清理过期归档"""
    jobs = sorted(merged.values(),
                  key=lambda j: (j.get("lastSeen", ""), j.get("id")), reverse=True)
    active_jobs = [j for j in jobs if j.get("active")]

    # 前端全量文件：只保留在招岗位 + 今日见到的岗位，控制体积
    payload_jobs = [j for j in jobs if j.get("active") or j.get("lastSeen") == today]

    new_today = sum(1 for j in jobs if j.get("firstSeen") == today)
    by_source = {}
    by_group = {}
    by_city = {}
    for j in active_jobs:
        by_source[j.get("sourceName", "其他")] = by_source.get(j.get("sourceName", "其他"), 0) + 1
        by_group[j.get("companyGroup", "其他")] = by_group.get(j.get("companyGroup", "其他"), 0) + 1
        by_city[j.get("city", "全国")] = by_city.get(j.get("city", "全国"), 0) + 1

    meta = {
        "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updateDate": today,
        "total": len(jobs),
        "activeTotal": len(active_jobs),
        "newToday": new_today,
        "bySource": dict(sorted(by_source.items(), key=lambda x: -x[1])),
        "byCompanyGroup": dict(sorted(by_group.items(), key=lambda x: -x[1])),
        "byCity": dict(sorted(by_city.items(), key=lambda x: -x[1])[:30]),
        "sourceStats": source_stats,
    }
    _write_json(os.path.join(DATA_DIR, "jobs.json"),
                {"meta": meta, "jobs": payload_jobs})

    # 每日归档（全量快照，含下线）
    _write_json(os.path.join(ARCHIVE_DIR, f"{today}.json"),
                {"meta": meta, "jobs": jobs})

    # 统计趋势
    stats = _read_json(os.path.join(DATA_DIR, "stats.json"), {"history": []})
    history = stats.get("history", [])
    history = [h for h in history if h.get("date") != today]
    history.append({"date": today, "active": len(active_jobs),
                    "new": new_today, "total": len(jobs)})
    history = history[-120:]
    stats["history"] = history
    _write_json(os.path.join(DATA_DIR, "stats.json"), stats)

    # 清理过期归档
    try:
        cutoff = time.time() - ARCHIVE_KEEP_DAYS * 86400
        for fn in os.listdir(ARCHIVE_DIR):
            fp = os.path.join(ARCHIVE_DIR, fn)
            if os.path.getmtime(fp) < cutoff:
                os.remove(fp)
    except OSError:
        pass

    return meta
