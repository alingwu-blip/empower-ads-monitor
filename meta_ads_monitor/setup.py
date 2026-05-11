#!/usr/bin/env python3
"""
Empower Mindfulness - Meta Ads Monitor
Step 1: Setup - Find your Ad Account ID and verify connection
"""

import urllib.request
import urllib.parse
import json
import os

# ============================================================
# 👇 貼上你的 Access Token（每次過期需要更新）
# ============================================================
ACCESS_TOKEN = "在這裡貼上你的 Token"

BASE_URL = "https://graph.facebook.com/v19.0"

def api_call(endpoint, params=None):
    if params is None:
        params = {}
    params["access_token"] = ACCESS_TOKEN
    url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.urlopen(url, timeout=15)
        return json.loads(req.read())
    except urllib.error.HTTPError as e:
        error_body = json.loads(e.read())
        print(f"❌ API Error: {error_body.get('error', {}).get('message', 'Unknown error')}")
        return None
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return None

def main():
    print("=" * 55)
    print("  Empower Mindfulness - Meta Ads API 設定檢查")
    print("=" * 55)

    # 1. 驗證 Token
    print("\n📡 Step 1：驗證 Access Token...")
    me = api_call("me", {"fields": "id,name"})
    if not me:
        print("❌ Token 無效或已過期，請重新取得 Token")
        return
    print(f"✅ 連線成功！帳號：{me.get('name')} (ID: {me.get('id')})")

    # 2. 找廣告帳號
    print("\n📋 Step 2：找你的廣告帳號...")
    ad_accounts = api_call("me/adaccounts", {
        "fields": "id,name,account_status,currency,amount_spent"
    })
    if not ad_accounts or "data" not in ad_accounts:
        print("❌ 找不到廣告帳號，請確認 Token 有 ads_read 權限")
        return

    accounts = ad_accounts["data"]
    print(f"\n找到 {len(accounts)} 個廣告帳號：\n")
    for i, acc in enumerate(accounts):
        status_map = {1: "✅ 啟用", 2: "❌ 停用", 3: "⚠️ 未確認", 9: "🔒 關閉"}
        status = status_map.get(acc.get("account_status"), "未知")
        spent = float(acc.get("amount_spent", 0)) / 100
        print(f"  [{i+1}] {acc.get('name')}")
        print(f"      ID: {acc.get('id')}")
        print(f"      狀態: {status} | 貨幣: {acc.get('currency')} | 總花費: {spent:.0f}")
        print()

    # 3. 儲存設定
    if len(accounts) == 1:
        chosen = accounts[0]
    else:
        choice = input("請輸入要使用的廣告帳號編號（數字）：")
        chosen = accounts[int(choice) - 1]

    config = {
        "access_token": ACCESS_TOKEN,
        "ad_account_id": chosen["id"],
        "ad_account_name": chosen["name"],
        "frequency_warning": 1.8,
        "frequency_stop": 2.0
    }

    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"✅ 設定已儲存！")
    print(f"   廣告帳號：{chosen['name']}")
    print(f"   帳號 ID：{chosen['id']}")
    print(f"\n🎉 設定完成！接下來可以執行 monitor.py 開始監控。")

if __name__ == "__main__":
    main()
