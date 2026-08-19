# 秋招情报站

> 央国企 / 互联网大厂秋招岗位信息聚合站 —— 全自动每日更新，无需本地运行任何程序。
>
> 数据来源：**国聘（央国企）**、**牛客网（校招职位 + 校招日程）**、**BOSS直聘（可选）**
>
> 纯静态部署：GitHub Actions 每日定时抓取 → 数据提交回仓库 → GitHub Pages 自动发布。

## 功能特性

| 模块 | 说明 |
|------|------|
| 数据采集 | 每日 2 次（北京时间 08:00 / 14:00）自动抓取国聘、牛客网等平台秋招岗位，含央国企专场 |
| 数据处理 | 清洗 + 结构化：岗位大类 / 公司性质 / 城市 / 学历 / 薪资（K·月薪数）标准化 |
| 前端展示 | 响应式界面：多维筛选（8 个维度）、关键词搜索、4 种排序、岗位详情、原始链接直达投递 |
| 增强功能 | 岗位收藏（本地持久化）、多岗位对比（最多 4 个，14 项字段对照表）、数据统计图表 |
| 更新机制 | GitHub Actions 定时任务 + 手动触发；增量合并去重，`今日新岗` / `即将截止` 自动标记 |
| 历史存储 | 每日全量快照归档 `docs/data/archive/`（保留 90 天），统计趋势保留 120 天 |
| 异常处理 | HTTP 请求自动重试（指数退避）；采集失败自动创建 GitHub Issue 告警，恢复后自动关闭 |

## 部署步骤（约 5 分钟）

### 1. 创建 GitHub 仓库并推送代码

```bash
cd JOB
git init
git add .
git commit -m "init: 秋招情报站"
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

### 2. 开启 GitHub Pages

仓库 **Settings → Pages → Build and deployment**：
- Source 选择 **Deploy from a branch**
- Branch 选择 **main**，目录选择 **/docs**
- 等待 1~2 分钟，访问 `https://<用户名>.github.io/<仓库名>/` 即可看到页面

### 3. 完成（可选配置）

- 定时任务默认已启用，无需任何配置；也可在 **Actions → 每日秋招数据采集 → Run workflow** 手动触发一次验证
- **可选**：抓取 BOSS直聘 需要有效 Cookie —— 仓库 **Settings → Secrets and variables → Actions → New repository secret**，名称 `ZHIPIN_COOKIE`，值为浏览器登录 BOSS直聘 后复制的完整 Cookie（含 `__zp_stoken__`）。不配置时该来源自动跳过，不影响其他来源

## 项目结构

```
JOB/
├── .github/workflows/scrape.yml   # 每日定时采集工作流（含告警与自动提交）
├── docs/                          # GitHub Pages 站点
│   ├── index.html                 # 单页应用入口
│   ├── assets/style.css           # 响应式样式
│   ├── assets/app.js              # 筛选/搜索/收藏/对比/统计逻辑
│   └── data/
│       ├── jobs.json              # 前端加载的全量岗位数据（含 meta 统计）
│       ├── stats.json             # 每日统计历史（趋势图）
│       └── archive/2026-08-19.json  # 每日全量快照
└── scraper/                       # Python 爬虫（标准库实现，零依赖）
    ├── main.py                    # 主入口：抓取→清洗→合并→存储→告警
    ├── http_client.py             # HTTP 客户端（重试+指数退避+超时）
    ├── signer.py                  # 国聘 API HMAC-SHA256 签名
    ├── processing.py              # 清洗与分类标准化
    ├── storage.py                 # 增量合并/归档/趋势统计
    ├── alerts.py                  # GitHub Issue 告警
    └── sources/
        ├── iguopin.py             # 国聘（央国企主来源）
        ├── nowcoder.py            # 牛客网（职位+校招日程）
        └── zhipin.py              # BOSS直聘（需 Cookie，可降级跳过）
```

## 本地运行（可选，无需部署）

```bash
cd scraper
python main.py          # 全量抓取，数据写入 docs/data/
# 然后任意静态服务器预览：
python -m http.server 8000 --directory ../docs
```

## 数据字段说明

| 字段 | 说明 |
|------|------|
| `categoryGroup` | 岗位大类：技术/IT、产品/设计、运营/市场、职能/行政、销售/商务、金融/投资、科研/教育、医疗/生物、制造/工程、供应链/物流、国企综合岗 |
| `companyGroup` | 公司性质：央国企 / 民营 / 外资 / 合资 / 事业单位 / 其他 |
| `salaryMin/Max/Months` | 标准化薪资（K/月）与薪资月数，支持区间筛选 |
| `isNew` / `active` | 今日新增标记 / 在招状态（14 天未抓到或已过截止日 → 下线） |
| `deadline` | 截止日期，剩余 ≤3 天前端红色高亮提醒 |

## 常见问题

- **页面数据多久更新？** 每天北京时间 08:00 / 14:00 各一次；页面顶部显示最近更新时间
- **为什么没有 BOSS直聘 数据？** BOSS直聘反爬严格（需登录态 `__zp_stoken__`），配置 `ZHIPIN_COOKIE` Secret 后自动启用；央国企岗位已由国聘覆盖
- **采集失败怎么办？** 查看仓库 Issues——失败时会自动创建带 `scrape-alert` 标签的告警 Issue，恢复后自动关闭；全部来源失败时 Actions 任务会标红并邮件通知
- **数据准确性？** 本站仅做聚合展示，薪资/岗位详情以「查看原岗位」链接的原始页面为准
