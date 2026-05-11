#!/usr/bin/env python3
"""
Empower Mindfulness - Meta Ads Action Script
手動執行，所有操作都需要確認才會送出

功能：
  1. 暫停頻率超標廣告（從 pending_pause.json 讀取，需確認）
  2. 複製最佳廣告設定 + 讓你選新貼文 → 建立新廣告
  3. 用受眾範本快速建立 AB test Ad Set（Spirit / Family 兩組）

執行方式：
  python3 action.py
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import os
import sys
from datetime import datetime

BASE_DIR     = os.path.dirname(__file__)
CONFIG_PATH  = os.path.join(BASE_DIR, "config.json")
PENDING_PATH = os.path.join(BASE_DIR, "pending_pause.json")
REPORTS_DIR  = os.path.join(BASE_DIR, "reports")
AUDIENCES_PATH = os.path.join(BASE_DIR, "audiences.json")

PAGE_ID = "114153688290088"   # Aling.Tuner 粉絲專頁 ID（如有變更請更新）

# ── 預設受眾範本 ─────────────────────────────────────────────────────────────
# 興趣 ID 需要先跑 setup_interests() 來填入；地點 key 已預設主要城市
DEFAULT_AUDIENCES = {
    "spirit": {
        "name": "Spirit受眾（靈性自我成長）",
        "age_min": 35,
        "age_max": 55,
        "genders": [],        # [] = 全部
        "geo_locations": {
            "cities": [
                {"key": "2306179"},                                        # 台北市
                {"key": "226984"},                                         # 新北市
                {"key": "2306182"},                                        # 台中市
                {"key": "2306183"},                                        # 台南市
                {"key": "2306185"},                                        # 高雄市
                {"key": "2306188", "radius": 25, "distance_unit": "mile"} # 新竹
            ],
            "countries": ["HK"],
            "regions": [{"key": "3847"}]   # 美國加州
        },
        # flexible_spec: 第一層 OR，第二層 AND（與第一層交集）
        "flexible_spec": [
            {
                "interests": [
                    # 填入 ID 後格式：{"id": "123", "name": "Spirituality"}
                    # 先用 setup_interests() 取得 ID
                    {"name": "Spirituality"},
                    {"name": "Personal development"},
                    {"name": "Self-awareness"},
                    {"name": "Psychology"}
                ]
            },
            {
                "interests": [
                    {"name": "Astrology"},
                    {"name": "Buddhism"},
                    {"name": "Mindfulness"},
                    {"name": "Life coaching"}
                ]
            }
        ],
        "daily_budget": 15000   # NT$150/日（Meta API 單位：分，15000 = NT$150）
    },
    "family": {
        "name": "Family受眾（家庭職場壓力）",
        "age_min": 35,
        "age_max": 55,
        "genders": [],
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
            {
                "interests": [
                    {"name": "Family"},
                    {"name": "Work–life balance"},
                    {"name": "Stress management"}
                ]
            },
            {
                "interests": [
                    {"name": "Mindfulness"},
                    {"name": "Personal development"},
                    {"name": "Psychology"}
                ]
            }
        ],
        "daily_budget": 15000
    }
}
# ─────────────────────────────────────────────────────────────────────────────


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print("❌ 找不到 config.json，請先執行 get_long_token.py")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_audiences():
    if os.path.exists(AUDIENCES_PATH):
        with open(AUDIENCES_PATH) as f:
            return json.load(f)
    return DEFAULT_AUDIENCES


def save_audiences(audiences):
    with open(AUDIENCES_PATH, "w", encoding="utf-8") as f:
        json.dump(audiences, f, indent=2, ensure_ascii=False)


def api_get(endpoint, params, token):
    params["access_token"] = token
    url = f"https://graph.facebook.com/v19.0/{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.urlopen(url, timeout=20)
        return json.loads(req.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f"❌ GET Error: {err.get('error', {}).get('message', '')}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def api_post(endpoint, data, token):
    """POST 或 PATCH 請求"""
    data["access_token"] = token
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    url = f"https://graph.facebook.com/v19.0/{endpoint}"
    try:
        req = urllib.request.Request(url, data=encoded, method="POST")
        res = urllib.request.urlopen(req, timeout=20)
        return json.loads(res.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f"❌ POST Error: {err.get('error', {}).get('message', '')}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def api_patch(ad_id, data, token):
    """PATCH 請求（更新廣告狀態）"""
    data["access_token"] = token
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    url = f"https://graph.facebook.com/v19.0/{ad_id}"
    try:
        req = urllib.request.Request(url, data=encoded, method="POST")
        req.add_header("X-HTTP-Method-Override", "PATCH")
        res = urllib.request.urlopen(req, timeout=20)
        return json.loads(res.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f"❌ PATCH Error: {err.get('error', {}).get('message', '')}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def get_latest_report():
    """讀取最新 JSON 報告"""
    if not os.path.exists(REPORTS_DIR):
        return None
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.endswith(".json")],
        reverse=True
    )
    if not files:
        return None
    with open(os.path.join(REPORTS_DIR, files[0]), encoding="utf-8") as f:
        return json.load(f)


def confirm(msg):
    """詢問使用者確認，回傳 True/False"""
    ans = input(f"\n{msg} [y/N] ").strip().lower()
    return ans in ("y", "yes")


# ══════════════════════════════════════════════════════════════════════════════
# 功能一：暫停頻率超標廣告
# ══════════════════════════════════════════════════════════════════════════════

def show_pending_pauses():
    """顯示 pending_pause.json 中等待暫停的廣告"""
    if not os.path.exists(PENDING_PATH):
        # 從最新報告讀取
        report = get_latest_report()
        if not report or not report.get("frequency_stops"):
            print("✅ 目前沒有頻率超標的廣告需要暫停")
            return []
        return report["frequency_stops"]

    with open(PENDING_PATH) as f:
        pending = json.load(f)
    return pending.get("ads_to_pause", [])


def pause_flagged_ads():
    print("\n" + "="*60)
    print("⛔ 功能一：暫停頻率超標廣告")
    print("="*60)

    config = load_config()
    token = config["access_token"]
    account_id = config["ad_account_id"]
    freq_stop = config.get("frequency_stop", 2.0)

    # 從最新報告找超標廣告
    report = get_latest_report()
    if not report:
        print("❌ 找不到報告，請先執行 monitor.py")
        return

    stops = report.get("frequency_stops", [])
    if not stops:
        print("✅ 目前沒有廣告頻率 ≥ {freq_stop}x，無需暫停")
        return

    print(f"\n以下廣告頻率 ≥ {freq_stop}x，建議立即暫停：\n")
    for i, ad in enumerate(stops, 1):
        print(f"  [{i}] {ad.get('name', '未知')}  —  頻率 {ad.get('freq', 0):.2f}x  —  {ad.get('campaign', '')}")

    if not confirm("確認要暫停以上所有廣告嗎？"):
        print("取消操作。")
        return

    # 從 API 找這些廣告的 ID
    print("\n🔍 正在查詢廣告 ID...")
    ads_result = api_get(f"{account_id}/ads", {
        "fields": "id,name,status",
        "effective_status": '["ACTIVE"]',
        "limit": 200
    }, token)

    if not ads_result or "data" not in ads_result:
        print("❌ 無法取得廣告清單")
        return

    stop_names = {ad["name"] for ad in stops}
    ads_to_pause = [a for a in ads_result["data"] if a["name"] in stop_names]

    if not ads_to_pause:
        print("⚠️  在 ACTIVE 廣告中找不到對應的廣告（可能已暫停）")
        return

    print(f"\n準備暫停 {len(ads_to_pause)} 則廣告...\n")
    for ad in ads_to_pause:
        result = api_patch(ad["id"], {"status": "PAUSED"}, token)
        if result and result.get("success"):
            print(f"  ✅ 已暫停：{ad['name']}")
        else:
            print(f"  ❌ 暫停失敗：{ad['name']}")


# ══════════════════════════════════════════════════════════════════════════════
# 功能二：複製最佳廣告設定 + 選新貼文
# ══════════════════════════════════════════════════════════════════════════════

def extract_post_id_from_url(url):
    """從 FB 貼文 URL 提取 post ID"""
    # 格式 1: https://www.facebook.com/aling.tuner/posts/123456789
    # 格式 2: https://www.facebook.com/permalink.php?story_fbid=123&id=456
    import re
    m = re.search(r'/posts/(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'story_fbid=(\d+)', url)
    if m:
        return m.group(1)
    # 如果只輸入數字，直接用
    if url.strip().isdigit():
        return url.strip()
    return None


def create_ad_from_best():
    print("\n" + "="*60)
    print("⭐ 功能二：複製最佳廣告設定，選新貼文建廣告")
    print("="*60)

    config = load_config()
    token = config["access_token"]
    account_id = config["ad_account_id"]

    # 從報告找最佳廣告
    report = get_latest_report()
    if not report:
        print("❌ 找不到報告，請先執行 monitor.py")
        return

    active_ads = report.get("active_ads", [])
    valid_ads = [a for a in active_ads if a.get("cpr") and a.get("results", 0) >= 5]
    if not valid_ads:
        print("❌ 沒有足夠數據的 ACTIVE 廣告")
        return

    best = min(valid_ads, key=lambda x: x["cpr"])
    print(f"\n目前最佳廣告：")
    print(f"  名稱：{best['ad_name']}")
    print(f"  Campaign：{best['campaign']}")
    print(f"  CPR：NT${best['cpr']:.2f}  |  花費：NT${best['spend']:.0f}  |  頻率：{best['frequency']:.2f}x")

    if not confirm("要以這則廣告的設定為基礎，建立新廣告嗎？"):
        print("取消操作。")
        return

    # 從 API 取得這則廣告的完整設定
    print("\n🔍 正在讀取廣告設定...")
    ads_result = api_get(f"{account_id}/ads", {
        "fields": "id,name,adset_id",
        "limit": 200
    }, token)

    if not ads_result or "data" not in ads_result:
        print("❌ 無法取得廣告清單")
        return

    best_ad = next((a for a in ads_result["data"] if a["name"] == best["ad_name"]), None)
    if not best_ad:
        print(f"❌ 找不到廣告：{best['ad_name']}")
        return

    adset_id = best_ad["adset_id"]
    adset_info = api_get(adset_id, {
        "fields": "name,targeting,daily_budget,bid_amount,billing_event,optimization_goal,campaign_id,status"
    }, token)

    if not adset_info:
        print("❌ 無法取得 Ad Set 設定")
        return

    campaign_id = adset_info.get("campaign_id")
    print(f"\n✅ 已讀取設定：")
    print(f"  Ad Set：{adset_info.get('name')}")
    print(f"  日預算：NT${int(adset_info.get('daily_budget', 0)) // 100}")
    print(f"  優化目標：{adset_info.get('optimization_goal')}")

    # 讓使用者輸入新貼文
    print("\n請貼上要投放的新 FB 貼文網址（或直接輸入貼文 ID）：")
    post_url = input("貼文網址：").strip()
    post_id = extract_post_id_from_url(post_url)

    if not post_id:
        print("❌ 無法解析貼文 ID，請確認網址格式")
        return

    story_id = f"{PAGE_ID}_{post_id}"
    print(f"\n  貼文 ID：{story_id}")

    # 設定新廣告名稱
    today = datetime.now().strftime("%m%d")
    default_name = f"{best['ad_name'].split('-')[0]}-新素材-{today}"
    print(f"\n新廣告名稱（直接按 Enter 使用預設：{default_name}）：")
    ad_name = input("廣告名稱：").strip() or default_name

    print(f"\n準備建立：")
    print(f"  廣告名稱：{ad_name}")
    print(f"  使用貼文：{story_id}")
    print(f"  沿用 Campaign：{campaign_id}")
    print(f"  複製 Ad Set 設定：{adset_info.get('name')}")

    if not confirm("確認建立廣告嗎？"):
        print("取消操作。")
        return

    # 建立新 Ad Set（複製設定）
    print("\n⏳ 建立 Ad Set...")
    new_adset_name = f"{adset_info.get('name', 'AdSet')}-{today}"
    adset_data = {
        "name": new_adset_name,
        "campaign_id": campaign_id,
        "daily_budget": adset_info.get("daily_budget", "15000"),
        "billing_event": adset_info.get("billing_event", "IMPRESSIONS"),
        "optimization_goal": adset_info.get("optimization_goal", "PAGE_LIKES"),
        "targeting": json.dumps(adset_info.get("targeting", {})),
        "status": "PAUSED"   # 先暫停，確認後再手動開啟
    }

    new_adset = api_post(f"{account_id}/adsets", adset_data, token)
    if not new_adset or "id" not in new_adset:
        print("❌ Ad Set 建立失敗")
        return

    new_adset_id = new_adset["id"]
    print(f"  ✅ Ad Set 建立成功：{new_adset_id}")

    # 建立 Creative
    print("⏳ 建立廣告素材...")
    creative_data = {
        "name": f"Creative-{ad_name}",
        "object_story_id": story_id
    }
    creative = api_post(f"{account_id}/adcreatives", creative_data, token)
    if not creative or "id" not in creative:
        print("❌ 廣告素材建立失敗")
        return

    creative_id = creative["id"]
    print(f"  ✅ 素材建立成功：{creative_id}")

    # 建立 Ad
    print("⏳ 建立廣告...")
    ad_data = {
        "name": ad_name,
        "adset_id": new_adset_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": "PAUSED"
    }
    new_ad = api_post(f"{account_id}/ads", ad_data, token)
    if not new_ad or "id" not in new_ad:
        print("❌ 廣告建立失敗")
        return

    print(f"\n🎉 廣告建立完成！")
    print(f"  廣告 ID：{new_ad['id']}")
    print(f"  狀態：PAUSED（請到 Ads Manager 確認後手動開啟）")
    print(f"\n⚠️  記得到 Ads Manager 確認受眾、粉絲排除設定正確後再開啟。")


# ══════════════════════════════════════════════════════════════════════════════
# 功能三：用受眾範本快速建立 AB test Ad Set
# ══════════════════════════════════════════════════════════════════════════════

def search_interest_raw(query, token, limit=15):
    """搜尋 FB 興趣資料庫，回傳原始候選清單（含 audience_size / path）"""
    result = api_get("search", {
        "type": "adinterest",
        "q": query,
        "fields": "id,name,audience_size,path,topic,disambiguation_category",
        "limit": limit
    }, token)
    if result and "data" in result:
        return result["data"]
    return []


def browse_interests(token):
    """自由搜尋 FB 興趣資料庫——讓你看候選清單，方便挑選正確標籤"""
    print("\n" + "="*60)
    print("🔍 FB 興趣資料庫搜尋")
    print("="*60)
    print("輸入關鍵字搜尋（例如：meditation、psychology、astrology）")
    print("輸入 q 離開")

    while True:
        print()
        query = input("搜尋關鍵字：").strip()
        if query.lower() in ("q", "quit", "exit", ""):
            break

        candidates = search_interest_raw(query, token)
        if not candidates:
            print(f"  ❌ 找不到「{query}」相關的興趣標籤")
            continue

        print(f"\n  找到 {len(candidates)} 個結果：")
        print(f"  {'#':>2}  {'名稱':<35} {'受眾規模':>12}  {'分類路徑'}")
        print(f"  {'-'*80}")
        for idx, c in enumerate(candidates):
            name    = c.get("name", "")[:34]
            size    = c.get("audience_size", 0)
            path    = " > ".join(c.get("path", [])) if c.get("path") else c.get("topic", "")
            size_str = f"{size:,}" if size else "—"
            print(f"  {idx+1:>2}. {name:<35} {size_str:>12}  {path}")


def setup_interests(token):
    """互動式設定受眾興趣標籤 ID——每個標籤都讓你看候選後選擇"""
    print("\n" + "="*60)
    print("⚙️  受眾興趣標籤設定（互動式）")
    print("="*60)
    print("每個關鍵字會顯示 FB 上所有候選，由你選正確的那一個")
    print("輸入編號選取 / s 跳過 / r 換關鍵字重搜")
    print()

    audiences = load_audiences()

    # 收集所有需要設定的 (aud_key, layer_idx, interest_idx, interest_name)
    tasks = []
    for aud_key, aud in audiences.items():
        for li, layer in enumerate(aud.get("flexible_spec", [])):
            for ii, interest in enumerate(layer.get("interests", [])):
                tasks.append({
                    "aud_key": aud_key,
                    "aud_name": aud.get("name", aud_key),   # 相容舊格式
                    "layer": li + 1,
                    "idx": ii,
                    "current": interest
                })

    for task in tasks:
        aud = audiences[task["aud_key"]]
        layer = aud["flexible_spec"][task["layer"] - 1]
        interest = layer["interests"][task["idx"]]

        # 已有 ID 的跳過
        if "id" in interest:
            print(f"  ✅ 已設定：{interest['name']} (ID: {interest['id']})")
            continue

        original_name = interest["name"]
        query = original_name

        while True:
            print(f"\n▶  [{task['aud_name']}] 第{task['layer']}層 — 搜尋：{query}")
            candidates = search_interest_raw(query, token)

            if not candidates:
                print(f"  ❌ 找不到「{query}」相關標籤")
                action = input("  輸入 r 換關鍵字 / s 跳過：").strip().lower()
                if action == "r":
                    query = input("  新關鍵字：").strip()
                    continue
                else:
                    print(f"  ⏭  跳過「{original_name}」（保留名稱，之後可再設定）")
                    break

            print(f"  {'#':>2}  {'名稱':<38} {'受眾規模':>12}  {'分類路徑'}")
            print(f"  {'-'*80}")
            for i, c in enumerate(candidates):
                name    = c.get("name", "")[:37]
                size    = c.get("audience_size", 0)
                path    = " > ".join(c.get("path", [])) if c.get("path") else c.get("topic", "")
                size_str = f"{size:,}" if size else "—"
                print(f"  {i+1:>2}. {name:<38} {size_str:>12}  {path}")

            action = input("\n  輸入編號選取 / r 換關鍵字 / s 跳過：").strip().lower()

            if action == "s":
                print(f"  ⏭  跳過「{original_name}」")
                break
            elif action == "r":
                query = input("  新關鍵字：").strip()
                continue
            elif action.isdigit() and 1 <= int(action) <= len(candidates):
                chosen = candidates[int(action) - 1]
                layer["interests"][task["idx"]] = {
                    "id": chosen["id"],
                    "name": chosen["name"]
                }
                print(f"  ✅ 選定：{chosen['name']} (ID: {chosen['id']}, 受眾: {chosen.get('audience_size', 0):,})")
                break
            else:
                print("  ⚠️  請輸入正確的編號、r 或 s")

    save_audiences(audiences)
    print("\n✅ 設定完成，已儲存到 audiences.json")
    print("   下次建立廣告時會自動使用這組受眾。")
    return audiences


def get_page_fan_audience_id(account_id, token):
    """取得粉絲專頁的自訂受眾 ID（用於排除現有粉絲）"""
    result = api_get(f"{account_id}/customaudiences", {
        "fields": "id,name,subtype",
        "limit": 100
    }, token)
    if not result or "data" not in result:
        return None
    for aud in result["data"]:
        if aud.get("subtype") == "ENGAGEMENT" and "Aling" in aud.get("name", ""):
            return aud["id"]
    # 如果找不到特定的，回傳第一個 ENGAGEMENT 類型
    for aud in result["data"]:
        if aud.get("subtype") in ("ENGAGEMENT", "PAGE"):
            return aud["id"]
    return None


def create_ab_test_adsets():
    print("\n" + "="*60)
    print("🧪 功能三：快速建立 AB Test Ad Set（Spirit / Family）")
    print("="*60)

    config = load_config()
    token = config["access_token"]
    account_id = config["ad_account_id"]

    # 確保有興趣 ID
    audiences = load_audiences()
    spirit = audiences.get("spirit", DEFAULT_AUDIENCES["spirit"])
    family = audiences.get("family", DEFAULT_AUDIENCES["family"])

    # 選擇受眾
    print("\n要建立哪個受眾的 Ad Set？")
    print("  [1] Spirit 受眾（靈性自我成長）")
    print("  [2] Family 受眾（家庭職場壓力）")
    print("  [3] 兩個都建（完整 AB test）")
    choice = input("\n請選擇 [1/2/3]：").strip()

    if choice == "1":
        selected = [("spirit", spirit)]
    elif choice == "2":
        selected = [("family", family)]
    elif choice == "3":
        selected = [("spirit", spirit), ("family", family)]
    else:
        print("取消操作。")
        return

    # 選擇 Campaign
    print("\n請輸入要使用的 Campaign ID（在 Ads Manager 的 Campaign 層級可以找到）：")
    print("（也可以直接按 Enter，我會從最新報告找現有 Campaign）")
    campaign_id = input("Campaign ID：").strip()

    if not campaign_id:
        report = get_latest_report()
        if report and report.get("active_ads"):
            # 用第一個 active ad 的 campaign
            first = report["active_ads"][0]
            print(f"⚠️  將使用報告中的 Campaign：{first.get('campaign')}")
            # 需要從 API 找 campaign ID
            ads_result = api_get(f"{account_id}/ads", {
                "fields": "id,name,campaign_id",
                "limit": 50
            }, token)
            if ads_result and "data" in ads_result:
                # 找第一個 active ad 的 campaign_id
                first_ad = next((a for a in ads_result["data"] if a.get("name")), None)
                if first_ad:
                    campaign_id = first_ad.get("campaign_id", "")
        if not campaign_id:
            print("❌ 找不到 Campaign ID，請手動輸入")
            return

    # 輸入貼文
    print("\n請貼上要投放的 FB 貼文網址：")
    post_url = input("貼文網址：").strip()
    post_id = extract_post_id_from_url(post_url)
    if not post_id:
        print("❌ 無法解析貼文 ID")
        return

    story_id = f"{PAGE_ID}_{post_id}"

    # 取得粉絲受眾 ID（用於排除）
    print("\n🔍 正在查詢粉絲排除受眾...")
    fan_audience_id = get_page_fan_audience_id(account_id, token)
    if fan_audience_id:
        print(f"  ✅ 找到粉絲受眾 ID：{fan_audience_id}")
    else:
        print("  ⚠️  找不到粉絲排除受眾，建立後請在 Ads Manager 手動設定排除")

    today = datetime.now().strftime("%m%d")

    print(f"\n準備建立 {len(selected)} 個 Ad Set：")
    for key, aud in selected:
        print(f"  • {aud['name']}  |  日預算 NT${aud['daily_budget']//100}")

    if not confirm("確認建立嗎？"):
        print("取消操作。")
        return

    for key, aud in selected:
        print(f"\n⏳ 建立 Ad Set：{aud['name']}...")

        # 加入粉絲排除
        targeting = dict(aud.get("flexible_spec", {}))
        targeting_full = {
            "age_min": aud["age_min"],
            "age_max": aud["age_max"],
            "flexible_spec": aud["flexible_spec"],
            "geo_locations": aud["geo_locations"]
        }
        if fan_audience_id:
            targeting_full["excluded_custom_audiences"] = [{"id": fan_audience_id}]

        adset_name = f"AB-{key.upper()}-{today}"
        adset_data = {
            "name": adset_name,
            "campaign_id": campaign_id,
            "daily_budget": str(aud["daily_budget"]),
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "PAGE_LIKES",
            "targeting": json.dumps(targeting_full),
            "status": "PAUSED"
        }

        new_adset = api_post(f"{account_id}/adsets", adset_data, token)
        if not new_adset or "id" not in new_adset:
            print(f"  ❌ Ad Set 建立失敗（{aud['name']}）")
            continue

        new_adset_id = new_adset["id"]
        print(f"  ✅ Ad Set 建立成功：{adset_name}（ID: {new_adset_id}）")

        # 建立 Creative + Ad
        creative_data = {
            "name": f"Creative-{key}-{today}",
            "object_story_id": story_id
        }
        creative = api_post(f"{account_id}/adcreatives", creative_data, token)
        if not creative or "id" not in creative:
            print(f"  ❌ 素材建立失敗（{key}）")
            continue

        ad_data = {
            "name": f"AD-{key.upper()}-{today}",
            "adset_id": new_adset_id,
            "creative": json.dumps({"creative_id": creative["id"]}),
            "status": "PAUSED"
        }
        new_ad = api_post(f"{account_id}/ads", ad_data, token)
        if new_ad and "id" in new_ad:
            print(f"  ✅ 廣告建立成功（ID: {new_ad['id']}）")
        else:
            print(f"  ❌ 廣告建立失敗（{key}）")

    print(f"\n🎉 完成！請到 Ads Manager 確認設定後再開啟廣告。")
    print("⚠️  注意：Advantage+ 設定需要在 Ads Manager 手動開啟。")


# ══════════════════════════════════════════════════════════════════════════════
# 主選單
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Empower Mindfulness — 廣告操作工具")
    print("  所有操作都需要你確認才會執行")
    print("=" * 60)

    config = load_config()
    token = config["access_token"]

    print("\n請選擇功能：")
    print("  [1] ⛔ 暫停頻率超標廣告")
    print("  [2] ⭐ 複製最佳廣告設定 + 選新貼文建廣告")
    print("  [3] 🧪 快速建立 AB Test Ad Set（Spirit / Family）")
    print("  [4] 🔍 更新受眾興趣標籤 ID（首次使用請先執行）")
    print("  [0] 離開")

    choice = input("\n請輸入數字：").strip()

    if choice == "1":
        pause_flagged_ads()
    elif choice == "2":
        create_ad_from_best()
    elif choice == "3":
        create_ab_test_adsets()
    elif choice == "4":
        setup_interests(token)
    elif choice == "0":
        print("掰掰！")
    else:
        print("❌ 無效選項")


if __name__ == "__main__":
    main()
