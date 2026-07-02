#!/usr/bin/env python3
"""
晋江文学城 耽美 VIP 金榜 監測腳本
每天由 GitHub Actions 執行，比對狀態變化，更新 notifications.json
"""
import json, re, os
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from html.parser import HTMLParser

URL = "https://www.jjwxc.net/topten.php?orderstr=5&t=0&fw=3&xx=2&isvip=1"
TOP_N = 20
PREV_FILE = "prev_state.json"
NOTIF_FILE = "notifications.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Referer": "https://www.jjwxc.net/",
}

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.cur_row, self.cur_cell = [], [], ""
        self.in_td = False
        self.cur_href = ""

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cur_row = []
        elif tag == "td":
            self.in_td = True
            self.cur_cell = ""
            self.cur_href = ""
        elif tag == "a" and self.in_td:
            d = dict(attrs)
            self.cur_href = d.get("href", "")

    def handle_endtag(self, tag):
        if tag == "td":
            self.in_td = False
            self.cur_row.append((self.cur_cell.strip(), self.cur_href))
        elif tag == "tr" and self.cur_row:
            self.rows.append(self.cur_row)

    def handle_data(self, data):
        if self.in_td:
            self.cur_cell += data

def fetch_novels():
    req = Request(URL, headers=HEADERS)
    with urlopen(req, timeout=20) as r:
        raw = r.read()
    # 晉江用 GBK
    try:
        html = raw.decode("gbk")
    except:
        html = raw.decode("utf-8", errors="replace")

    p = TableParser()
    p.feed(html)

    novels = []
    for row in p.rows:
        if not row: continue
        rank_text = row[0][0].strip()
        if not re.match(r"^\d+$", rank_text): continue
        rank = int(rank_text)
        if rank > TOP_N: break
        if len(row) < 5: continue
        author = row[1][0]
        title = row[2][0]
        href = row[2][1] or ""
        if href and not href.startswith("http"):
            href = "https://www.jjwxc.net/" + href.lstrip("/")
        status = row[4][0] if len(row) > 4 else ""
        word_count = row[5][0] if len(row) > 5 else ""
        novels.append({
            "rank": rank,
            "author": author,
            "title": title,
            "status": status,
            "wordCount": word_count,
            "url": href,
        })
    return novels

def load_json(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    print("抓取晉江耽美 VIP 金榜...")
    novels = fetch_novels()
    print(f"取得 {len(novels)} 筆資料")

    # 現在狀態：{title: {status, author, url, rank}}
    current = {n["title"]: n for n in novels}

    # 讀取上次狀態
    prev = load_json(PREV_FILE)

    # 讀取既有通知
    notif_data = load_json(NOTIF_FILE)
    notifications = notif_data.get("notifications", [])

    # 台北時間
    tz_taipei = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_taipei).strftime("%Y-%m-%d %H:%M")

    new_count = 0
    for title, info in current.items():
        prev_info = prev.get(title)
        if prev_info:
            # 曾在榜單上，檢查狀態變化
            if prev_info.get("status") != "完结" and info["status"] == "完结":
                notifications.insert(0, {
                    "id": f"{title}_{now_str}",
                    "type": "completed",
                    "title": title,
                    "author": info["author"],
                    "rank": info["rank"],
                    "url": info["url"],
                    "detectedAt": now_str,
                    "read": False,
                })
                print(f"🎉 新完結：{title}（作者：{info['author']}，排名：{info['rank']}）")
                new_count += 1
        else:
            # 新上榜的書，如果一上榜就是完結也通知
            if info["status"] == "完结":
                notifications.insert(0, {
                    "id": f"{title}_{now_str}",
                    "type": "completed",
                    "title": title,
                    "author": info["author"],
                    "rank": info["rank"],
                    "url": info["url"],
                    "detectedAt": now_str,
                    "read": False,
                })
                new_count += 1

    # 保留最多 100 則通知
    notifications = notifications[:100]

    # 儲存當前榜單狀態（只存 title/status/author/url/rank）
    save_json(PREV_FILE, {
        t: {"status": v["status"], "author": v["author"], "url": v["url"], "rank": v["rank"]}
        for t, v in current.items()
    })

    # 更新通知 JSON
    save_json(NOTIF_FILE, {
        "lastUpdated": now_str,
        "totalUnread": sum(1 for n in notifications if not n.get("read")),
        "notifications": notifications,
        "currentChart": novels,  # 也存一份現在榜單，供 App 顯示
    })

    print(f"完成！新通知：{new_count} 則，總通知：{len(notifications)} 則")

if __name__ == "__main__":
    main()
