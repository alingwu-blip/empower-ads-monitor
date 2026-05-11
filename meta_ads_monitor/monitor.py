#!/usr/bin/env python3
"""
Empower Mindfulness - Meta Ads Monitor
每日廣告監控：只顯示 ACTIVE 廣告 + 每日粉絲增量追蹤 + 增速警報
"""

import urllib.request
import urllib.parse
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "follows_snapshot.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print("❌ 找不到 config.json，請先執行 get_long_token.py")
        exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)

def api_call(endpoint, params, token):
    params["access_token"] = token
    url = f"https://graph.facebook.com/v19.0/{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.urlopen(url, timeout=20)
        return json.loads(req.read())
    except urllib.error.HTTPError as e:
        error_body = json.loads(e.read())
        print(f"❌ API Error: {error_body.get('error', {}).get('message', '')}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def extract_cpr(insight):
    """從 insight 資料提取每次結果成本（依序嘗試多種 action type）"""
    cost_data = insight.get("cost_per_action_type", [])
    priority = [
        "page_engagement", "post_engagement", "like",
        "onsite_conversion.post_save", "comment", "link_click"
    ]
    for action_type in priority:
        for item in cost_data:
            if item.get("action_type") == action_type:
                val = float(item.get("value", 0))
                if val > 0:
                    return val
    values = [float(i["value"]) for i in cost_data if float(i.get("value", 0)) > 0]
    return min(values) if values else None

def extract_results(insight):
    """取得結果數（page_engagement = 頁面互動，含按讚、留言、分享、點擊）"""
    actions = insight.get("actions", [])
    priority = ["page_engagement", "post_engagement", "like", "comment", "link_click"]
    for action_type in priority:
        for item in actions:
            if item.get("action_type") == action_type:
                return int(item.get("value", 0))
    return 0

def extract_follows(insight):
    """取得追蹤者/粉絲增加數（累計，30天）"""
    actions = insight.get("actions", [])
    total = 0
    for item in actions:
        if item.get("action_type") in ["like", "follow"]:
            total += int(item.get("value", 0))
    return total if total > 0 else None

def get_all_ad_insights(config):
    """
    拉取廣告數據：
    1. insights API（過去30天有花費的廣告）
    2. 另外補抓目前 effective_status=ACTIVE 的廣告
       → 避免剛上線/剛開啟尚無花費的廣告被漏掉
    """
    token      = config["access_token"]
    account_id = config["ad_account_id"]

    # ── 1. 拉 insights（有花費數據的廣告）───────────────────────────────────
    result = api_call(f"{account_id}/insights", {
        "level": "ad",
        "fields": "ad_id,ad_name,campaign_id,campaign_name,adset_id,adset_name,"
                  "impressions,reach,frequency,spend,actions,cost_per_action_type,ctr,cpc",
        "date_preset": "last_30d",
        "limit": 500
    }, token)

    ad_insights = result["data"] if result and "data" in result else []

    while result and "paging" in result and result["paging"].get("cursors", {}).get("after"):
        after = result["paging"]["cursors"]["after"]
        result = api_call(f"{account_id}/insights", {
            "level": "ad",
            "fields": "ad_id,ad_name,campaign_id,campaign_name,adset_id,adset_name,"
                      "impressions,reach,frequency,spend,actions,cost_per_action_type,ctr,cpc",
            "date_preset": "last_30d",
            "limit": 500,
            "after": after
        }, token)
        if result and "data" in result:
            ad_insights.extend(result["data"])
        else:
            break

    # ── 2. 拉目前 ACTIVE 的廣告（補漏）──────────────────────────────────────
    active_result = api_call(f"{account_id}/ads", {
        "fields": "id,name,effective_status,campaign_id,campaign_name,adset_id,adset_name",
        "effective_status": '["ACTIVE"]',
        "limit": 500
    }, token)

    active_now = {}   # ad_id → ad dict
    if active_result and "data" in active_result:
        for a in active_result["data"]:
            active_now[a["id"]] = a

    # ── 3. 合併：用 effective_status 標記狀態，補上沒有 insights 的 ACTIVE 廣告 ──
    seen_ids = set()
    for ad in ad_insights:
        ad_id = ad.get("ad_id", "")
        seen_ids.add(ad_id)
        if ad_id in active_now:
            ad["ad_status"] = "ACTIVE"
        else:
            # 有 insights 但目前不在 ACTIVE 清單 → 補查
            pass   # 留空，後面用 status_map 補

    # 補查 insights 裡非 ACTIVE 的廣告的實際狀態
    non_active_ids = [ad.get("ad_id","") for ad in ad_insights if ad.get("ad_id") not in active_now]
    if non_active_ids:
        other_result = api_call(f"{account_id}/ads", {
            "fields": "id,effective_status",
            "ids": ",".join(non_active_ids[:50]),   # 最多一次查50個
        }, token)
        other_map = {}
        if other_result:
            # ids 查詢回傳的是 dict，key 是 id
            if isinstance(other_result, dict) and "data" not in other_result:
                other_map = {k: v.get("effective_status","") for k, v in other_result.items() if isinstance(v, dict)}
            elif "data" in other_result:
                other_map = {a["id"]: a.get("effective_status","") for a in other_result["data"]}
        for ad in ad_insights:
            if ad.get("ad_id") not in active_now:
                ad["ad_status"] = other_map.get(ad.get("ad_id",""), "PAUSED")

    # 補加：有 ACTIVE 但完全沒有 insights 數據的廣告（剛開啟）
    for ad_id, a in active_now.items():
        if ad_id not in seen_ids:
            ad_insights.append({
                "ad_id":        ad_id,
                "ad_name":      a.get("name", "未知"),
                "campaign_id":  a.get("campaign_id", ""),
                "campaign_name": a.get("campaign_name", ""),
                "adset_id":     a.get("adset_id", ""),
                "adset_name":   a.get("adset_name", ""),
                "impressions":  "0",
                "reach":        "0",
                "frequency":    "0",
                "spend":        "0",
                "ad_status":    "ACTIVE",
                "_no_data":     True   # 標記為尚無花費數據
            })

    camp_map = {a.get("campaign_id"): a.get("campaign_name") for a in ad_insights}
    return ad_insights, camp_map

# ─── 每日粉絲快照：追蹤 delta ───────────────────────────────────────────────

def load_snapshot():
    """讀取昨日快照 {ad_id: {date: "YYYY-MM-DD", follows: N, history: [...]}}"""
    if not os.path.exists(SNAPSHOT_PATH):
        return {}
    with open(SNAPSHOT_PATH) as f:
        return json.load(f)

def save_snapshot(snapshot):
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

def compute_follow_delta(ad_id, ad_name, follows_today, snapshot):
    """
    回傳 (delta_today, slowdown_warning)
    delta_today: 今日新增粉絲（與昨日相比）
    slowdown_warning: True 如果近3日增速下滑 > 30%
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    entry = snapshot.get(ad_id, {})
    history = entry.get("history", [])  # list of {"date": ..., "follows": ...}

    # 更新快照：如果今天已有紀錄就更新，否則新增
    if history and history[-1]["date"] == today_str:
        history[-1]["follows"] = follows_today
    else:
        history.append({"date": today_str, "follows": follows_today})

    # 只保留最近 7 天
    history = history[-7:]
    snapshot[ad_id] = {"ad_name": ad_name, "history": history}

    # 計算今日 delta（今日 - 昨日）
    delta_today = None
    if len(history) >= 2:
        delta_today = history[-1]["follows"] - history[-2]["follows"]
        if delta_today < 0:
            delta_today = 0  # 不應該為負，保護性處理

    # 增速放緩偵測：比較近3天平均 vs 前3天平均
    slowdown_warning = False
    if len(history) >= 4:
        # 計算每日 delta 序列
        deltas = [history[i]["follows"] - history[i-1]["follows"] for i in range(1, len(history))]
        deltas = [max(0, d) for d in deltas]
        if len(deltas) >= 3:
            recent_avg = sum(deltas[-2:]) / 2  # 最近2天平均
            earlier_avg = sum(deltas[:-2]) / max(len(deltas) - 2, 1)  # 之前平均
            if earlier_avg > 0 and recent_avg < earlier_avg * 0.7:
                slowdown_warning = True

    return delta_today, slowdown_warning, snapshot

# ────────────────────────────────────────────────────────────────────────────

def run_monitor():
    config = load_config()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    freq_warn = config.get("frequency_warning", 1.8)
    freq_stop = config.get("frequency_stop", 2.0)
    today_str = datetime.now().strftime("%Y-%m-%d")

    print("=" * 72)
    print(f"  Empower Mindfulness 廣告監控報告（每日，廣告層級）")
    print(f"  {now}")
    print("=" * 72)

    print("\n⏳ 正在拉取廣告數據...")
    ad_insights, camp_map = get_all_ad_insights(config)

    if not ad_insights:
        print("❌ 無法取得廣告數據，請確認 Token 和帳號 ID")
        return

    # 讀取快照
    snapshot = load_snapshot()

    # 整理數據
    for ad in ad_insights:
        ad["_freq"] = float(ad.get("frequency", 0))
        ad["_spend"] = float(ad.get("spend", 0))
        ad["_cpr"] = extract_cpr(ad)
        ad["_cpc"] = float(ad["cpc"]) if ad.get("cpc") and float(ad.get("cpc", 0)) > 0 else None
        ad["_results"] = extract_results(ad)
        follows_30d = extract_follows(ad) or 0
        ad["_follows_30d"] = follows_30d

        # 每日粉絲 delta
        ad_id = ad.get("ad_id", "")
        delta, slowdown, snapshot = compute_follow_delta(
            ad_id, ad.get("ad_name", ""), follows_30d, snapshot
        )
        ad["_follows_delta"] = delta
        ad["_slowdown"] = slowdown

    # 儲存更新後的快照
    save_snapshot(snapshot)

    # 分 ACTIVE / 非 ACTIVE
    active_ads   = [a for a in ad_insights if a.get("ad_status") == "ACTIVE"]
    inactive_ads = [a for a in ad_insights if a.get("ad_status") != "ACTIVE"]

    # ── 頻率警報（只看 ACTIVE）──────────────────────────────────────────────
    freq_stops = [a for a in active_ads if a["_freq"] >= freq_stop]
    freq_warns = [a for a in active_ads if freq_warn <= a["_freq"] < freq_stop]

    if freq_stops:
        print(f"\n🚨 頻率超標（≥{freq_stop}x）— 請立即在 Ads Manager 停用：")
        for ad in sorted(freq_stops, key=lambda x: x["_freq"], reverse=True):
            print(f"   ⛔ [{ad.get('campaign_name','')}] {ad.get('ad_name','未知')} — 頻率 {ad['_freq']:.2f}x")
    else:
        print("\n✅ 無廣告頻率超標")

    if freq_warns:
        print(f"\n⚠️  頻率警告（≥{freq_warn}x）：")
        for ad in sorted(freq_warns, key=lambda x: x["_freq"], reverse=True):
            print(f"   ⚠️  [{ad.get('campaign_name','')}] {ad.get('ad_name','未知')} — 頻率 {ad['_freq']:.2f}x")

    # ── 粉絲增速放緩警報 ────────────────────────────────────────────────────
    slowdown_ads = [a for a in active_ads if a.get("_slowdown")]
    if slowdown_ads:
        print(f"\n📉 粉絲增速放緩（最近2天 vs 前期平均下滑 > 30%）— 考慮換廣告素材：")
        for ad in slowdown_ads:
            print(f"   📉 [{ad.get('campaign_name','')}] {ad.get('ad_name','未知')}")

    # ── ACTIVE 廣告明細 ─────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("📋 今日 ACTIVE 廣告明細（依 Campaign 分組，依頻率排序）")
    print(f"   說明：結果 = 頁面互動次數（按讚/留言/分享/點擊貼文）")
    print(f"{'='*72}")

    if not active_ads:
        print("   （目前無 ACTIVE 廣告）")
    else:
        camp_ads = defaultdict(list)
        for ad in active_ads:
            camp_ads[ad.get("campaign_name", "未知")].append(ad)

        # 依「昨日+粉絲」降序排，沒有數據的排最後
        def sort_key_camp(c):
            return max((a.get("_follows_delta") or 0) for a in camp_ads[c])
        camp_order = sorted(camp_ads.keys(), key=sort_key_camp, reverse=True)

        for camp_name in camp_order:
            # 每個 Campaign 內也依昨日+粉絲排
            ads = sorted(camp_ads[camp_name],
                         key=lambda x: x.get("_follows_delta") or 0, reverse=True)
            print(f"\n🟢 Campaign：{camp_name}")
            print(f"  {'廣告名稱':<26} {'花費':>7} {'頻率':>7} {'累積粉絲':>8} {'昨日+粉':>7} {'CPR':>8} {'CPC':>8}")
            print(f"  {'─'*80}")

            for ad in ads:
                name     = ad.get("ad_name", "未知")[:24]
                spend    = ad["_spend"]
                freq     = ad["_freq"]
                follows  = ad["_follows_30d"]
                delta    = ad["_follows_delta"]
                cpr      = ad["_cpr"]
                cpc      = ad["_cpc"]
                slowdown = ad["_slowdown"]

                freq_icon = "🚨" if freq >= freq_stop else ("⚠️" if freq >= freq_warn else "  ")
                cpr_str   = f"NT${cpr:.2f}" if cpr else "    -"
                cpc_str   = f"NT${cpc:.2f}" if cpc else "    -"
                delta_str = f"+{delta}" if delta is not None else "  -"
                if slowdown:
                    delta_str += "📉"

                if ad.get("_no_data"):
                    print(f"  🟢{name:<25} （剛開啟，尚無花費數據）")
                else:
                    print(f"  🟢{name:<25} NT${spend:>4.0f} {freq_icon}{freq:>4.2f}x {follows:>8} {delta_str:>7} {cpr_str:>8} {cpc_str:>8}")

    # ── 非 ACTIVE 廣告摘要（背景參考）──────────────────────────────────────
    if inactive_ads:
        print(f"\n{'='*72}")
        print("📁 非 ACTIVE 廣告（停用中，僅供策略參考）")
        print(f"{'='*72}")

        camp_inactive = defaultdict(list)
        for ad in inactive_ads:
            camp_inactive[ad.get("campaign_name", "未知")].append(ad)

        for camp_name, ads in sorted(camp_inactive.items()):
            print(f"\n⚫ Campaign：{camp_name}")
            print(f"  {'廣告名稱':<28} {'花費':>7} {'觸及':>7} {'頻率':>6} {'CPR':>9} {'30日粉絲':>8}")
            print(f"  {'─'*74}")
            for ad in sorted(ads, key=lambda x: x["_cpr"] or 999):
                name     = ad.get("ad_name", "未知")[:26]
                spend    = ad["_spend"]
                reach    = int(ad.get("reach", 0))
                freq     = ad["_freq"]
                cpr      = ad["_cpr"]
                follows  = ad["_follows_30d"]

                status_icon = "⏸️ " if ad.get("ad_status") in ("PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED") else "🗑️ "
                cpr_str     = f"NT${cpr:.2f}" if cpr else "     -"
                follows_str = f"+{follows}" if follows else "  -"
                print(f"  {status_icon}{name:<27} NT${spend:>5.0f} {reach:>7,} {freq:>6.2f}x {cpr_str:>9} {follows_str:>8}")

    # ── 今日建議摘要 ────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("💡 今日建議：")

    if freq_stops:
        print(f"   🔴 {len(freq_stops)} 則廣告頻率 ≥ {freq_stop}x，請立即停用")
    if freq_warns:
        print(f"   🟡 {len(freq_warns)} 則廣告頻率接近 {freq_stop}x，準備新素材")
    if slowdown_ads:
        for ad in slowdown_ads:
            print(f"   📉 [{ad.get('campaign_name','')}] {ad.get('ad_name','?')} 粉絲增速放緩，考慮換素材")

    # 最佳廣告（從 ACTIVE 中找）
    valid_ads = [a for a in active_ads if a["_cpr"] and a["_results"] >= 5]
    if valid_ads:
        best = min(valid_ads, key=lambda x: x["_cpr"])
        print(f"   ⭐ 目前最佳 ACTIVE 廣告：{best.get('ad_name','?')} — CPR NT${best['_cpr']:.2f} ({best.get('campaign_name','')})")

    # 從非 active 找有潛力可復活的廣告（CPR 低、粉絲多、頻率 < 1.5）
    revival_candidates = [a for a in inactive_ads
                          if a["_cpr"] and a["_cpr"] < 2.0
                          and a["_freq"] < 1.5
                          and a["_follows_30d"] and a["_follows_30d"] >= 5]
    if revival_candidates:
        best_revival = min(revival_candidates, key=lambda x: x["_cpr"])
        print(f"   💡 可考慮重啟：{best_revival.get('ad_name','?')} — CPR NT${best_revival['_cpr']:.2f}，頻率 {best_revival['_freq']:.2f}x（目前停用）")

    if not freq_stops and not freq_warns and not slowdown_ads:
        print("   🟢 所有 ACTIVE 廣告狀態正常，繼續觀察")

    # ── 儲存 JSON 報告 ───────────────────────────────────────────────────────
    report_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.json")

    report_data = {
        "generated_at": now,
        "frequency_stops": [{"name": a.get("ad_name"), "campaign": a.get("campaign_name"), "freq": a["_freq"]} for a in freq_stops],
        "frequency_warnings": [{"name": a.get("ad_name"), "campaign": a.get("campaign_name"), "freq": a["_freq"]} for a in freq_warns],
        "slowdown_alerts": [{"name": a.get("ad_name"), "campaign": a.get("campaign_name")} for a in slowdown_ads],
        "active_ads": [{
            "campaign": a.get("campaign_name"),
            "ad_name": a.get("ad_name"),
            "spend": a["_spend"],
            "reach": int(a.get("reach", 0)),
            "frequency": a["_freq"],
            "results": a["_results"],
            "cpr": a["_cpr"],
            "cpc": a["_cpc"],
            "follows_30d": a["_follows_30d"],
            "follows_delta_today": a["_follows_delta"],
            "slowdown": a["_slowdown"],
            "no_data": a.get("_no_data", False)
        } for a in active_ads],
        "inactive_ads_summary": [{
            "campaign": a.get("campaign_name"),
            "ad_name": a.get("ad_name"),
            "status": a.get("ad_status"),
            "spend": a["_spend"],
            "frequency": a["_freq"],
            "cpr": a["_cpr"],
            "follows_30d": a["_follows_30d"]
        } for a in inactive_ads]
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\n📁 報告已儲存：{report_path}")
    print("=" * 72)

if __name__ == "__main__":
    run_monitor()
