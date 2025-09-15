#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    # Python 3
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
except ImportError:  # pragma: no cover
    # Python 2 fallback (unlikely, but keeps imports tidy)
    from urllib2 import Request, urlopen, URLError, HTTPError  # type: ignore

import xml.etree.ElementTree as ET
import ssl


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
)

# Create SSL context that bypasses certificate verification
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


def http_get(url: str, timeout: int = 15) -> Tuple[int, bytes]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
            return resp.getcode(), resp.read()
    except HTTPError as e:
        return e.code, e.read() if hasattr(e, "read") else b""
    except URLError:
        return 0, b""


def http_post_json(url: str, payload: Dict, timeout: int = 15) -> Tuple[int, bytes]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json; charset=utf-8",
    })
    try:
        with urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
            return resp.getcode(), resp.read()
    except HTTPError as e:
        return e.code, e.read() if hasattr(e, "read") else b""
    except URLError:
        return 0, b""


def http_post_form(url: str, form: Dict[str, str], timeout: int = 15) -> Tuple[int, bytes]:
    encoded = "&".join(
        f"{k}={quote_plus(v)}" for k, v in form.items()
    ).encode("utf-8")
    req = Request(url, data=encoded, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    })
    try:
        with urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
            return resp.getcode(), resp.read()
    except HTTPError as e:
        return e.code, e.read() if hasattr(e, "read") else b""
    except URLError:
        return 0, b""


def quote_plus(s: str) -> str:
    # Minimal encoder to avoid importing urllib.parse for Python 3/2 juggling
    try:
        from urllib.parse import quote_plus as qp  # type: ignore
        return qp(s)
    except Exception:
        # Super minimal fallback
        return s.replace(" ", "+")


def parse_rss_items(xml_bytes: bytes) -> List[Dict]:
    items: List[Dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items

    # RSS feeds typically: rss > channel > item
    channel = root.find("channel")
    if channel is None:
        # Sometimes namespaced
        for child in root:
            if child.tag.endswith("channel"):
                channel = child
                break
    if channel is None:
        return items

    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        items.append({
            "title": title,
            "link": link,
            "pubDate": pub_date,
            "description": description,
        })
    return items


TWEET_ID_RE = re.compile(r"/status/(\d+)\b")


def extract_tweet_id(link: str) -> Optional[str]:
    m = TWEET_ID_RE.search(link)
    return m.group(1) if m else None


def best_nitter_url(instances: List[str], username: str) -> Optional[str]:
    for base in instances:
        base = base.rstrip("/")
        url = f"{base}/{username}/rss"
        code, body = http_get(url)
        if code == 200 and body:
            return url
    return None


def fetch_latest_from_nitter(instances: List[str], username: str) -> List[Dict]:
    # Try each instance until success, return items
    for base in instances:
        base = base.rstrip("/")
        url = f"{base}/{username}/rss"
        code, body = http_get(url)
        if code == 200 and body:
            items = parse_rss_items(body)
            # Items are usually newest first; standardize sort oldest->newest
            items.sort(key=lambda x: x.get("pubDate", ""))
            return items
    return []


def load_json(path: str, default):
    if not path:
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def save_json_atomic(path: str, data) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def build_x_link(username: str, tweet_id: str) -> str:
    return f"https://x.com/{username}/status/{tweet_id}"


def push_wecom(webhook: str, text: str) -> bool:
    payload = {
        "msgtype": "text",
        "text": {"content": text[:4096]},  # basic guard
    }
    code, body = http_post_json(webhook, payload)
    if code != 200:
        return False
    try:
        resp = json.loads(body.decode("utf-8"))
        return resp.get("errcode", -1) == 0
    except Exception:
        return False


def push_serverchan(sendkey: str, title: str, desp: str) -> bool:
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    code, body = http_post_form(url, {"title": title, "desp": desp})
    if code != 200:
        return False
    try:
        resp = json.loads(body.decode("utf-8"))
        return resp.get("code") == 0
    except Exception:
        return False


def simple_translate(text: str) -> str:
    """简单但实用的英文到中文翻译"""
    import re

    # 短语和词组翻译（优先级高）
    phrases = {
        # 完整短语
        "going up": "上涨", "going down": "下跌", "right now": "现在", "just now": "刚刚",
        "breaking news": "突发新闻", "coming soon": "即将到来", "new update": "新更新",
        "stock price": "股价", "market cap": "市值", "AI technology": "AI技术",
        "new product": "新产品", "big news": "重大新闻", "just launched": "刚推出",

        # 时间表达
        "2 hours ago": "2小时前", "1 hour ago": "1小时前", "3 hours ago": "3小时前",
        "1 day ago": "1天前", "2 days ago": "2天前", "1 week ago": "1周前",
    }

    # 单词翻译
    words = {
        # 高频词汇
        "and": "和", "or": "或", "but": "但是", "so": "所以", "because": "因为",
        "will": "将", "would": "会", "can": "可以", "should": "应该", "must": "必须",
        "is": "是", "are": "是", "was": "是", "were": "是", "have": "有", "has": "有",
        "do": "做", "does": "做", "did": "做了", "get": "获得", "got": "获得了",

        # 商业/科技
        "company": "公司", "business": "商业", "market": "市场", "stock": "股票",
        "price": "价格", "investment": "投资", "technology": "技术", "AI": "AI",
        "product": "产品", "service": "服务", "user": "用户", "customer": "客户",
        "update": "更新", "launch": "推出", "release": "发布", "announce": "宣布",

        # 动词
        "said": "说", "says": "说", "think": "认为", "believe": "相信",
        "launched": "推出了", "released": "发布了", "announced": "宣布了",
        "shared": "分享了", "posted": "发布了", "tweeted": "发推说",

        # 时间
        "today": "今天", "yesterday": "昨天", "tomorrow": "明天", "now": "现在",
        "hour": "小时", "hours": "小时", "day": "天", "days": "天", "week": "周",
        "month": "月", "year": "年", "ago": "前", "later": "后",

        # 常用形容词
        "new": "新", "big": "大", "small": "小", "good": "好", "great": "很棒",
        "bad": "坏", "better": "更好", "best": "最好", "important": "重要",
    }

    result = text

    # 首先处理短语
    for phrase, translation in phrases.items():
        result = re.sub(r'\b' + re.escape(phrase) + r'\b', translation, result, flags=re.IGNORECASE)

    # 然后处理单词
    for word, translation in words.items():
        result = re.sub(r'\b' + re.escape(word) + r'\b', translation, result, flags=re.IGNORECASE)

    # 移除多余的冠词和介词
    result = re.sub(r'\bthe\b', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\ba\b', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\ban\b', '', result, flags=re.IGNORECASE)

    # 清理多余空格
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def format_message(username: str, item: Dict) -> Tuple[str, str]:
    link = item.get("link") or ""
    tid = extract_tweet_id(link) or ""
    x_link = build_x_link(username, tid) if tid else link
    title = item.get("title") or ""
    # Clean basic HTML entities often present in RSS titles
    title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

    # 翻译推文内容
    translated_title = simple_translate(title)

    # 如果翻译后内容不同，显示中英对照
    if translated_title != title and translated_title.strip():
        text = f"@{username}:\n{translated_title}\n\n原文: {title}\n{x_link}"
    else:
        text = f"@{username}: {title}\n{x_link}"

    return text, x_link


def run_once(config: Dict, state: Dict) -> Dict:
    users: List[str] = config.get("users", [])
    instances: List[str] = config.get("nitter_instances", [
        "https://nitter.net",
        "https://nitter.poast.org",
        "https://nitter.privacydev.net",
        "https://n.ramle.be",
    ])

    push_cfg: Dict = config.get("push", {})
    method: str = push_cfg.get("method", "wecom")
    wecom_webhook: Optional[str] = push_cfg.get("wecom_webhook") or os.environ.get("WECOM_WEBHOOK")
    serverchan_key: Optional[str] = push_cfg.get("serverchan_sendkey") or os.environ.get("SERVERCHAN_SENDKEY")

    if method == "wecom" and not wecom_webhook:
        print("[warn] WeCom webhook not configured; skipping push.")
    if method == "serverchan" and not serverchan_key:
        print("[warn] Server酱 sendkey not configured; skipping push.")

    state.setdefault("users", {})
    users_state: Dict = state["users"]

    for username in users:
        items = fetch_latest_from_nitter(instances, username)
        if not items:
            print(f"[info] No items fetched for @{username}")
            continue

        last_id = str(users_state.get(username, {}).get("last_id")) if users_state.get(username) else None

        new_items: List[Dict] = []
        for it in items:
            tid = extract_tweet_id(it.get("link") or "")
            if not tid:
                continue
            if last_id is None or int(tid) > int(last_id):
                new_items.append(it)

        if not new_items:
            print(f"[info] No new tweets for @{username}")
            continue

        # push oldest first
        new_items.sort(key=lambda x: x.get("pubDate", ""))
        latest_seen_id = last_id
        for it in new_items:
            msg, x_link = format_message(username, it)
            ok = False
            if method == "wecom" and wecom_webhook:
                ok = push_wecom(wecom_webhook, msg)
            elif method == "serverchan" and serverchan_key:
                ok = push_serverchan(serverchan_key, f"@{username} 最新推文", msg + "\n\n" + x_link)
            else:
                print("[warn] No push method configured.")
                ok = False

            tid = extract_tweet_id(it.get("link") or "")
            if ok and tid:
                latest_seen_id = tid
                print(f"[sent] @{username} {tid}")
            else:
                print(f"[fail] push @{username} -> {tid or 'unknown'}")

        if latest_seen_id:
            users_state[username] = {"last_id": latest_seen_id}

    state["users"] = users_state
    state["updated_at"] = datetime.utcnow().isoformat() + "Z"
    return state


def main():
    parser = argparse.ArgumentParser(description="Fetch X tweets via Nitter and push to WeChat")
    parser.add_argument("--config", default="config.json", help="Path to config JSON file")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--daemon", action="store_true", help="Run forever with interval from config")
    args = parser.parse_args()

    # GitHub Actions环境检测
    if os.environ.get("GITHUB_ACTIONS"):
        # 在GitHub Actions中，优先使用GitHub专用配置
        if os.path.exists("config_github.json"):
            args.config = "config_github.json"

        # 如果配置中的sendkey是FROM_ENV，从环境变量读取
        cfg = load_json(args.config, {})
        if cfg.get("push", {}).get("serverchan_sendkey") == "FROM_ENV":
            sendkey = os.environ.get("SERVERCHAN_SENDKEY")
            if sendkey:
                cfg["push"]["serverchan_sendkey"] = sendkey
            else:
                print("ERROR: SERVERCHAN_SENDKEY environment variable not set")
                sys.exit(1)
    else:
        cfg = load_json(args.config, {})

    if not cfg:
        print("Config not found or invalid. Create config.json or pass --config.")
        sys.exit(1)

    state_path = cfg.get("state_file", "state.json")
    state = load_json(state_path, {})

    interval = int(cfg.get("interval_seconds", 600))

    if args.once and args.daemon:
        print("Use either --once or --daemon, not both.")
        sys.exit(2)

    if args.once or not args.daemon:
        new_state = run_once(cfg, state)
        save_json_atomic(state_path, new_state)
        return

    try:
        while True:
            new_state = run_once(cfg, state)
            save_json_atomic(state_path, new_state)
            state = new_state
            time.sleep(max(60, interval))
    except KeyboardInterrupt:
        print("Exiting.")


if __name__ == "__main__":
    main()

