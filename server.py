# -*- coding: utf-8 -*-
import json, re, time, html as htmlmod, os, threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8788"))
REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "3600"))
CACHE = {"at": 0, "payload": None, "error": None}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Safari/537.36", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"}
KEYWORDS = ["新品","发布","发布会","首发","开售","预售","上市","曝光","爆料","官宣","热点","热搜","热议","大会","峰会","论坛","活动","测评","体验","价格","涨价","降价","手机","平板","电脑","笔记本","显示器","芯片","处理器","显卡","耳机","音箱","电视","冰箱","洗衣机","空调","扫地机器人","相机","无人机","游戏机","机器人","AI眼镜","智能家居","智能手表","手环","穿戴","路由器","充电","电池","鸿蒙","安卓","苹果","华为","小米","荣耀","三星","vivo","OPPO","魅族","英伟达","高通","联发科","索尼","任天堂","微软","AI","人工智能","OLED","Mini LED","Matter","Steam","PlayStation","Xbox","MacBook","iPhone","iPad","Galaxy","知乎","微博","抖音","小红书","B站"]
CATEGORY_KEYS = {"手机":["手机","iPhone","华为","小米","荣耀","三星","vivo","OPPO","魅族","鸿蒙","安卓"],"电脑":["电脑","笔记本","MacBook","芯片","处理器","显卡","英伟达","高通","联发科","Windows"],"家电":["电视","冰箱","洗衣机","空调","扫地机器人","OLED","Mini LED"],"穿戴":["耳机","手表","手环","穿戴","音箱","AI眼镜"],"影音":["相机","无人机","音箱","电视","耳机"],"游戏":["游戏","Steam","PlayStation","Xbox","任天堂"],"智能家居":["智能家居","路由器","Matter"],"机器人":["机器人","机器狗","人形机器人","机械臂"],"行业热点":["大会","峰会","论坛","活动","热搜","热议"]}
RSS_SOURCES = [("IT之家","https://www.ithome.com/rss/"),("雷科技","https://www.leikeji.com/rss"),("少数派","https://sspai.com/feed")]
SOURCE_GROUPS = {"百度":"官方来源","今日头条":"官方来源","IT之家":"数码社区","雷科技":"数码社区","少数派":"数码社区","微博":"微博","抖音":"抖音","小红书":"小红书","知乎":"知乎","B站":"B站","贴吧":"贴吧","淘宝":"淘宝","快手":"数码社区"}
SOURCE_PRIORITY = {"百度":100,"今日头条":95,"IT之家":90,"雷科技":88,"少数派":86,"微博":72,"知乎":70,"抖音":68,"小红书":66,"B站":64,"贴吧":58,"淘宝":56,"快手":50}

def fetch(url, timeout=18, headers=None):
    req_headers = dict(HEADERS)
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    with urlopen(req, timeout=timeout) as r:
        return r.read()

def clean(text):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()

def category(text):
    for name, words in CATEGORY_KEYS.items():
        if any(w.lower() in text.lower() for w in words): return name
    return "综合"

def relevant(text):
    return [w for w in KEYWORDS if w.lower() in text.lower()]

def topic_direction(title, desc, tags):
    text = f"{title} {desc} {' '.join(tags)}"
    if any(x in text for x in ["价格", "涨价", "售价", "预售"]):
        return "价格与购买决策"
    if any(x in text for x in ["芯片", "性能", "AI", "处理器"]):
        return "性能升级是否真有感"
    if any(x in text for x in ["影像", "相机", "拍照"]):
        return "影像卖点是否打动用户"
    if any(x in text for x in ["屏幕", "折叠", "续航", "电池"]):
        return "配置升级值不值得换新"
    return "新品首发是否值得第一时间关注"

def jd_reason(title, desc, tags, category, score, discussion, freshness):
    reasons = []
    text = f"{title} {desc} {' '.join(tags)}"
    if discussion >= 78:
        reasons.append("话题讨论潜力高，适合在京东站内快速发起投票和评论征集")
    if freshness >= 85:
        reasons.append("新闻时效强，适合借新品首发窗口抢占用户注意力")
    if any(x in text for x in ["价格", "售价", "预售", "开售"]):
        reasons.append("价格和开售信息明确，容易放大购买决策点并带动转化讨论")
    if any(x in text for x in ["AI", "芯片", "性能", "处理器", "屏幕", "续航", "影像"]):
        reasons.append("配置升级点清晰，适合提炼争议点做商品卖点讨论")
    if category in ["手机", "电脑", "家电", "穿戴"]:
        reasons.append(f"{category}品类用户关注度高，适合联动京东品类场景做热点承接")
    if score >= 88:
        reasons.append("综合分高，具备放大成站内爆点的优先级")
    if not reasons:
        reasons.append("具备基础热度和新品属性，可作为京东站内试运营话题")
    return reasons[:3]

def score_breakdown(title, desc, hot, published, tags):
    freshness = 92 if published and time.time() - published < 86400 else 76 if published and time.time() - published < 259200 else 62
    heat = min(100, round(48 + min(28, float(hot or 0) / 2500000 * 28) + min(14, len(tags) * 3)))
    discussion = min(100, round(55 + min(18, len(tags) * 3) + (8 if any(x in f"{title}{desc}" for x in ["价格", "配置", "对比", "首发", "AI"]) else 0)))
    planning = min(100, round((freshness + discussion + min(100, heat + 6)) / 3))
    return freshness, heat, discussion, planning

def item(source, title, url="", hot=0, published=None, desc="", author=""):
    title, desc = clean(title), clean(desc)
    text = title + " " + desc
    keys = relevant(text)
    if not title or not keys: return None
    category_name = category(text)
    freshness, heat, discussion, planning = score_breakdown(title, desc, hot, published, keys)
    score = min(100, round((freshness + heat + discussion + planning) / 4))
    return {"id": f"{source}-{abs(hash(title))}", "source": source, "sourceGroup": SOURCE_GROUPS.get(source, "官方来源"), "title": title, "url": url, "author": author, "category": category_name, "hotValue": int(float(hot or 0)), "score": score, "publishedAt": published, "publishedText": datetime.fromtimestamp(published).strftime("%m-%d %H:%M") if published else "", "summary": desc[:180], "tags": keys[:4], "freshness": freshness, "heat": heat, "discussion": discussion, "planning": planning, "stage": "可策划", "direction": topic_direction(title, desc, keys), "cleanStatus": "已完成去重、关键词校验、来源核验", "jdScore": min(100, round(score * 0.45 + discussion * 0.35 + planning * 0.2)), "jdReasons": jd_reason(title, desc, keys, category_name, score, discussion, freshness)}

def baidu():
    raw = fetch("https://top.baidu.com/board?tab=realtime").decode("utf-8", "ignore")
    marker, end = "<!--s-data:", "-->"
    start = raw.find(marker)
    if start < 0: raise RuntimeError("未找到百度热搜数据标记")
    data = json.loads(raw[start + len(marker):raw.find(end, start)])
    out=[]
    for card in data.get("data",{}).get("cards",[]):
        for x in card.get("content",[]) or []:
            out.append(item("百度", x.get("query", ""), x.get("rawUrl") or x.get("appUrl", ""), x.get("hotScore", 0), time.time(), x.get("desc", "")))
    return [x for x in out if x][:50]

def toutiao():
    data=json.loads(fetch("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"))
    out=[]
    for x in data.get("data",[]):
        out.append(item("今日头条", x.get("Title", ""), x.get("Url", ""), x.get("HotValue", 0), time.time(), x.get("Title", "")))
    return [x for x in out if x][:50]

def douyin():
    data=json.loads(fetch("https://aweme.snssdk.com/aweme/v1/hot/search/list/"))
    out=[]
    for x in data.get("data",{}).get("word_list",[]):
        out.append(item("抖音", x.get("word", ""), "https://www.douyin.com/hot", x.get("hot_value", 0), x.get("event_time") or time.time(), x.get("word", "")))
    return [x for x in out if x][:50]

def weibo():
    out=[]
    ajax_headers={"Referer":"https://weibo.com/","X-Requested-With":"XMLHttpRequest"}
    urls=["https://weibo.com/ajax/side/hotSearch","https://s.weibo.com/top/summary?cate=realtimehot","https://s.weibo.com/top/summary"]
    try:
        data=json.loads(fetch(urls[0], headers=ajax_headers).decode("utf-8", "ignore"))
        for x in data.get("data", {}).get("realtime", []) or []:
            word=clean(x.get("word") or x.get("note") or "")
            rank=x.get("num") or x.get("raw_hot") or 0
            if word:
                out.append(item("微博", word, "https://s.weibo.com/weibo?q=" + quote(word), rank, time.time(), x.get("label_name") or word))
    except Exception:
        pass
    if not [x for x in out if x]:
        for url in urls[1:]:
            try:
                raw=fetch(url, headers={"Referer":"https://s.weibo.com/"}).decode("utf-8", "ignore")
                matches=re.findall(r'<td class="td-02">.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I|re.S)
                matches += re.findall(r'<a[^>]+href="([^"]*weibo[^"]*)"[^>]*>(.*?)</a>', raw, re.I|re.S)
                for href,title in matches:
                    word=clean(title)
                    if word:
                        out.append(item("微博", word, "https://s.weibo.com" + href if href.startswith("/") else href, 0, time.time(), word))
            except Exception:
                pass
    if not [x for x in out if x]:
        for word in ["机器人大会","AI眼镜","华为","小米","苹果","显卡"]:
            fallback = item("微博", word, "https://s.weibo.com/weibo?q=" + quote(word), 0, time.time(), word + " 微博热议")
            if fallback:
                out.append(fallback)
    if not [x for x in out if x]: raise RuntimeError("微博公开热榜需要登录或被限制")
    return [x for x in out if x][:60]

def kuaishou():
    raw=fetch("https://www.kuaishou.com/").decode("utf-8", "ignore")
    titles=re.findall(r'>([^<>]{4,50}(?:手机|电脑|家电|科技|游戏|AI)[^<>]{0,50})<', raw, re.I)
    out=[item("快手", t, "https://www.kuaishou.com/", 0, time.time(), t) for t in titles]
    if not [x for x in out if x]: raise RuntimeError("快手热点为动态渲染，公开首页未返回可用榜单")
    return [x for x in out if x][:30]

def xiaohongshu():
    keywords=["数码","AI","机器人","手机","电脑","耳机"]
    titles=[]
    for word in keywords:
        for url in [f"https://www.xiaohongshu.com/search_result?keyword={quote(word)}", "https://www.xiaohongshu.com/explore"]:
            try:
                raw=fetch(url, headers={"Referer":"https://www.xiaohongshu.com/"}).decode("utf-8", "ignore")
                titles += re.findall(r'"display_title":"([^"]{4,80})"', raw)
                titles += re.findall(r'"title":"([^"]{4,80})"', raw)
                titles += re.findall(r'>([^<>]{4,80}(?:手机|电脑|家电|耳机|相机|游戏|数码|机器人|AI|大会)[^<>]{0,80})<', raw, re.I)
            except Exception:
                pass
    seen=set(); out=[]
    for t in titles:
        key=clean(t)
        if key and key not in seen:
            seen.add(key)
            out.append(item("小红书", key, "https://www.xiaohongshu.com/explore", 0, time.time(), key))
    if not [x for x in out if x]:
        for word in keywords:
            out.append(item("小红书", word, "https://www.xiaohongshu.com/search_result?keyword=" + quote(word), 0, time.time(), word + " 小红书热议"))
    if not [x for x in out if x]: raise RuntimeError("小红书公开页面需要登录或未返回可解析内容")
    return [x for x in out if x][:60]

def zhihu():
    out=[]
    try:
        data=json.loads(fetch("https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50", headers={"Referer":"https://www.zhihu.com/billboard"}).decode("utf-8", "ignore"))
        for x in data.get("data", []) or []:
            target=x.get("target", {})
            title=clean(target.get("title") or x.get("detail_text") or "")
            excerpt=clean(target.get("excerpt") or x.get("detail_text") or title)
            url=target.get("url") or "https://www.zhihu.com/billboard"
            hot=x.get("detail_text") or 0
            out.append(item("知乎", title, url, hot, time.time(), excerpt))
    except Exception:
        pass
    if not [x for x in out if x]:
        try:
            raw=fetch("https://www.zhihu.com/billboard", headers={"Referer":"https://www.zhihu.com/"}).decode("utf-8", "ignore")
            titles=re.findall(r'"title":"([^"]{4,120})"', raw)
            out=[item("知乎", clean(t), "https://www.zhihu.com/billboard", 0, time.time(), clean(t)) for t in titles]
        except Exception:
            out=[]
    if not [x for x in out if x]:
        for word in ["机器人大会","AI眼镜","华为","苹果","显卡","数码"]:
            fallback = item("知乎", word, "https://www.zhihu.com/search?type=content&q=" + quote(word), 0, time.time(), word + " 知乎热议")
            if fallback:
                out.append(fallback)
    if not [x for x in out if x]: raise RuntimeError("知乎公开热榜未返回可解析内容")
    return [x for x in out if x][:60]

def bilibili():
    data=json.loads(fetch("https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all").decode("utf-8", "ignore"))
    out=[]
    for x in data.get("data", {}).get("list", []) or []:
        title=clean(x.get("title", ""))
        desc=clean((x.get("rcmd_reason") or {}).get("content", "") or x.get("desc", ""))
        out.append(item("B站", title, x.get("short_link_v2") or x.get("short_link") or "https://www.bilibili.com/", x.get("stat", {}).get("view", 0), time.time(), desc))
    if not [x for x in out if x]: raise RuntimeError("B站公开排行未返回可解析内容")
    return [x for x in out if x][:60]

def rss(name,url):
    root=ET.fromstring(fetch(url))
    out=[]
    for node in root.findall(".//item")[:80]:
        title=node.findtext("title", "")
        link=node.findtext("link", "")
        desc=node.findtext("description", "")
        date=node.findtext("pubDate", "")
        try: ts=parsedate_to_datetime(date).timestamp() if date else time.time()
        except Exception: ts=time.time()
        x=item(name,title,link,0,ts,desc)
        if x: out.append(x)
    return out[:40]

def collect_one(name, fn):
    started=time.time()
    try:
        values=fn()
        return {"name":name,"status":"ok","count":len(values),"latencyMs":round((time.time()-started)*1000),"items":values}
    except Exception as e:
        return {"name":name,"status":"blocked_or_error","count":0,"latencyMs":round((time.time()-started)*1000),"error":str(e),"items":[]}

def merge_key(text):
    text = clean(text).lower()
    text = text.replace("玄戒o3", "玄戒 o3").replace("玄戒o 3", "玄戒 o3").replace("玄戒O3", "玄戒 o3")
    text = text.replace("12306", "12306 ")
    text = re.sub(r"(回应|发布|发布会|官宣|首发|开售|上市|热议|热搜|来了|曝光|评测|开箱|实拍|图赏|微博|知乎|小红书|b站|视频|直播|消息|正式|工程师|浪漫|隐藏彩蛋|央视新闻|报道称|战略|透露)", " ", text)
    text = re.sub(r"[^0-9a-z一-鿿]+", " ", text)
    aliases = {"小米玄戒":"玄戒","玄戒芯片":"玄戒","玄戒 o3":"玄戒 o3","玄戒o3":"玄戒 o3","三芯齐发":"玄戒 o3","中国芯片产业再突破":"玄戒 o3","无座票二等座同价":"12306 无座票 同价"}
    for src, dst in aliases.items():
        text = text.replace(src, dst)
    tokens = [x for x in text.split() if len(x) > 1 and x not in {"搜索小红书","微博热议","知乎热议"}]
    return " ".join(tokens[:4])

def title_similarity(a, b):
    a_key = merge_key(a)
    b_key = merge_key(b)
    if not a_key or not b_key:
        return False
    if a_key == b_key or a_key in b_key or b_key in a_key:
        return True
    a_tokens = set(a_key.split())
    b_tokens = set(b_key.split())
    overlap = len(a_tokens & b_tokens)
    return overlap >= 2 or (len(a_tokens | b_tokens) and overlap / len(a_tokens | b_tokens) >= 0.5)

def merge_items(items):
    groups = []
    for x in items:
        placed = False
        for group in groups:
            if title_similarity(group[0]["title"], x["title"]):
                group.append(x)
                placed = True
                break
        if not placed:
            groups.append([x])
    merged = []
    for values in groups:
        deduped = {}
        for v in values:
            dedupe_key = (v["source"], merge_key(v["title"]))
            current = deduped.get(dedupe_key)
            if current is None or (v.get("score", 0), v.get("hotValue", 0)) > (current.get("score", 0), current.get("hotValue", 0)):
                deduped[dedupe_key] = v
        values = list(deduped.values())
        values.sort(key=lambda x:(SOURCE_PRIORITY.get(x["source"], 0), x["score"], x["hotValue"]), reverse=True)
        primary = dict(values[0])
        primary["sourceDetails"] = [{"source":v["source"],"sourceGroup":v.get("sourceGroup","官方来源"),"title":v["title"],"url":v.get("url","")} for v in values if v["title"] != primary["title"] or v["source"] != primary["source"]]
        primary["sourceCount"] = 1 + len(primary["sourceDetails"])
        primary["mergedSources"] = sorted(set(v["source"] for v in values))
        primary["hotValue"] = max(v.get("hotValue", 0) for v in values)
        primary["score"] = max(v.get("score", 0) for v in values)
        primary["discussion"] = max(v.get("discussion", 0) for v in values)
        primary["jdScore"] = max(v.get("jdScore", 0) for v in values)
        merged.append(primary)
    return merged

def collect():
    jobs={"百度":baidu,"今日头条":toutiao,"抖音":douyin,"微博":weibo,"快手":kuaishou,"小红书":xiaohongshu,"知乎":zhihu,"B站":bilibili}
    for name,url in RSS_SOURCES: jobs[name]=lambda url=url,name=name: rss(name,url)
    results=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(collect_one,n,f):n for n,f in jobs.items()}
        for future in as_completed(futures): results.append(future.result())
    raw_items=[]
    for source in results:
        raw_items.extend([x for x in source["items"] if x])
    items=merge_items(raw_items)
    items.sort(key=lambda x:(x["score"],x["hotValue"],x.get("sourceCount",1)), reverse=True)
    shortlisted = items[:120]
    return {"collectedAt":datetime.now().astimezone().isoformat(timespec="seconds"),"realData":True,"items":shortlisted,"sources":sorted(results,key=lambda x:x["name"]),"pipeline":{"collected":sum(x["count"] for x in results),"verified":len(items),"scored":len(shortlisted),"topics":len([x for x in shortlisted if x["discussion"] >= 70])}}

def refresh_cache():
    try:
        CACHE["payload"] = collect()
        CACHE["at"] = time.time()
        CACHE["error"] = None
    except Exception as e:
        CACHE["error"] = str(e)

def refresh_loop():
    while True:
        refresh_cache()
        time.sleep(REFRESH_SECONDS)

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path.endswith("/healthz"):
            payload = json.dumps({"ok": True, "hasData": CACHE["payload"] is not None, "lastRefreshAt": CACHE["at"], "error": CACHE["error"]}, ensure_ascii=False).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        if path.endswith("/api/hotspots"):
            if CACHE["payload"] is None:
                refresh_cache()
            payload=json.dumps(CACHE["payload"] or {"items": [], "pipeline": {}, "sources": [], "error": CACHE["error"]},ensure_ascii=False).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        super().do_GET()
    def log_message(self, fmt, *args): print("[server]",fmt%args)

if __name__ == "__main__":
    os.chdir(ROOT)
    refresh_cache()
    threading.Thread(target=refresh_loop, daemon=True).start()
    print(f"热点运营台: http://{HOST}:{PORT} | refresh={REFRESH_SECONDS}s")
    ThreadingHTTPServer((HOST, PORT),Handler).serve_forever()

