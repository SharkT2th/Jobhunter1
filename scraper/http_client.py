# -*- coding: utf-8 -*-
"""HTTP 客户端：带重试、退避、超时控制（纯标准库实现，无第三方依赖）"""
import json
import random
import ssl
import time
import urllib.error
import urllib.request

# 统一的浏览器请求头，绕过基础 UA 检测
BASE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 宽松 SSL 上下文（部分站点证书链在 CI 环境可能不全）
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


class FetchError(Exception):
    """重试后仍失败的抓取异常"""


def fetch(url, *, method="GET", headers=None, data=None, form=None,
          timeout=20, retries=3, backoff=2.0, sleep=1.0, logger=None):
    """发起 HTTP 请求，失败自动重试（指数退避 + 抖动）。

    data: dict -> JSON body；form: dict -> x-www-form-urlencoded body
    返回解析后的 JSON；若响应非 JSON 返回原始文本。
    """
    hdrs = dict(BASE_HEADERS)
    if headers:
        hdrs.update(headers)

    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json;charset=UTF-8")
    elif form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        hdrs.setdefault("Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8")

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace")
                if not text:
                    raise FetchError("empty response")
                # WAF 拦截页识别：阿里云 WAF 返回 HTML 挑战页
                if text.lstrip()[:15].lower().startswith("<!doctype html") or \
                   "aliyun_waf_aa" in text[:4000]:
                    raise FetchError("blocked by WAF (html challenge page)")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        except FetchError as e:
            last_err = e
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                ConnectionError, OSError) as e:
            last_err = e

        if attempt < retries:
            wait = sleep * (backoff ** (attempt - 1)) + random.uniform(0, 0.8)
            if logger:
                logger.info(f"  重试 {attempt}/{retries - 1}：{last_err}，等待 {wait:.1f}s")
            time.sleep(wait)

    raise FetchError(f"{url} 抓取失败（重试{retries}次）: {last_err}")
