# -*- coding: utf-8 -*-
"""秋招岗位信息聚合爬虫 —— 主入口

用法：python main.py [--days N]
流程：多源抓取 -> 清洗分类 -> 增量合并 -> 归档存储 -> 异常告警
"""
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Logger:
    def _ts(self):
        return time.strftime("%H:%M:%S")

    def info(self, msg):
        print(f"[{self._ts()}] INFO  {msg}", flush=True)

    def warn(self, msg):
        print(f"[{self._ts()}] WARN  {msg}", flush=True)

    def error(self, msg):
        print(f"[{self._ts()}] ERROR {msg}", flush=True)


def main():
    from sources import iguopin, nowcoder, zhipin
    from processing import process, sanitize_fields
    from storage import load_existing, merge, save
    import alerts

    log = Logger()
    today = date.today().isoformat()
    log.info(f"=== 秋招数据聚合开始 {today} ===")

    failures = []
    fresh = []
    source_stats = {}

    tasks = [
        ("国聘(央国企)", iguopin.crawl),
        ("牛客网-职位", nowcoder.crawl_jobs),
        ("牛客网-校招日程", nowcoder.crawl_schedule),
        ("BOSS直聘", zhipin.crawl),
    ]
    for name, fn in tasks:
        t0 = time.time()
        try:
            items = fn(log)
            fresh.extend(items)
            source_stats[name] = {"count": len(items),
                                  "seconds": round(time.time() - t0, 1),
                                  "ok": True}
            log.info(f"[{name}] 成功: {len(items)} 条, 耗时 {time.time()-t0:.1f}s")
        except Exception as e:
            failures.append((name, str(e)))
            source_stats[name] = {"count": 0, "ok": False, "error": str(e)}
            log.error(f"[{name}] 失败: {e}")

    if not fresh and failures:
        log.error("所有数据源均失败，数据未更新！")
        alerts.alert(failures, log)
        sys.exit(1)   # 全部失败时让 CI 明确报错

    # 清洗 + 分类
    valid = process(fresh, today, log)

    # 增量合并 + 存储（对全量数据做兜底规范化，修复历史遗留脏字段）
    existing = load_existing()
    merged, new_count = merge(existing, valid, today)
    for j in merged.values():
        sanitize_fields(j)
    meta = save(merged, today, source_stats)
    log.info(f"合并完成: 全量 {meta['total']} 条, 在招 {meta['activeTotal']} 条, "
             f"今日新增 {new_count} 条")

    # 告警 / 恢复关闭
    if failures:
        alerts.alert(failures, log)
    else:
        alerts.resolve_alerts(log)

    log.info("=== 完成 ===")


if __name__ == "__main__":
    main()
