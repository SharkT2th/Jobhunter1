/* 秋招情报站 前端逻辑（纯原生JS，无依赖） */
(function () {
  "use strict";

  var PAGE_SIZE = 20;
  var MAX_COMPARE = 4;
  var LS_FAV = "qz_favs";
  var LS_CMP = "qz_compares";

  var state = {
    jobs: [],
    meta: {},
    stats: {},
    tab: "all",
    shown: PAGE_SIZE,
    // 筛选条件
    q: "",
    category: "", city: "", edu: "", company: "", type: "",
    salary: "", source: "", sort: "default",
    onlyNew: false, onlyActive: true, onlySoe: false
  };

  /* ---------- 工具 ---------- */
  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function lsGet(k, def) {
    try { return JSON.parse(localStorage.getItem(k)) || def; } catch (e) { return def; }
  }
  function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* 隐私模式忽略 */ } }
  function daysUntil(dstr) {
    if (!dstr) return null;
    var d = new Date(dstr + "T23:59:59");
    if (isNaN(d)) return null;
    return Math.ceil((d - Date.now()) / 86400000);
  }

  var favs = lsGet(LS_FAV, []);
  var compares = lsGet(LS_CMP, []);
  var favSet = {}; favs.forEach(function (id) { favSet[id] = 1; });
  var cmpSet = {}; compares.forEach(function (id) { cmpSet[id] = 1; });

  /* ---------- 数据加载 ---------- */
  function load() {
    var nocache = "?t=" + Date.now();
    var p1 = fetch("data/jobs.json" + nocache).then(function (r) { return r.json(); });
    var p2 = fetch("data/stats.json" + nocache).then(function (r) { return r.json(); }).catch(function () { return {}; });
    Promise.all([p1, p2]).then(function (arr) {
      state.jobs = (arr[0] && arr[0].jobs) || [];
      state.meta = (arr[0] && arr[0].meta) || {};
      state.stats = arr[1] || {};
      initFilters();
      renderHeader();
      render();
    }).catch(function (e) {
      $("resultCount").textContent = "数据加载失败，请刷新重试";
      $("jobList").innerHTML = "";
      console.error(e);
    });
  }

  /* ---------- 头部统计 ---------- */
  function renderHeader() {
    var m = state.meta;
    var soeCount = state.jobs.filter(function (j) { return j.companyGroup === "央国企"; }).length;
    $("headerStats").innerHTML =
      '<div class="h-stat"><b>' + (m.activeTotal != null ? m.activeTotal : state.jobs.length) + "</b><span>在招岗位</span></div>" +
      '<div class="h-stat"><b>' + (m.newToday != null ? m.newToday : "-") + "</b><span>今日新增</span></div>" +
      '<div class="h-stat"><b>' + soeCount + "</b><span>央国企</span></div>" +
      '<div class="h-stat"><b>' + (m.total != null ? m.total : state.jobs.length) + "</b><span>历史累计</span></div>";

    var d = m.updateDate || "";
    var isToday = d === new Date().toISOString().slice(0, 10);
    var time = m.updatedAt || d;
    $("updateBanner").innerHTML = '<span class="dot"></span>' +
      (isToday ? "今日已更新 · " : "") + "数据更新于 " + esc(time) +
      " · 每日自动同步国聘/牛客等平台 · <a href='javascript:void(0)' onclick='APP.goStats()'>查看更新趋势 →</a>";
  }

  /* ---------- 筛选器初始化 ---------- */
  function fillSelect(id, values, unit) {
    var sel = $(id);
    var first = sel.options[0];
    sel.innerHTML = "";
    sel.appendChild(first);
    values.forEach(function (v) {
      var o = document.createElement("option");
      o.value = v[0];
      o.textContent = v[1] + (unit || "") + (v[2] ? " (" + v[2] + ")" : "");
      sel.appendChild(o);
    });
  }

  function initFilters() {
    function counter(key) {
      var map = {};
      state.jobs.forEach(function (j) {
        var v = (j[key] || "").trim();
        if (v) map[v] = (map[v] || 0) + 1;
      });
      return Object.keys(map).map(function (k) { return [k, k, map[k]]; })
        .sort(function (a, b) { return b[2] - a[2]; });
    }
    fillSelect("fCategory", counter("categoryGroup"));
    fillSelect("fCity", counter("city"));
    fillSelect("fEdu", counter("education"));
    fillSelect("fCompany", counter("companyGroup"));
    fillSelect("fType", counter("recruitType"));
    fillSelect("fSource", counter("sourceName"));
  }

  /* ---------- 过滤 + 排序 ---------- */
  function salaryMatch(j) {
    if (!state.salary) return true;
    var parts = state.salary.split("-");
    var lo = +parts[0], hi = +parts[1];
    if (lo === 0 && hi === 10) return j.salaryMax != null && j.salaryMax < 10;
    var mn = j.salaryMin, mx = j.salaryMax;
    if (mn == null && mx == null) return false;
    if (mn == null) mn = 0;
    if (mx == null) mx = 999;
    return mn <= hi && mx >= lo;
  }

  function filtered() {
    var q = state.q.trim().toLowerCase();
    var list = state.jobs.filter(function (j) {
      if (state.onlyActive && !j.active) return false;
      if (state.onlyNew && !j.isNew) return false;
      if (state.onlySoe && j.companyGroup !== "央国企") return false;
      if (state.category && j.categoryGroup !== state.category) return false;
      if (state.city && j.city !== state.city) return false;
      if (state.edu && j.education !== state.edu) return false;
      if (state.company && j.companyGroup !== state.company) return false;
      if (state.type && j.recruitType !== state.type) return false;
      if (state.source && j.sourceName !== state.source) return false;
      if (!salaryMatch(j)) return false;
      if (q) {
        var hay = (j.title + " " + j.company + " " + (j.jobCategory || "") + " " +
          (j.industry || "") + " " + (j.desc || "") + " " + j.city).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });

    var s = state.sort;
    list.sort(function (a, b) {
      if (s === "salary") {
        var ba = a.salaryMax || 0, bb = b.salaryMax || 0;
        return bb - ba;
      }
      if (s === "new") return (b.publishDate || "").localeCompare(a.publishDate || "");
      if (s === "deadline") {
        var da = a.deadline ? (a.deadline + (a.active ? "0" : "9")) : "9999";
        var db = b.deadline ? (b.deadline + (b.active ? "0" : "9")) : "9999";
        return da.localeCompare(db);
      }
      // 默认：在招 > 今日新 > 新发布
      if (!!a.active !== !!b.active) return a.active ? -1 : 1;
      if (!!a.isNew !== !!b.isNew) return a.isNew ? -1 : 1;
      return (b.publishDate || "").localeCompare(a.publishDate || "");
    });
    return list;
  }

  function favList() {
    return state.jobs.filter(function (j) { return favSet[j.id]; });
  }

  /* ---------- 渲染列表 ---------- */
  function cardHTML(j) {
    var initial = esc((j.company || "?").charAt(0));
    var logo = j.logo
      ? '<img class="comp-logo" src="' + esc(j.logo) + '" alt="" loading="lazy" data-initial="' + initial + '" onerror="logoErr(this)">'
      : '<div class="comp-logo">' + initial + "</div>";

    var tags = (j.tags || []).slice(0, 4).map(function (t) {
      var cls = "";
      if (t === "央国企") cls = "t-soe";
      else if (j.isNew && t === "校招") cls = "t-new";
      else if (t === "实习") cls = "t-intern";
      else if (t === "校招日程") cls = "t-schedule";
      return '<span class="tag ' + cls + '">' + esc(t) + "</span>";
    }).join("");
    if (j.isNew && (j.tags || []).indexOf("今日新") === -1) {
      tags += '<span class="tag t-new">今日新</span>';
    }

    var dl = daysUntil(j.deadline);
    var dlTxt = j.deadline ? (dl != null && dl < 0 ? "已截止" :
      dl != null && dl <= 3 ? "仅剩" + dl + "天" : j.deadline + " 截止") : "";
    var dlCls = dl != null && dl >= 0 && dl <= 3 ? "deadline-soon" : "";

    var meta = "";
    function mi(icon, text, cls) {
      return text ? '<span class="m-item ' + (cls || "") + '">' + icon + esc(text) + "</span>" : "";
    }
    var icoLoc = '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M12 2C8.1 2 5 5.1 5 9c0 5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>';
    var icoEdu = '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M12 3L1 9l11 6 9-4.9V17h2V9L12 3zM5 13.2v3.3c0 1.9 3.1 3.5 7 3.5s7-1.6 7-3.5v-3.3l-7 3.8-7-3.8z"/></svg>';
    var icoExp = '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M20 6h-4V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2H4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2zM10 4h4v2h-4V4z"/></svg>';
    var icoDl = '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 10.6l4 2.3-1 1.7-5-2.9V6h2v6.6z"/></svg>';

    meta += mi(icoLoc, j.district || j.city);
    meta += mi(icoEdu, j.education);
    meta += mi(icoExp, j.experience);
    if (j.graduationYear) meta += '<span class="m-item">' + esc(j.graduationYear) + "</span>";
    meta += mi(icoDl, dlTxt, dlCls);

    var salary = j.salaryText
      ? '<div class="job-salary">' + esc(j.salaryText) + "</div>" : "";
    var desc = j.desc ? '<div class="job-desc">' + esc(j.desc) + "</div>" : "";

    return '<div class="job-card' + (j.active === false ? " expired" : "") + '">' +
      logo +
      '<div class="job-main">' +
        '<div class="job-title-row">' +
          '<span class="job-title" data-detail="' + esc(j.id) + '">' + esc(j.title) + "</span>" + tags +
        "</div>" +
        '<div class="job-company"><b>' + esc(j.company) + "</b>" +
          (j.industry ? " · " + esc(j.industry) : "") +
          (j.companyGroup && j.companyGroup !== "其他" ? " · " + esc(j.companyGroup) : "") + "</div>" +
        '<div class="job-meta">' + meta + "</div>" +
        desc +
      "</div>" +
      '<div class="job-side">' + salary +
        '<div class="card-actions">' +
          '<button class="icon-btn' + (favSet[j.id] ? " active" : "") + '" title="收藏" data-fav="' + esc(j.id) + '">' +
            '<svg viewBox="0 0 24 24" width="15" height="15"><path fill="currentColor" d="M12 17.3l-6.2 3.7 1.7-7L2 9.2l7.1-.6L12 2l2.9 6.6 7.1.6-5.5 4.8 1.7 7z"/></svg></button>' +
          '<button class="icon-btn cmp' + (cmpSet[j.id] ? " active" : "") + '" title="对比" data-cmp="' + esc(j.id) + '">' +
            '<svg viewBox="0 0 24 24" width="15" height="15"><path fill="currentColor" d="M3 3h8v18H3V3zm10 0h8v18h-8V3z"/></svg></button>' +
        "</div>" +
      "</div>" +
    "</div>";
  }

  function render() {
    var isFav = state.tab === "fav";
    $("favModeTip").hidden = !isFav;
    $("filters").style.opacity = isFav ? ".45" : "";
    $("filters").style.pointerEvents = isFav ? "none" : "";

    var list = isFav ? favList() : filtered();
    state.shown = Math.min(state.shown, Math.max(list.length, PAGE_SIZE));

    $("resultCount").innerHTML = isFav
      ? "已收藏 <b>" + list.length + "</b> 个岗位"
      : "共筛选出 <b>" + list.length + "</b> 个岗位";

    var slice = list.slice(0, state.shown);
    $("jobList").innerHTML = slice.map(cardHTML).join("");
    $("emptyBox").hidden = list.length !== 0;
    $("loadMore").hidden = state.shown >= list.length;
    $("loadMore").textContent = "加载更多（剩余 " + (list.length - state.shown) + " 条）";

    $("favCount").textContent = favs.length;
    renderCompareBar();
  }

  /* ---------- 统计视图 ---------- */
  function barsHTML(counter, color) {
    var max = counter[0] ? counter[0][2] : 1;
    return counter.slice(0, 10).map(function (c) {
      return '<div class="bar-row">' +
        '<span class="bar-label" title="' + esc(c[1]) + '">' + esc(c[1]) + "</span>" +
        '<div class="bar-track"><div class="bar-fill" style="width:' + (c[2] / max * 100) + "%; " + (color || "") + '"></div></div>' +
        '<span class="bar-val">' + c[2] + "</span></div>";
    }).join("") || '<p style="color:var(--text-3);font-size:13px">暂无数据</p>';
  }

  function renderStats() {
    var active = state.jobs.filter(function (j) { return j.active !== false; });
    function counter(key) {
      var map = {};
      active.forEach(function (j) {
        var v = (j[key] || "").trim();
        if (v) map[v] = (map[v] || 0) + 1;
      });
      return Object.keys(map).map(function (k) { return [k, k, map[k]]; }).sort(function (a, b) { return b[2] - a[2]; });
    }
    $("chartCategory").innerHTML = barsHTML(counter("categoryGroup"));
    $("chartCity").innerHTML = barsHTML(counter("city"));
    $("chartCompany").innerHTML = barsHTML(counter("companyGroup"));
    $("chartSource").innerHTML = barsHTML(counter("sourceName"));
    $("chartType").innerHTML = barsHTML(counter("recruitType"));

    // 趋势图（近30天）
    var hist = (state.stats.history || []).slice(-30);
    var maxN = 1;
    hist.forEach(function (h) { if (h.new > maxN) maxN = h.new; });
    $("chartTrend").innerHTML = hist.map(function (h) {
      var hpx = Math.max(6, Math.round(h.new / maxN * 120));
      return '<div class="trend-col"><span class="trend-num">' + h.new + "</span>" +
        '<div class="trend-bar" style="height:' + hpx + 'px" title="' + h.date + " 新增 " + h.new + " / 在招 " + h.active + '"></div>' +
        '<span class="trend-date">' + h.date.slice(5) + "</span></div>";
    }).join("") || '<p style="color:var(--text-3);font-size:13px">暂无历史数据，明天更新后可见</p>';

    // 数据源状态
    var ss = state.meta.sourceStats || {};
    $("sourceStatus").innerHTML = Object.keys(ss).map(function (k) {
      var v = ss[k];
      return '<div class="src-item"><div><div class="src-name">' + esc(k) + "</div>" +
        '<div class="src-info">' + (v.count || 0) + " 条 · " + (v.seconds || 0) + "s</div></div>" +
        '<span class="' + (v.ok ? "src-ok" : "src-bad") + '">' + (v.ok ? "正常" : "异常") + "</span></div>";
    }).join("") || '<p style="color:var(--text-3);font-size:13px">暂无采集记录</p>';
  }

  /* ---------- 收藏 / 对比 ---------- */
  function toggleFav(id) {
    if (favSet[id]) { delete favSet[id]; favs = favs.filter(function (x) { return x !== id; }); }
    else { favSet[id] = 1; favs.push(id); }
    lsSet(LS_FAV, favs);
    render();
  }

  function toggleCompare(id) {
    if (cmpSet[id]) {
      delete cmpSet[id];
      compares = compares.filter(function (x) { return x !== id; });
    } else {
      if (compares.length >= MAX_COMPARE) {
        toast("最多同时对比 " + MAX_COMPARE + " 个岗位");
        return;
      }
      cmpSet[id] = 1; compares.push(id);
    }
    lsSet(LS_CMP, compares);
    render();
  }

  function renderCompareBar() {
    $("compareBar").hidden = compares.length === 0;
    $("compareItems").innerHTML = compares.map(function (id) {
      var j = byId(id);
      var name = j ? j.title : id;
      return '<div class="cmp-chip"><span>' + esc(name) + "</span>" +
        '<button data-cmp="' + esc(id) + '" title="移除">✕</button></div>';
    }).join("");
    $("doCompare").disabled = compares.length < 2;
    $("doCompare").textContent = compares.length < 2
      ? "再选 " + (2 - compares.length) + " 个可对比" : "开始对比（" + compares.length + "）";
  }

  function byId(id) {
    for (var i = 0; i < state.jobs.length; i++) if (state.jobs[i].id === id) return state.jobs[i];
    return null;
  }

  /* ---------- 详情弹窗 ---------- */
  function openDetail(id) {
    var j = byId(id);
    if (!j) return;
    var dl = daysUntil(j.deadline);
    function item(label, val) {
      return val ? '<div class="d-item"><div class="dl">' + label + '</div><div class="dv">' + esc(val) + "</div></div>" : "";
    }
    var logo = j.logo
      ? '<img class="comp-logo" style="width:56px;height:56px" src="' + esc(j.logo) + '" data-initial="' + esc((j.company || "?").charAt(0)) + '" onerror="logoErr(this)">'
      : "";
    $("detailContent").innerHTML =
      '<div class="d-top">' + logo +
        '<div><div class="d-title">' + esc(j.title) + "</div>" +
        '<div class="d-company">' + esc(j.company) + (j.industry ? " · " + esc(j.industry) : "") + "</div>" +
        (j.salaryText ? '<div class="d-salary">' + esc(j.salaryText) + "</div>" : "") +
        '<div class="d-tags">' + (j.tags || []).concat(j.companyGroup && j.companyGroup !== "其他" ? [j.companyGroup] : [])
          .map(function (t) { return '<span class="tag">' + esc(t) + "</span>"; }).join("") + "</div>" +
      "</div></div>" +
      '<div class="d-grid">' +
        item("工作地点", j.district || j.city) +
        item("学历要求", j.education) +
        item("经验要求", j.experience) +
        item("招聘类型", j.recruitType) +
        item("毕业届别", j.graduationYear) +
        item("岗位大类", j.categoryGroup) +
        item("单位性质", j.companyNature || j.companyGroup) +
        item("数据来源", j.sourceName) +
        item("发布日期", j.publishDate) +
        item("截止时间", j.deadline ? j.deadline + (dl != null && dl >= 0 ? "（剩" + dl + "天）" : "（已截止）") : "") +
        item("首次收录", j.firstSeen) +
        item("最近更新", j.lastSeen) +
      "</div>" +
      (j.desc ? '<h3 style="font-size:15px;margin:10px 0 8px">职位描述</h3><div class="d-desc">' + esc(j.desc) + "</div>" : "") +
      '<div class="d-links">' +
        '<a class="btn-primary" href="' + esc(j.link) + '" target="_blank" rel="noopener">查看原岗位 & 投递 ↗</a>' +
        (j.applyLink ? '<a class="btn-ghost" href="' + esc(j.applyLink) + '" target="_blank" rel="noopener">直达网申</a>' : "") +
      "</div>";
    $("detailModal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  /* ---------- 对比弹窗 ---------- */
  function openCompare() {
    if (compares.length < 2) return;
    var jobs = compares.map(byId).filter(Boolean);
    var rows = [
      ["职位名称", function (j) { return "<b>" + esc(j.title) + "</b>"; }],
      ["公司", function (j) { return esc(j.company); }],
      ["薪资", function (j) {
        return j.salaryText ? '<span class="val-hl">' + esc(j.salaryText) + "</span>" : "面议";
      }],
      ["城市", function (j) { return esc(j.district || j.city || "-"); }],
      ["学历", function (j) { return esc(j.education || "-"); }],
      ["经验", function (j) { return esc(j.experience || "-"); }],
      ["招聘类型", function (j) { return esc(j.recruitType || "-"); }],
      ["毕业届别", function (j) { return esc(j.graduationYear || "-"); }],
      ["岗位大类", function (j) { return esc(j.categoryGroup || "-"); }],
      ["单位性质", function (j) { return esc(j.companyNature || j.companyGroup || "-"); }],
      ["行业", function (j) { return esc(j.industry || "-"); }],
      ["发布日期", function (j) { return esc(j.publishDate || "-"); }],
      ["截止时间", function (j) { return esc(j.deadline || "长期"); }],
      ["原始链接", function (j) { return '<a href="' + esc(j.link) + '" target="_blank" rel="noopener">打开 ↗</a>'; }]
    ];
    var html = "<thead><tr><th></th>" +
      jobs.map(function (j) { return "<th>" + esc(j.title) + "<br><span style='font-weight:400;font-size:12px'>" + esc(j.company) + "</span></th>"; }).join("") +
      "</tr></thead><tbody>";
    rows.forEach(function (r) {
      html += "<tr><th>" + r[0] + "</th>" + jobs.map(function (j) { return "<td>" + r[1](j) + "</td>"; }).join("") + "</tr>";
    });
    html += "</tbody>";
    $("compareTable").innerHTML = html;
    $("compareModal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeModal(id) {
    $(id).hidden = true;
    document.body.style.overflow = "";
  }

  /* ---------- 轻提示 ---------- */
  var toastTimer = null;
  function toast(msg) {
    var t = document.createElement("div");
    t.textContent = msg;
    t.style.cssText = "position:fixed;top:20px;left:50%;transform:translateX(-50%);background:rgba(31,36,48,.9);color:#fff;padding:9px 20px;border-radius:10px;font-size:14px;z-index:999;animation:pop .2s";
    document.body.appendChild(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.remove(); }, 2200);
  }

  /* ---------- 事件绑定 ---------- */
  function bind() {
    // 搜索（回车/防抖）
    var debounce = null;
    $("searchInput").addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        state.q = $("searchInput").value;
        state.shown = PAGE_SIZE;
        render();
      }, 260);
    });
    $("clearSearch").addEventListener("click", function () {
      $("searchInput").value = "";
      state.q = "";
      state.shown = PAGE_SIZE;
      render();
    });

    // 下拉筛选
    [["fCategory", "category"], ["fCity", "city"], ["fEdu", "edu"], ["fCompany", "company"],
     ["fType", "type"], ["fSalary", "salary"], ["fSource", "source"], ["fSort", "sort"]].forEach(function (p) {
      $(p[0]).addEventListener("change", function () {
        state[p[1]] = this.value;
        state.shown = PAGE_SIZE;
        render();
      });
    });

    // 快捷开关
    [["onlyNew", "onlyNew"], ["onlyActive", "onlyActive"], ["onlySoe", "onlySoe"]].forEach(function (p) {
      $(p[0]).addEventListener("change", function () {
        state[p[1]] = this.checked;
        state.shown = PAGE_SIZE;
        render();
      });
    });

    $("resetFilters").addEventListener("click", resetFilters);
    $("loadMore").addEventListener("click", function () {
      state.shown += PAGE_SIZE;
      render();
    });

    // Tab
    $("tabs").addEventListener("click", function (e) {
      var btn = e.target.closest(".tab");
      if (!btn) return;
      switchTab(btn.dataset.tab);
    });

    // 列表事件委托（收藏/对比/详情）
    $("jobList").addEventListener("click", function (e) {
      var favBtn = e.target.closest("[data-fav]");
      if (favBtn) { toggleFav(favBtn.dataset.fav); return; }
      var cmpBtn = e.target.closest("[data-cmp]");
      if (cmpBtn) { toggleCompare(cmpBtn.dataset.cmp); return; }
      var title = e.target.closest("[data-detail]");
      if (title) openDetail(title.dataset.detail);
    });

    // 对比栏
    $("compareItems").addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-cmp]");
      if (btn) toggleCompare(btn.dataset.cmp);
    });
    $("doCompare").addEventListener("click", openCompare);
    $("clearCompare").addEventListener("click", function () {
      compares = []; cmpSet = {};
      lsSet(LS_CMP, compares);
      render();
    });

    // 弹窗关闭
    document.querySelectorAll("[data-close]").forEach(function (el) {
      el.addEventListener("click", function () { closeModal(el.dataset.close); });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { closeModal("detailModal"); closeModal("compareModal"); }
    });
  }

  function switchTab(tab) {
    state.tab = tab;
    document.querySelectorAll(".tab").forEach(function (t) {
      t.classList.toggle("active", t.dataset.tab === tab);
    });
    $("listView").hidden = tab === "stats";
    $("statsView").hidden = tab !== "stats";
    $("statsView").id = "statsView";
    if (tab === "stats") renderStats();
    else { state.shown = PAGE_SIZE; render(); }
    window.scrollTo({ top: 0 });
  }

  function resetFilters() {
    state.q = ""; state.category = ""; state.city = ""; state.edu = "";
    state.company = ""; state.type = ""; state.salary = ""; state.source = "";
    state.sort = "default"; state.onlyNew = false; state.onlyActive = true; state.onlySoe = false;
    $("searchInput").value = "";
    ["fCategory", "fCity", "fEdu", "fCompany", "fType", "fSalary", "fSource"].forEach(function (id) { $(id).value = ""; });
    $("fSort").value = "default";
    $("onlyNew").checked = false; $("onlyActive").checked = true; $("onlySoe").checked = false;
    state.shown = PAGE_SIZE;
    if (state.tab === "fav") switchTab("all");
    else render();
  }

  /* ---------- 对外接口 ---------- */
  window.APP = {
    resetAll: resetFilters,
    goStats: function () { switchTab("stats"); window.scrollTo({ top: 0 }); }
  };
  window.logoErr = function (img) {
    var d = document.createElement("div");
    d.className = "comp-logo";
    d.textContent = img.dataset.initial || "?";
    if (img.parentNode) img.parentNode.replaceChild(d, img);
  };

  // 支持 URL 参数 ?q=xxx
  var urlQ = new URLSearchParams(location.search).get("q");
  if (urlQ) { state.q = urlQ; }

  bind();
  load();
})();
