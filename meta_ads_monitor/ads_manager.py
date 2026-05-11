#!/usr/bin/env python3
"""
Empower Mindfulness - 廣告助理（聰明版）
直接執行：python3 ads_manager.py
不需要記任何指令，它會自動告訴你現在該做什麼。
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import os
import sys
import re
from datetime import datetime

BASE_DIR       = os.path.dirname(__file__)
CONFIG_PATH    = os.path.join(BASE_DIR, "config.json")
AUDIENCES_PATH = os.path.join(BASE_DIR, "audiences.json")
REPORTS_DIR    = os.path.join(BASE_DIR, "reports")
PAGE_ID        = "114153688290088"

SPIRIT_AUDIENCE = {
    "age_min": 35,
    "age_max": 55,
    "geo_locations": {
        "cities": [
            {"key": "2306179"},
            {"key": "226984"},
            {"key": "2306182"},
            {"key": "2306183"},
            {"key": "2306185"},
            {"key": "2306188", "radius": 25, "distance_unit": "mile"}
        ],
        "countries": ["HK"],
        "regions": [{"key": "3847"}]
    },
    "flexible_spec": [
        {"interests": [
            {"name": "Spirituality"},
            {"name": "Personal development"},
            {"name": "Self-awareness"},
            {"name": "Psychology"}
        ]},
        {"interests": [
            {"name": "Astrology"},
            {"name": "Buddhism"},
            {"name": "Mindfulness"},
            {"name": "Life coaching"}
        ]}
    ]
}

# ── API helpers ───────────────────────────────────────────────────────────────

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print("❌ 找不到 config.json，請先執行 get_long_token.py")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)

def load_audience():
    if os.path.exists(AUDIENCES_PATH):
        with open(AUDIENCES_PATH) as f:
            return json.load(f).get("spirit", SPIRIT_AUDIENCE)
    return SPIRIT_AUDIENCE

def save_audience(audience):
    data = {}
    if os.path.exists(AUDIENCES_PATH):
        with open(AUDIENCES_PATH) as f:
            data = json.load(f)
    data["spirit"] = audience
    with open(AUDIENCES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def api_get(endpoint, params, token):
    params["access_token"] = token
    url = f"https://graph.facebook.com/v19.0/{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        res = urllib.request.urlopen(url, timeout=20)
        return json.loads(res.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f"❌ {err.get('error', {}).get('message', '未知錯誤')}")
        return None
    except Exception as e:
        print(f"❌ {e}")
        return None

def api_post(endpoint, data, token):
    data["access_token"] = token
    url = f"https://graph.facebook.com/v19.0/{endpoint}"
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=encoded, method="POST")
        res = urllib.request.urlopen(req, timeout=20)
        return json.loads(res.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f"❌ {err.get('error', {}).get('message', '未知錯誤')}")
        return None
    except Exception as e:
        print(f"❌ {e}")
        return None

def api_patch(obj_id, data, token):
    data["access_token"] = token
    url = f"https://graph.facebook.com/v19.0/{obj_id}"
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=encoded, method="POST")
        req.add_header("X-HTTP-Method-Override", "PATCH")
        res = urllib.request.urlopen(req, timeout=20)
        return json.loads(res.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f"❌ {err.get('error', {}).get('message', '未知錯誤')}")
        return None
    except Exception as e:
        print(f"❌ {e}")
        return None

def get_latest_report():
    if not os.path.exists(REPORTS_DIR):
        return None
    files = sorted([f for f in os.listdir(REPORTS_DIR) if f.endswith(".json")], reverse=True)
    if not files:
        return None
    with open(os.path.join(REPORTS_DIR, files[0]), encoding="utf-8") as f:
        return json.load(f)

def confirm(msg):
    return input(f"\n{msg} [y/N] ").strip().lower() in ("y", "yes")

def extract_post_id(raw):
    raw = raw.strip()
    if raw.isdigit():
        return raw
    for pattern in [r'/posts/(\d+)', r'story_fbid=(\d+)', r'/(\d{10,})']:
        m = re.search(pattern, raw)
        if m:
            return m.group(1)
    return None

def get_fan_exclusion_id(account_id, token):
    result = api_get(f"{account_id}/customaudiences", {
        "fields": "id,name,subtype", "limit": 100
    }, token)
    if not result:
        return None
    for a in result.get("data", []):
        if a.get("subtype") in ("PAGE", "ENGAGEMENT"):
            return a["id"]
    return None

# ── 分析現況 ──────────────────────────────────────────────────────────────────

def analyze_situation(report):
    """
    讀取最新報告，回傳：
    - urgent_actions: 緊急要做的事 (list of dict)
    - suggestions: 一般建議 (list of dict)
    - active_ads: ACTIVE 廣告清單
    - summary: 一行摘要
    """
    if not report:
        return [], [], [], "找不到報告，請先執行 monitor.py"

    active      = report.get("active_ads", [])
    freq_stops  = report.get("frequency_stops", [])
    freq_warns  = report.get("frequency_warnings", [])
    slowdowns   = report.get("slowdown_alerts", [])

    urgent    = []
    suggested = []

    # 緊急：頻率超標
    for ad in freq_stops:
        urgent.append({
            "icon": "🚨",
            "title": f"立即暫停「{ad['name']}」",
            "detail": f"頻率 {ad['freq']:.2f}x，已超標，受眾看太多次了",
            "action": "pause",
            "ad_name": ad["name"]
        })

    # 警告：頻率接近上限
    for ad in freq_warns:
        urgent.append({
            "icon": "⚠️ ",
            "title": f"「{ad['name']}」頻率接近上限（{ad['freq']:.2f}x）→ 暫停",
            "detail": "頻率快到上限，選此直接暫停廣告",
            "action": "pause",
            "ad_name": ad["name"]
        })

    # 建議：粉絲增速放緩
    for ad in slowdowns:
        suggested.append({
            "icon": "📉",
            "title": f"「{ad['name']}」粉絲增速放緩",
            "detail": "最近幾天新粉絲明顯減少，可以考慮換文章",
            "action": "prepare_next",
            "ad_name": ad["name"]
        })

    # 一般建議：廣告太多、預算分散
    if len(active) > 2:
        suggested.append({
            "icon": "💡",
            "title": f"目前有 {len(active)} 則廣告同時跑",
            "detail": "預算比較分散，建議暫停表現差的，集中在好的",
            "action": "review_budget",
            "ad_name": None
        })

    # 摘要
    total_spend = sum(a.get("spend", 0) for a in active)
    best = min(active, key=lambda x: x.get("cpr") or 999) if active else None
    if best and best.get("cpr"):
        summary = (f"{len(active)} 則廣告 ACTIVE｜"
                   f"最佳：{best['ad_name']}（CPR NT${best['cpr']:.2f}）")
    elif active:
        summary = f"{len(active)} 則廣告 ACTIVE"
    else:
        summary = "目前沒有 ACTIVE 廣告"

    return urgent, suggested, active, summary


# ── 主選單 ────────────────────────────────────────────────────────────────────

def show_main_menu(report, config):
    urgent, suggested, active, summary = analyze_situation(report)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_time = report.get("generated_at", "未知") if report else "—"

    # 報告是否超過 3 小時（提醒更新）
    stale_warning = ""
    if report and report_time != "未知":
        try:
            rt = datetime.strptime(report_time, "%Y-%m-%d %H:%M")
            hours_old = (datetime.now() - rt).total_seconds() / 3600
            if hours_old > 3:
                stale_warning = f"  ⚠️  報告已 {hours_old:.0f} 小時未更新，建議先選「更新廣告數據」\n"
        except Exception:
            pass

    print("\n" + "═"*58)
    print("  📊 Empower Mindfulness · 廣告助理")
    print(f"  {now}   （報告：{report_time}）")
    print("═"*58)
    if stale_warning:
        print(stale_warning)
    print(f"\n  目前狀況：{summary}\n")

    # 顯示廣告清單
    if active:
        # 依昨日+粉絲降序（最有力的廣告在上方）
        sorted_active = sorted(active, key=lambda x: x.get("follows_delta_today") or 0, reverse=True)
        print(f"  {'廣告名稱':<22} {'頻率':>6} {'累積粉絲':>8} {'昨日+粉':>7} {'CPR':>8} {'CPC':>8}")
        print(f"  {'─'*66}")
        for ad in sorted_active:
            freq   = ad.get("frequency", 0)
            cpr    = ad.get("cpr")
            cpc    = ad.get("cpc")
            delta  = ad.get("follows_delta_today")
            total  = ad.get("follows_30d", 0) or 0
            icon   = "🚨" if freq >= 2.0 else "⚠️" if freq >= 1.8 else "🟢"
            cpr_s  = f"NT${cpr:.2f}" if cpr else "     -"
            cpc_s  = f"NT${cpc:.2f}" if cpc else "     -"
            d_s    = f"+{delta}" if delta is not None else "  -"
            name   = ad.get("ad_name", "未知")[:20]
            if ad.get("no_data"):
                print(f"  {icon} {name:<20} （剛開啟，尚無數據）")
            else:
                print(f"  {icon} {name:<20} {freq:>5.2f}x {total:>8} {d_s:>7} {cpr_s:>8} {cpc_s:>8}")
        print()

    # 建立選單選項
    options = []

    # 緊急項目優先
    for item in urgent:
        options.append(item)

    # 一般建議
    for item in suggested:
        options.append(item)

    # 固定選項
    options.append({
        "icon": "🔄",
        "title": "更新廣告數據（重新拉取 API）",
        "detail": "馬上執行 monitor.py，取得最新成效",
        "action": "refresh"
    })
    options.append({
        "icon": "🚪",
        "title": "離開",
        "detail": "",
        "action": "exit"
    })

    # 顯示選單
    if urgent:
        print(f"  ⚡ 現在需要處理：")
        for i, opt in enumerate(options):
            if opt in urgent:
                print(f"  [{i+1}] {opt['icon']} {opt['title']}")
                if opt.get("detail"):
                    print(f"       {opt['detail']}")
        print()

    remaining = [o for o in options if o not in urgent]
    print(f"  其他操作：")
    for opt in remaining:
        idx = options.index(opt) + 1
        print(f"  [{idx}] {opt['icon']} {opt['title']}")
        if opt.get("detail"):
            print(f"       {opt['detail']}")

    print()
    choice = input("  請選擇 → ").strip()

    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(options):
        print("  ❌ 無效選項")
        return True

    selected = options[int(choice) - 1]
    action   = selected["action"]

    if action == "exit":
        return False
    elif action == "pause":
        do_pause(selected.get("ad_name"), config)
    elif action == "refresh":
        do_refresh()
    elif action == "prepare_next":
        print(f"\n  💡 建議：先看最近發的文章，哪一篇有比較好的自然互動？")
        print(f"     有了候選文章後，選「建立新廣告」把它跑起來。")
        print(f"     新廣告跑起來後，再回來暫停「{selected.get('ad_name', '')}」。")
        input("\n  按 Enter 繼續...")
    elif action == "review_budget":
        do_review_budget(active, config)

    return True


# ── 執行動作 ──────────────────────────────────────────────────────────────────

def do_pause(ad_name, config):
    print(f"\n  ⛔ 暫停廣告：{ad_name}")
    token      = config["access_token"]
    account_id = config["ad_account_id"]

    if not confirm(f"  確認要暫停「{ad_name}」嗎？"):
        return

    result = api_get(f"{account_id}/ads", {
        "fields": "id,name,status",
        "effective_status": '["ACTIVE"]',
        "limit": 200
    }, token)

    if not result:
        return

    target = next((a for a in result.get("data", []) if a["name"] == ad_name), None)
    if not target:
        print(f"  ⚠️  找不到 ACTIVE 中的「{ad_name}」（可能已暫停）")
        return

    res = api_patch(target["id"], {"status": "PAUSED"}, token)
    if res and res.get("success"):
        print(f"  ✅ 已暫停：{ad_name}")
    else:
        print(f"  ❌ 暫停失敗，請到 Ads Manager 手動操作")


def pick_adset_targeting(account_id, token):
    """列出現有 Ad Set，讓使用者選一個來複製受眾設定"""
    print("\n  📋 讀取現有 Ad Set（複製受眾用）...")
    result = api_get(f"{account_id}/adsets", {
        "fields": "id,name,targeting,campaign_id,status",
        "effective_status": '["ACTIVE","PAUSED"]',
        "limit": 20
    }, token)
    adsets = result.get("data", []) if result else []

    if not adsets:
        print("  ⚠️  找不到任何 Ad Set，請先在 Ads Manager 建立一組受眾")
        return None, None

    print()
    for i, a in enumerate(adsets, 1):
        icon = "🟢" if a.get("status") == "ACTIVE" else "⏸️"
        print(f"  [{i}] {icon} {a['name']}")

    while True:
        ch = input("\n  選哪個 Ad Set 的受眾？→ ").strip()
        if ch.isdigit() and 1 <= int(ch) <= len(adsets):
            chosen = adsets[int(ch) - 1]
            return chosen["targeting"], chosen["campaign_id"]
        print("  ❌ 請輸入有效編號")


def do_create(config):
    print("\n" + "─"*58)
    print("  ✍️  建立新廣告")
    print("─"*58)
    print("  提醒：選有自然互動的文章，效果比較好。\n")

    token      = config["access_token"]
    account_id = config["ad_account_id"]

    # 貼文
    print("  請貼上 FB 貼文網址（或直接輸入貼文數字 ID）：")
    raw     = input("  → ").strip()
    post_id = extract_post_id(raw)

    if not post_id:
        print("\n  ⚠️  無法自動解析，請直接輸入貼文數字 ID：")
        print("  （到貼文右上角「⋯」→「複製連結」，網址裡的長數字就是 ID）")
        post_id = input("  → ").strip()
        if not post_id.isdigit():
            print("  ❌ 無效 ID，取消")
            return

    story_id = f"{PAGE_ID}_{post_id}"

    # 選受眾（從現有 Ad Set 複製）
    targeting, campaign_id = pick_adset_targeting(account_id, token)
    if not targeting:
        input("\n  按 Enter 繼續...")
        return

    # 預算
    print(f"\n  每日預算（直接按 Enter = NT$300）：NT$")
    budget_input = input("  → ").strip()
    budget_ntd   = int(budget_input) if budget_input.isdigit() else 300
    daily_budget = budget_ntd * 100

    # 廣告名稱
    today        = datetime.now().strftime("%m%d")
    default_name = f"Post-{today}"
    print(f"\n  廣告名稱（按 Enter = 「{default_name}」）：")
    ad_name = input("  → ").strip() or default_name

    # 確認
    age_min = targeting.get("age_min", "?")
    age_max = targeting.get("age_max", "?")
    print(f"\n  {'─'*48}")
    print(f"  廣告名稱：{ad_name}")
    print(f"  貼文 ID ：{story_id}")
    print(f"  受眾年齡：{age_min}–{age_max} 歲（複製自選定 Ad Set）")
    print(f"  每日預算：NT${budget_ntd}")
    print(f"  狀態：PAUSED（建好後到 Ads Manager 開啟）")
    print(f"  {'─'*48}")

    if not confirm("  確認建立？"):
        return

    # 建立 Ad Set
    print("\n  ⏳ 建立中...")
    adset = api_post(f"{account_id}/adsets", {
        "name": f"AdSet-{ad_name}",
        "campaign_id": campaign_id,
        "daily_budget": str(daily_budget),
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "PAGE_LIKES",
        "targeting": json.dumps(targeting),
        "status": "PAUSED"
    }, token)
    if not adset or "id" not in adset:
        print("  ❌ Ad Set 建立失敗")
        return

    creative = api_post(f"{account_id}/adcreatives", {
        "name": f"Creative-{ad_name}",
        "object_story_id": story_id
    }, token)
    if not creative or "id" not in creative:
        print("  ❌ 素材建立失敗")
        return

    ad = api_post(f"{account_id}/ads", {
        "name": ad_name,
        "adset_id": adset["id"],
        "creative": json.dumps({"creative_id": creative["id"]}),
        "status": "PAUSED"
    }, token)

    if ad and "id" in ad:
        print(f"\n  🎉 廣告建好了！")
        print(f"  → 到 Ads Manager 搜尋「{ad_name}」，確認後開啟它")
        print(f"  → 記得確認 Advantage+ 是開啟的")
    else:
        print("  ❌ 廣告建立失敗")


def do_refresh():
    print("\n  🔄 正在更新數據，請稍候...")
    script = None
    import subprocess
    for root, dirs, files in os.walk("/sessions"):
        for f in files:
            if f == "monitor.py" and "meta_ads_monitor" in root:
                script = os.path.join(root, f)
                break
    if not script:
        # 用已知路徑
        script = os.path.join(BASE_DIR, "monitor.py")

    try:
        result = subprocess.run(["python3", script], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("  ✅ 數據已更新！重新啟動助理來看最新狀況。")
        else:
            print(f"  ❌ 更新失敗：{result.stderr[:200]}")
    except Exception as e:
        print(f"  ❌ 無法執行：{e}")

    input("\n  按 Enter 繼續...")


def do_setup(config):
    """呼叫 action.py 的互動式受眾設定"""
    import sys
    action_path = os.path.join(BASE_DIR, "action.py")
    if not os.path.exists(action_path):
        print("  ❌ 找不到 action.py")
        input("\n  按 Enter 繼續...")
        return

    # 動態載入 action.py
    import importlib.util
    spec = importlib.util.spec_from_file_location("action", action_path)
    action = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(action)

    token = config["access_token"]
    action.setup_interests(token)
    input("\n  按 Enter 繼續...")


def do_browse_interests(config):
    """呼叫 action.py 的自由搜尋 FB 興趣資料庫"""
    action_path = os.path.join(BASE_DIR, "action.py")
    if not os.path.exists(action_path):
        print("  ❌ 找不到 action.py")
        input("\n  按 Enter 繼續...")
        return

    import importlib.util
    spec = importlib.util.spec_from_file_location("action", action_path)
    action = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(action)

    token = config["access_token"]
    action.browse_interests(token)


def do_review_budget(active, config):
    print("\n  💡 各廣告花費分析：\n")
    total = sum(a.get("spend", 0) for a in active)
    for ad in sorted(active, key=lambda x: x.get("spend", 0), reverse=True):
        pct  = (ad["spend"] / total * 100) if total > 0 else 0
        bar  = "█" * int(pct / 5)
        name = ad.get("ad_name", "未知")[:22]
        print(f"  {name:<22} NT${ad['spend']:>6.0f}  {bar} {pct:.0f}%")

    print(f"\n  總花費（30日）：NT${total:.0f}")
    print(f"\n  建議：暫停花費高但 CPR 也高的廣告，把預算集中給 CPR 最低的。")

    if confirm("  要暫停表現最差的廣告嗎？"):
        worst = max(active, key=lambda x: x.get("cpr") or 0)
        do_pause(worst.get("ad_name"), config)


# ── 主程式 ────────────────────────────────────────────────────────────────────

def main():
    config = load_config()
    report = get_latest_report()

    running = True
    while running:
        try:
            running = show_main_menu(report, config)
            # 每次操作後重新載入報告（可能已更新）
            report = get_latest_report()
        except KeyboardInterrupt:
            print("\n\n  掰掰！")
            break


if __name__ == "__main__":
    main()
