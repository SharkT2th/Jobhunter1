# -*- coding: utf-8 -*-
"""异常报警：抓取失败时自动创建/更新 GitHub Issue。

依赖环境变量（GitHub Actions 自动注入 GITHUB_TOKEN）：
  GITHUB_TOKEN   仓库令牌（contents/issue 权限）
  GITHUB_REPOSITORY  形如 owner/repo，Actions 自动注入
本地运行时若无这两个变量则仅打印告警日志。
"""
import json
import os
import urllib.request

from http_client import BASE_HEADERS


def _api(url, payload=None, method="GET"):
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = dict(BASE_HEADERS)
    headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def alert(failures, logger):
    """failures: [(source_name, error_message)]，创建 Issue 或追加评论"""
    if not failures:
        return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not repo or not token:
        logger.warn("告警（本地模式，未配置 GITHUB_TOKEN/GITHUB_REPOSITORY，"
                    "跳过 Issue 创建）:")
        for name, err in failures:
            logger.warn(f"  [{name}] {err}")
        return

    title = "【数据采集异常】部分数据源抓取失败"
    lines = ["以下数据源在定时抓取中失败，请检查接口变更或反爬策略：", ""]
    for name, err in failures:
        lines.append(f"- **{name}**: `{err}`")
    lines += ["", "_本 Issue 由每日自动抓取任务创建，恢复后将自动关闭。_"]
    body = "\n".join(lines)

    # 查找已存在的打开告警 Issue（按标签）
    label = "scrape-alert"
    issues = _api(f"https://api.github.com/repos/{repo}/issues?"
                  f"labels={label}&state=open")
    existing = None
    if isinstance(issues, list):
        for it in issues:
            if "数据采集异常" in (it.get("title") or ""):
                existing = it
                break

    if existing:
        _api(f"https://api.github.com/repos/{repo}/issues/"
             f"{existing['number']}/comments", {"body": body}, "POST")
        logger.info(f"告警已追加到 Issue #{existing['number']}")
    else:
        result = _api(f"https://api.github.com/repos/{repo}/issues",
                      {"title": title, "body": body, "labels": [label]}, "POST")
        if result and result.get("number"):
            logger.info(f"已创建告警 Issue #{result['number']}: {result.get('html_url')}")
        else:
            logger.warn("告警 Issue 创建失败（检查 Token 权限）")


def resolve_alerts(logger):
    """全部数据源恢复正常时，关闭打开的告警 Issue"""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not repo or not token:
        return
    issues = _api(f"https://api.github.com/repos/{repo}/issues?"
                  f"labels=scrape-alert&state=open")
    if not isinstance(issues, list) or not issues:
        return
    for it in issues:
        if "数据采集异常" in (it.get("title") or ""):
            _api(f"https://api.github.com/repos/{repo}/issues/"
                 f"{it['number']}", {"state": "closed"}, "PATCH")
            logger.info(f"数据源已恢复，关闭告警 Issue #{it['number']}")
