# -*- coding: utf-8 -*-
"""国聘(iguopin) API 签名生成器。

逆向自 www.iguopin.com 前端 main.js（模块 43260/27712）：
  dayKey = HmacSHA256(key=SECRET, msg="YYYYMMDD:floor(t/180)")
  sign   = HmacSHA256(key=dayKey,  msg="{t}|{nonce}|{METHOD}|{path}|pc")
其中日期使用北京时间（UTC+8），nonce 为 8 位 base36 随机串。
"""
import hashlib
import hmac
import random
import string
import time
from datetime import datetime, timedelta, timezone

SECRET = "cu4&dYe*feF8t$E9m"     # 模块 27712 导出的 MB 常量
SLICE = 180                       # 时间片长度（秒）
APP_VERSION = "5.2.300"

BEIJING_TZ = timezone(timedelta(hours=8))
_BASE36 = string.ascii_lowercase + string.digits


def _hmac_hex(key: str, msg: str) -> str:
    return hmac.new(key.encode("utf-8"), msg.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def make_headers(method: str, path: str) -> dict:
    """为指定请求生成带签名的请求头。path 形如 /api/jobs/v3/list（相对路径）"""
    t = int(time.time())
    nonce = "".join(random.choices(_BASE36, k=8))
    day = datetime.fromtimestamp(t, BEIJING_TZ).strftime("%Y%m%d")
    day_key = _hmac_hex(SECRET, f"{day}:{t // SLICE}")
    msg = f"{t}|{nonce}|{method.upper()}|{path}|pc"
    sign = _hmac_hex(day_key, msg)
    return {
        "Device": "pc",
        "Version": APP_VERSION,
        "Subsite": "iguopin",
        "Sign": sign,
        "T": str(t),
        "Nonce": nonce,
    }
