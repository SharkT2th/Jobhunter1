# -*- coding: utf-8 -*-
"""数据处理：清洗、去噪、分类标准化（岗位大类 / 单位性质 / 城市）"""
import json
import re

# ---- 岗位大类映射（关键词 -> 大类），命中第一个即止 ----
CATEGORY_RULES = [
    ("技术/IT", ["后端", "前端", "软件", "开发", "算法", "测试", "运维", "大数据",
                 "人工智能", "AI", "机器学习", "数据", "网络", "安全", "嵌入式",
                 "硬件工程师", "通信", "计算机", "信息技术岗", "Java", "Java",
                 "C++", "Python", "Go", "程序员", "DBA", "架构"]),
    ("产品/设计", ["产品", "交互", "设计", "UI", "UX", "用研", "策划", "游戏策划"]),
    ("运营/市场", ["运营", "编辑", "内容", "新媒体", "市场", "营销", "推广", "品牌",
                   "公关", "广告", "增长"]),
    ("职能/行政", ["行政", "文秘", "人事", "人力资源", "HR", "财务", "会计", "审计",
                   "税务", "法务", "合规", "助理", "综合"]),
    ("销售/商务", ["销售", "商务", "客户", "渠道", "BD", "客户经理", "顾问", "售前"]),
    ("金融/投资", ["金融", "投资", "证券", "银行", "基金", "保险", "风控", "信贷",
                   "期货", "信托"]),
    ("科研/教育", ["科研", "博士后", "研究员", "教师", "教育", "课程", "讲师"]),
    ("医疗/生物", ["医生", "医师", "护士", "医疗", "药学", "临床", "生物", "医学"]),
    ("制造/工程", ["工艺", "制造", "机械", "电气", "自动化", "土木", "建筑", "施工",
                   "质量", "QC", "生产", "设备", "汽车", "焊接", "化工"]),
    ("供应链/物流", ["供应链", "物流", "仓储", "采购", "外贸", "跟单"]),
    ("国企综合岗", ["管培", "储备干部", "党校", "党务", "工会", "共青团", "文职",
                    "公职", "选调"]),
]

SOE_NATURES = {"国企", "央企", "国有企业", "国有控股", "事业单位", "国家机关",
               "中央企业", "国有独资"}
FOREIGN_NATURES = {"外商独资", "外企", "外国独资"}
JOINT_NATURES = {"中外合资", "合资", "港澳台投资", "中外合作"}
PRIVATE_NATURES = {"民营企业", "民营", "私企", "民办非企业"}


def classify_category(job):
    """根据原始岗位类别 + 职位名，归入统一岗位大类"""
    text = f"{job.get('jobCategory', '')} {job.get('title', '')}"
    for group, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw.lower() in text.lower():
                return group
    if job.get("entryType") == "schedule":
        return "校招日程"
    return "其他"


def classify_company(job):
    """单位性质归组：央国企 / 民营 / 外资 / 合资 / 事业单位 / 其他"""
    nature = (job.get("companyNature") or "").strip()
    if not nature:
        # 名称兜底：中字头/国字头公司大概率央国企
        name = job.get("company") or ""
        if name.startswith(("中国", "国家", "中信", "中铁", "中建", "中石油",
                            "中石化", "中海油", "中烟", "中船", "中航", "中核",
                            "国家电", "国网", "招商局")) or "集团" == name[-2:]:
            if name.startswith(("中国", "国家")):
                return "央国企"
        return "其他"
    if nature in SOE_NATURES:
        return "央国企"
    if nature in FOREIGN_NATURES:
        return "外资"
    if nature in JOINT_NATURES:
        return "合资"
    if nature in PRIVATE_NATURES:
        return "民营"
    if "事业" in nature or "机关" in nature:
        return "事业单位"
    if "上市" in nature or "股份" in nature:
        return "民营"
    return "其他"


def normalize_city(city):
    c = (city or "").strip()
    if not c:
        return "全国"
    # 多城市（"深圳,成都,武汉" / "北京、上海"）取第一个
    for sep in ("、", ",", "，", ";", "；", "/"):
        if sep in c:
            c = c.split(sep)[0].strip()
            break
    if c.endswith("市") and len(c) > 2:
        c = c[:-1]
    if c.endswith("地区") and len(c) > 3:
        c = c[:-2]
    return c or "全国"


DESC_KEYS = ("requirements", "description", "jobDescription", "infos")


def extract_desc(text):
    """ext 字段可能为 JSON 字符串，解析并提取正文；非 JSON 原样返回"""
    text = (text or "").strip()
    if not text.startswith("{"):
        return text[:500]
    try:
        obj = json.loads(text)
    except ValueError:
        # 截断的 JSON：宽松提取第一个长字符串值
        vals = re.findall(r'"((?:[^"\\]|\\.)*)"', text)
        for v in vals:
            if len(v) > 20:
                try:
                    return json.loads('"' + v + '"')[:500]
                except ValueError:
                    continue
        return ""
    if not isinstance(obj, dict):
        return ""
    for key in DESC_KEYS:
        if obj.get(key):
            return str(obj[key])[:500]
    for v in obj.values():            # 兜底：取第一个非空字符串值
        if isinstance(v, str) and v.strip():
            return v.strip()[:500]
    return ""


def sanitize_fields(job):
    """兜底规范化（处理历史遗留的脏数据，幂等）"""
    exp = job.get("experience")
    if isinstance(exp, dict):
        job["experience"] = (exp.get("expTag") or "").strip() or "应届"
    elif exp is None:
        job["experience"] = ""
    desc = job.get("desc")
    if isinstance(desc, str) and desc.strip().startswith("{"):
        job["desc"] = extract_desc(desc)
    return job


def clean(job, today):
    """清洗单条记录：补全派生字段、过滤无效数据。返回 None 表示丢弃"""
    if not job.get("title") or not job.get("company"):
        return None
    job["title"] = job["title"].strip()[:80]
    job["company"] = job["company"].strip()[:60]
    job["city"] = normalize_city(job.get("city"))
    job["categoryGroup"] = classify_category(job)
    job["companyGroup"] = classify_company(job)
    if job.get("companyGroup") == "央国企" and "央国企" not in job.get("tags", []):
        job.setdefault("tags", []).append("央国企")
    # 有效期：过期的岗位仍保留（便于历史检索），但打标记
    deadline = job.get("deadline") or ""
    job["expired"] = bool(deadline and deadline < today)
    return sanitize_fields(job)


def process(jobs, today, logger):
    valid, dropped = [], 0
    for j in jobs:
        c = clean(j, today)
        if c is None:
            dropped += 1
        else:
            valid.append(c)
    logger.info(f"数据处理: 有效 {len(valid)} 条，剔除 {dropped} 条无效数据")
    return valid
