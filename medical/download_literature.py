#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
医学文献知识库下载器 —— 为"杏林大健康 AI 问答系统"构建 RAG 知识库来源。

从 6 个中文医学期刊 OA 官网, 按"与项目需求的相关性"筛选并下载文献:
  Phase A 发现(期次目录/站点地图) → Phase B 相关性打分与 Top-N 选择 → Phase C 下载 PDF、校验、提取全文文本、写 manifest.jsonl

用法:
  python download_literature.py                    # 全流程, 默认 80 篇
  python download_literature.py --phase discover   # 只跑发现, 刷新候选池
  python download_literature.py --phase download   # 用已有 selection 下载(断点续传)
  python download_literature.py --max 120          # 扩量到 120 篇
  python download_literature.py --journal chinagp,jpmed

断点续传: knowledge_base/manifest.jsonl 中已成功的文章自动跳过。
"""
import argparse
import json
import re
import sys
import time
import pathlib
from collections import Counter, defaultdict
from urllib.parse import urljoin

import requests

try:
    import pymupdf  # PyMuPDF
except ImportError:
    pymupdf = None

ROOT = pathlib.Path(__file__).resolve().parent
KB = ROOT / "knowledge_base"
CAND_FILE = KB / "candidates.jsonl"
SELECT_FILE = KB / "selection.jsonl"
MANIFEST_FILE = KB / "manifest.jsonl"

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

MIN_INTERVAL = 1.0          # 同一站点两次请求的最小间隔(秒), 礼貌抓取
RETRIES = 3
_last_hit = {}              # host -> monotonic time


def _throttle(url):
    host = url.split("/")[2]
    now = time.monotonic()
    last = _last_hit.get(host, 0.0)
    wait = MIN_INTERVAL - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


def fetch(session, url, binary=False, **kw):
    """带限速与重试的 GET。"""
    last_err = None
    for i in range(RETRIES):
        try:
            _throttle(url)
            r = session.get(url, timeout=45, **kw)
            if r.status_code == 200:
                if not binary:
                    r.encoding = "utf-8"
                return r
            last_err = f"HTTP {r.status_code}"
            if r.status_code in (403, 404):
                break
        except requests.RequestException as e:
            last_err = str(e)[:120]
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed {url} -> {last_err}")


def post(session, url, **kw):
    _throttle(url)
    r = session.post(url, timeout=45, **kw)
    r.encoding = "utf-8"
    return r


# ---------------------------------------------------------------- 相关性词典
# 需求文档 18 类固定问答 + 大众健康咨询高频疾病/维度
DISEASES = [
    "感冒", "上呼吸道感染", "流感", "咳嗽", "发热", "哮喘", "慢阻肺", "COPD", "肺炎", "支气管炎",
    "肺结节", "鼻炎", "高血压", "冠心病", "心律失常", "心衰", "心力衰竭", "血脂", "高脂血症",
    "动脉粥样硬化", "卒中", "中风", "糖尿病", "高尿酸", "痛风", "肥胖", "脂肪肝", "甲状腺",
    "甲亢", "甲减", "骨质疏松", "贫血", "胃炎", "胃溃疡", "消化性溃疡", "幽门螺杆菌", "便秘",
    "腹泻", "肠易激", "胃食管反流", "肝炎", "脂肪性肝病", "胆结石", "胆囊炎", "痔疮", "尿路感染",
    "肾结石", "前列腺", "月经", "痛经", "多囊卵巢", "失眠", "睡眠", "头痛", "偏头痛", "焦虑",
    "抑郁", "阿尔茨海默", "痴呆", "帕金森", "癫痫", "颈椎病", "腰椎", "腰痛", "关节炎",
    "骨关节炎", "肩周炎", "湿疹", "痤疮", "荨麻疹", "过敏", "变应性", "近视", "中耳炎", "龋齿",
    "手足口", "水痘", "肺癌", "乳腺癌", "胃癌", "结直肠癌", "肠癌", "肝癌", "食管癌", "甲状腺癌",
    "宫颈癌", "前列腺癌", "肌少症", "骨折", "慢性肾病", "银屑病", "维生素", "骨质疏松症",
    "肌少性肥胖", "衰老", "更年期", "儿童", "老年",
]
DIMS = [
    "症状", "病因", "预防", "疫苗", "筛查", "诊断", "鉴别", "治疗", "用药", "药物", "抗生素",
    "饮食", "膳食", "营养", "食物", "运动", "康复", "管理", "健康教育", "依从性", "随访",
    "并发症", "预后", "生活方式", "戒烟", "心理", "检查", "检验", "影像", "超重", "减重",
    "体重", "血压", "血糖", "自我管理", "社区",
]
TYPE_BOOST = {"综述": 4, "进展": 3, "指南": 5, "共识": 5, "Meta": 4, "meta": 4, "系统评价": 4,
              "循证": 3, "述评": 1, "现状": 1, "策略": 1, "健康教育": 2, "健康管理": 2}
NEGATIVE = ["细胞", "小鼠", "大鼠", "动物", "基因", "蛋白", "通路", "表达", "纳米", "分子",
            "信号", "转染", "凋亡", "自噬", "铁死亡", "载体", "材料", "测序", "突变", "机制"]


def score_text(text):
    """返回 (得分, 命中主题列表)。"""
    if not text:
        return 0, []
    hits = []
    s = 0
    d_hits = [w for w in DISEASES if w in text]
    m_hits = [w for w in DIMS if w in text]
    t_hits = [w for w in TYPE_BOOST if w in text]
    n_hits = [w for w in NEGATIVE if w in text]
    s += 2 * len(set(d_hits)) + 2 * len(set(m_hits))
    s += sum(TYPE_BOOST[w] for w in t_hits)
    s -= min(3, len(n_hits))
    topics = sorted(set(d_hits)) + ["#" + w for w in sorted(set(m_hits))]
    return s, topics


def year_bonus(year):
    if not year:
        return 0
    if year >= 2025:
        return 2
    if year == 2024:
        return 1
    if year < 2023:
        return -1
    return 0


# ---------------------------------------------------------------- 各刊发现
def _parse_magtech_issue(html, base, journal, issue_url):
    """Magtech 期次页: 文章链接为 /CN/10.xxxx/... DOI URL, 锚文本即标题。"""
    out = []
    for m in re.finditer(r'href="(https?://[^"]*?/CN/(10\.[^"]+))"[^>]*>([^<]{6,120})</a>', html):
        url, title = m.group(1), m.group(3).strip()
        if title and "全文" not in title and "PDF" not in title:
            out.append({"journal": journal, "title": title, "url": url,
                        "issue_url": issue_url, "source": "issue"})
    return out


def disc_chinagp(session, years):
    out = []
    for y in years:
        try:
            r = fetch(session, f"https://www.chinagp.net/CN/article/showTenYearVolumnDetail.do?nian={y}")
        except RuntimeError as e:
            print(f"  [chinagp] {y} 年份页失败: {e}")
            continue
        issues = []
        for m in re.finditer(r'href="(\.\./volumn/volumn_\d+\.shtml)"', r.text):
            u = urljoin("https://www.chinagp.net/CN/article/", m.group(1))
            if u not in issues:
                issues.append(u)
        print(f"  [chinagp] {y} 年 {len(issues)} 期")
        for iu in issues:
            try:
                ri = fetch(session, iu)
            except RuntimeError as e:
                print(f"    期次页失败 {iu}: {e}")
                continue
            out += _parse_magtech_issue(ri.text, "https://www.chinagp.net", "chinagp", iu)
    return out


def disc_pumc(session, n_issues=30):
    r = fetch(session, "https://jcyxylc.pumc.edu.cn/CN/article/showOldVolumn.do")
    issues = []
    for m in re.finditer(r'href="(\.\./volumn/volumn_\d+\.shtml)"', r.text):
        u = urljoin("https://jcyxylc.pumc.edu.cn/CN/article/", m.group(1))
        if u not in issues:
            issues.append(u)
    issues = issues[:n_issues]  # 过刊页按新到旧排序
    print(f"  [jcyxylc] 抓取最近 {len(issues)} 期")
    out = []
    for iu in issues:
        try:
            ri = fetch(session, iu)
        except RuntimeError as e:
            print(f"    期次页失败 {iu}: {e}")
            continue
        out += _parse_magtech_issue(ri.text, "https://jcyxylc.pumc.edu.cn", "jcyxylc", iu)
    return out


def disc_jpmed(session, years):
    r = fetch(session, "https://jpmed.qdu.edu.cn/CN/article/showOldVolumn.do")
    issues = []
    for m in re.finditer(r'href="(https://jpmed\.qdu\.edu\.cn/CN/Y(\d{4})/V\d+/I\d+)"', r.text):
        u, y = m.group(1), int(m.group(2))
        if y in years and u not in issues:
            issues.append(u)
    print(f"  [jpmed] 抓取 {len(issues)} 期")
    out = []
    for iu in issues:
        try:
            ri = fetch(session, iu)
        except RuntimeError as e:
            print(f"    期次页失败 {iu}: {e}")
            continue
        out += _parse_magtech_issue(ri.text, "https://jpmed.qdu.edu.cn", "jpmed", iu)
    return out


def disc_ebcm(session):
    r = fetch(session, "https://www.pangupress.com/sitemap/ebcm.xml")
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", r.text)
            if re.search(r"/journal/ebcm/\d+/\d+/\d+$", u)]
    print(f"  [ebcm] sitemap {len(urls)} 篇")
    out = []
    for u in urls:
        try:
            ra = fetch(session, u)
        except RuntimeError as e:
            print(f"    文章页失败 {u}: {e}")
            continue
        metas = citation_metas(ra.text)
        if metas.get("title"):
            out.append({"journal": "ebcm", "title": metas["title"], "url": u,
                        "authors": metas.get("authors", []),
                        "year": metas.get("year"), "doi": metas.get("doi"),
                        "pdf_url": metas.get("pdf_url"), "source": "sitemap"})
    return out


def disc_bmjj(session):
    base = "https://bmjj.cbpt.cnki.net"
    r = fetch(session, base + "/portal/journal/portal/client/index")
    html = r.text
    out, seen = [], set()
    for chunk in html.split('class="paperBox"')[1:]:
        m = re.search(r'href="' + base + r'/portal/journal/portal/client/paper/([0-9a-f]+)"[^>]*>([^<]{5,120})</a>', chunk)
        if not m:
            continue
        pid, title = m.group(1), m.group(2).strip()
        if pid in seen:
            continue
        seen.add(pid)
        a_m = re.search(r'<span>([^<]{2,80})</span>', chunk)
        abs_m = re.search(r"<p>(.{10,600}?)</p>", chunk, re.S)
        abstract = re.sub(r"<[^>]+>", "", abs_m.group(1)).strip() if abs_m else ""
        pdf_m = re.search(r"getSpecialPDFUrl\('([0-9a-f]+)'", chunk)
        out.append({"journal": "bmjj", "title": title, "url": f"{base}/portal/journal/portal/client/paper/{pid}",
                    "authors": [a.strip() for a in a_m.group(1).split(";") if a.strip()] if a_m else [],
                    "abstract": abstract, "content_id": pdf_m.group(1) if pdf_m else None,
                    "source": "index"})
    print(f"  [bmjj] 首页 {len(out)} 篇")
    return out


def disc_zsyk(session):
    """方正出版平台对所有非浏览器客户端返回 403(TLS指纹/JS挑战 WAF), 详见 KB_README.md。"""
    print("  [zsyk] 方正平台 WAF 拦截(403), 本版跳过 —— 见 KB_README.md 扩量说明")
    return []


# ---------------------------------------------------------------- 元数据与下载
def citation_metas(html):
    metas = defaultdict(list)
    for m in re.finditer(r'<meta name="citation_([^"]+)" content="([^"]*)"', html):
        metas[m.group(1)].append(m.group(2).strip())
    authors = []
    for a in metas.get("author", []):
        authors += [x.strip() for x in re.split(r"[;；,，]", a) if x.strip()]
    date = (metas.get("publication_date") or metas.get("online_date") or metas.get("date") or [""])[0]
    ym = re.match(r"(\d{4})", date)
    return {
        "title": (metas.get("title") or [""])[0],
        "authors": authors,
        "year": int(ym.group(1)) if ym else None,
        "volume": (metas.get("volume") or [""])[0],
        "issue": (metas.get("issue") or [""])[0],
        "doi": (metas.get("doi") or [""])[0],
        "pdf_url": (metas.get("pdf_url") or [""])[0],
    }


def safe_name(s, maxlen=36):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", s or "").strip("_")
    return s[:maxlen]


def pdf_ok(data):
    return data and len(data) > 50 * 1024 and data[:5] == b"%PDF-"


def resolve_pdf_url(session, art):
    """从文章页解析 citation_pdf_url (Magtech/pangupress)。"""
    r = fetch(session, art["url"])
    metas = citation_metas(r.text)
    pdf = metas.get("pdf_url") or ""
    if not pdf:
        m = re.search(r'(downloadArticleFile\.do\?attachType=PDF&id=\d+)', r.text)
        pdf = m.group(1) if m else ""
    if pdf and not pdf.startswith("http"):
        pdf = urljoin(art["url"], pdf)
    return metas, pdf


def bmjj_pdf_url(session, art):
    cid = art.get("content_id")
    if not cid:
        return None
    base = "https://bmjj.cbpt.cnki.net"
    try:
        r = post(session, f"{base}/portal/journal/portal/journal/api/getChinesDownloadInfoByEnglishPaper?contentId={cid}",
                 headers={"Referer": base + "/portal/journal/portal/client/index"})
        d = r.json().get("data") or {}
        return d.get("pdfUrl") or None
    except Exception:
        return None


def extract_text(pdf_path, meta):
    """返回 (全文文本, 字符数, 页数)。文本头部带元信息, 便于后续 RAG 切块时保留来源。"""
    if pymupdf is None:
        return None, 0, 0
    doc = pymupdf.open(str(pdf_path))
    parts = []
    head = [f"标题: {meta.get('title', '')}"]
    if meta.get("authors"):
        head.append("作者: " + ", ".join(meta["authors"][:8]))
    head.append(f"期刊: {meta.get('journal_name', '')} {meta.get('year') or ''}"
                f" 第{meta.get('volume') or '?'}卷 第{meta.get('issue') or '?'}期")
    if meta.get("doi"):
        head.append(f"DOI: {meta['doi']}")
    head.append(f"来源URL: {meta.get('source_url', '')}")
    parts.append("\n".join(head) + "\n\n")
    n = 0
    for page in doc:
        t = page.get_text()
        n += len(t)
        parts.append(t)
    n_pages = len(doc)
    doc.close()
    return "\n".join(parts), n, n_pages


# ---------------------------------------------------------------- 主流程
JOURNALS = {
    "chinagp": "中国全科医学",
    "jcyxylc": "基础医学与临床",
    "jpmed": "精准医学杂志",
    "ebcm": "临床医药循证研究",
    "bmjj": "巴楚医学",
    "zsyk": "中山大学学报(医学科学版)",
}
BASE_CAPS = {"chinagp": 30, "jcyxylc": 15, "jpmed": 12, "ebcm": 8, "bmjj": 5, "zsyk": 12}
BACKFILL = [("chinagp", 45), ("jcyxylc", 25), ("jpmed", 20), ("ebcm", 12), ("bmjj", 6)]


def load_jsonl(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def dump_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def phase_discover(session, journals):
    if CAND_FILE.exists():
        old = load_jsonl(CAND_FILE)
        print(f"发现阶段: 复用已有候选池 {len(old)} 条 (加 --refresh 重新抓取)")
        return old
    cands = []
    years = [2024, 2025, 2026]
    if "chinagp" in journals:
        cands += disc_chinagp(session, years)
    if "jcyxylc" in journals:
        cands += disc_pumc(session)
    if "jpmed" in journals:
        cands += disc_jpmed(session, years)
    if "ebcm" in journals:
        cands += disc_ebcm(session)
    if "bmjj" in journals:
        cands += disc_bmjj(session)
    if "zsyk" in journals:
        cands += disc_zsyk(session)
    # 去重
    seen, uniq = set(), []
    for c in cands:
        k = c["url"]
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    for c in uniq:
        s, t = score_text(c.get("title", "") + " " + c.get("abstract", ""))
        c["score"] = s + year_bonus(c.get("year"))
        c["topics"] = t
    dump_jsonl(CAND_FILE, uniq)
    print(f"发现阶段完成: 候选 {len(uniq)} 篇 -> {CAND_FILE.name}")
    return uniq


def phase_select(cands, target):
    ranked = sorted(cands, key=lambda c: -c.get("score", 0))
    caps = dict(BASE_CAPS)
    need = set(caps) - {c["journal"] for c in ranked}
    for j in need:
        caps.pop(j, None)
    sel, per = [], Counter()
    # 第一轮: 基础配额
    for c in ranked:
        j = c["journal"]
        if j in caps and per[j] < caps[j] and len(sel) < target:
            sel.append(c)
            per[j] += 1
    # 第二轮: 被跳过的刊的配额顺延
    cap_order = [j for j, _ in BACKFILL if j in caps]
    idx = 0
    while len(sel) < min(target, len(ranked)) and idx < 200:
        progressed = False
        for j in cap_order:
            if len(sel) >= target:
                break
            limit = dict(BACKFILL)[j]
            room = [c for c in ranked if c["journal"] == j and c not in sel]
            if per[j] < limit and room:
                sel.append(room[0])
                per[j] += 1
                progressed = True
        idx += 1
        if not progressed:
            break
    print("选择结果:")
    for j in JOURNALS:
        if per[j]:
            print(f"  {JOURNALS[j]:<18} {per[j]} 篇")
    print(f"  合计 {len(sel)} 篇")
    return sel


def phase_download(session, sel, target):
    done_keys = set()
    if MANIFEST_FILE.exists():
        for r in load_jsonl(MANIFEST_FILE):
            if r.get("status") == "ok":
                done_keys.add(r["source_url"])
    rows = []
    for i, art in enumerate(sel, 1):
        j = art["journal"]
        meta = {"journal": j, "journal_name": JOURNALS[j], "title": art.get("title", ""),
                "authors": art.get("authors", []), "year": art.get("year"),
                "volume": art.get("volume"), "issue": art.get("issue"),
                "doi": art.get("doi"), "source_url": art["url"],
                "score": art.get("score"), "topics": art.get("topics", [])}
        outdir = KB / j
        outdir.mkdir(parents=True, exist_ok=True)
        if art["url"] in done_keys:
            print(f"[{i}/{len(sel)}] 已存在, 跳过: {art['title'][:40]}")
            continue
        status, pdf_path, txt_path = "unknown", None, None
        chars = pages = 0
        try:
            if j == "bmjj":
                pdf = bmjj_pdf_url(session, art)
                if not pdf:
                    status = "no_free_pdf"
            else:
                metas, pdf = resolve_pdf_url(session, art)
                meta.update({"title": metas.get("title") or meta["title"],
                             "authors": metas.get("authors") or meta["authors"],
                             "year": metas.get("year") or meta["year"],
                             "volume": metas.get("volume") or meta["volume"],
                             "issue": metas.get("issue") or meta["issue"],
                             "doi": metas.get("doi") or meta["doi"]})
                if not pdf:
                    status = "no_pdf_link"
            if pdf:
                _throttle(pdf)
                r = session.get(pdf, timeout=120, headers={**UA, "Referer": art["url"]})
                if r.status_code == 200 and pdf_ok(r.content):
                    fname = f"{j}_{meta.get('year') or 'na'}_{safe_name(meta['title'])}"
                    pdf_path = outdir / (fname + ".pdf")
                    n = 1
                    while pdf_path.exists():
                        pdf_path = outdir / (f"{fname}_{n}.pdf")
                        n += 1
                    pdf_path.write_bytes(r.content)
                    txt, chars, pages = extract_text(pdf_path, meta)
                    if txt:
                        txt_path = pdf_path.with_suffix(".txt")
                        txt_path.write_text(txt, encoding="utf-8")
                    status = "ok"
                else:
                    status = "pdf_invalid"
        except RuntimeError as e:
            status = f"http_error: {str(e)[:60]}"
        except Exception as e:
            status = f"error: {str(e)[:60]}"
        meta.update({"status": status, "pdf_path": str(pdf_path.relative_to(ROOT)) if pdf_path else None,
                     "txt_path": str(txt_path.relative_to(ROOT)) if txt_path else None,
                     "pdf_bytes": pdf_path.stat().st_size if pdf_path and pdf_path.exists() else 0,
                     "text_chars": chars, "pages": pages})
        rows.append(meta)
        mark = "OK " if status == "ok" else "~~ "
        print(f"[{i}/{len(sel)}] {mark} {status:<14} {JOURNALS[j]} | {meta['title'][:42]}")
        with open(MANIFEST_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"下载阶段完成: 本次成功 {ok}/{len(rows)}")
    return rows


def write_report(manifest_rows):
    raw = load_jsonl(MANIFEST_FILE)
    # 按 source_url 去重, 保留最后一次尝试的状态
    latest = {}
    for r in raw:
        latest[r["source_url"]] = r
    all_rows = list(latest.values())
    ok_rows = [r for r in all_rows if r.get("status") == "ok"]
    per_j = Counter(r["journal"] for r in ok_rows)
    topics = Counter()
    for r in ok_rows:
        for t in r.get("topics") or []:
            if not t.startswith("#"):
                topics[t] += 1
    lines = [
        "# 医学文献知识库 (knowledge_base)",
        "",
        f"为《杏林大健康 AI 问答系统》构建的 RAG 起步语料。共收录 **{len(ok_rows)} 篇**文献, 每篇含 PDF 原文与提取文本(.txt),",
        "元数据见 `manifest.jsonl` (标题/作者/期刊/年卷期/DOI/来源URL/文件路径/相关性得分)。",
        "",
        "## 各刊收录统计",
        "",
        "| 期刊 | 收录篇数 | 说明 |",
        "|---|---|---|",
    ]
    notes = {"chinagp": "OA(2022起), 半月刊, 大众健康+慢病管理相关性最高",
             "jcyxylc": "官网免费全文, 基础+临床",
             "jpmed": "OA(2018起), 双月刊",
             "ebcm": "Gold OA, 2025年创刊",
             "bmjj": "2025年起OA, 但门户PDF接口对最新期返回空(跳转知网)",
             "zsyk": "方正平台 WAF 拦截所有非浏览器客户端(403), 本轮未收录"}
    for j, name in JOURNALS.items():
        lines.append(f"| {name} | {per_j.get(j, 0)} | {notes[j]} |")
    lines += ["", "## 主题覆盖分布 (按标题命中疾病统计, 前 30)", ""]
    for t, n in topics.most_common(30):
        lines.append(f"- {t}: {n} 篇")
    fails = [r for r in all_rows if r.get("status") not in ("ok",)]
    if fails:
        lines += ["", "## 未成功清单", ""]
        for r in fails:
            lines.append(f"- [{r['status']}] {JOURNALS.get(r['journal'], r['journal'])} | {r['title'][:50]} | {r['source_url']}")
    lines += [
        "",
        "## 扩量方法",
        "",
        "```",
        "python download_literature.py --max 300                    # 扩到300篇(自动顺延配额)",
        "python download_literature.py --max 300 --refresh          # 重新抓取候选池(更多年份)",
        "python download_literature.py --journal chinagp,jcyxylc --max 200",
        "```",
        "",
        "抓取策略: 仅抓取官网 OA/免费全文, 同站点请求间隔 >=1 秒, 支持断点续传(已成功文章自动跳过)。",
        "",
        "## 来源",
        "",
        "选题依据《02_医疗文献地址.pdf》所列 6 个 OA 期刊官网; 相关性标准依据《01_需求文档.pdf》",
        "第 8/9 章(18 类固定问答: 疾病-症状/病因/预防/治疗/药品/食品宜忌/检查/并发症等)与 14.8 节医学资料要求。",
    ]
    (KB / "KB_README.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写入 {KB / 'KB_README.md'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["discover", "select", "download", "all"], default="all")
    ap.add_argument("--max", type=int, default=80, help="目标篇数")
    ap.add_argument("--journal", default="chinagp,jcyxylc,jpmed,ebcm,bmjj,zsyk")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存候选池, 重新发现")
    args = ap.parse_args()
    KB.mkdir(exist_ok=True)
    if args.refresh and CAND_FILE.exists():
        CAND_FILE.unlink()
    journals = set(args.journal.split(","))

    s = requests.Session()
    s.headers.update(UA)

    if args.phase in ("discover", "all"):
        cands = phase_discover(s, journals)
    else:
        cands = load_jsonl(CAND_FILE)
        print(f"候选池: {len(cands)} 条")
    if args.phase == "discover":
        return

    if args.phase in ("select", "all"):
        sel = phase_select(cands, args.max)
        dump_jsonl(SELECT_FILE, sel)
    else:
        sel = load_jsonl(SELECT_FILE)
        print(f"已有选择: {len(sel)} 篇")
    if args.phase == "select":
        return

    if args.phase in ("download", "all"):
        rows = phase_download(s, sel, args.max)
        write_report(rows)


if __name__ == "__main__":
    main()
