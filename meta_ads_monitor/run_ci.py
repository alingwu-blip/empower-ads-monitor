#!/usr/bin/env python3
"""
run_ci.py — GitHub Actions 無互動執行腳本
從環境變數讀取 token，執行監控，儲存報告，產生靜態 dashboard HTML。
"""

import os
import sys
import json
from datetime import datetime

# 讓 Python 能 import 同目錄的 monitor.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitor import (
    get_all_ad_insights,
    compute_follow_delta,
    extract_cpr,
    extract_results,
    extract_follows,
    load_snapshot,
    save_snapshot,
)

# ── 從環境變數讀取設定 ─────────────────────────────────────────────────────
def load_config_from_env():
    token = os.environ.get("META_ACCESS_TOKEN", "")
    account_id = os.environ.get("META_AD_ACCOUNT_ID", "")
    if not token or not account_id:
        print("❌ 缺少環境變數 META_ACCESS_TOKEN 或 META_AD_ACCOUNT_ID")
        sys.exit(1)
    return {
        "access_token": token,
        "ad_account_id": account_id,
        "frequency_warning": float(os.environ.get("FREQ_WARNING", "1.8")),
        "frequency_stop": float(os.environ.get("FREQ_STOP", "2.0")),
    }

# ── 產生靜態 HTML ──────────────────────────────────────────────────────────
DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Empower Mindfulness · 廣告監控</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system,"Helvetica Neue",Arial,sans-serif; background:#f5f5f7; color:#1d1d1f; font-size:14px; }
  .header { background:#fff; border-bottom:1px solid #e5e5ea; padding:16px 24px; display:flex; align-items:center; justify-content:space-between; }
  .header h1 { font-size:18px; font-weight:700; }
  .header h1 span { color:#6e6e73; font-weight:400; font-size:14px; margin-left:10px; }
  .badge { background:#f2f2f7; color:#6e6e73; padding:4px 10px; border-radius:20px; font-size:12px; }
  .stale { background:#fff8e6; border:1px solid #ffe08a; border-radius:10px; padding:10px 16px; margin:16px 24px 0; font-size:12px; color:#7a5700; display:none; }
  .content { padding:20px 24px; max-width:1200px; margin:0 auto; }
  .alerts { display:flex; gap:12px; margin-bottom:20px; flex-wrap:wrap; }
  .alert-card { flex:1; min-width:160px; border-radius:12px; padding:14px 16px; }
  .green  { background:#f0faf0; border:1px solid #b5e4b5; }
  .red    { background:#fff0f0; border:1px solid #ffb3b3; }
  .yellow { background:#fffbea; border:1px solid #ffe08a; }
  .blue   { background:#f0f5ff; border:1px solid #b3ceff; }
  .icon { font-size:20px; margin-bottom:4px; }
  .label { font-size:11px; color:#6e6e73; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:2px; }
  .val { font-size:18px; font-weight:700; }
  .detail { font-size:12px; color:#6e6e73; margin-top:2px; }
  .sec { font-size:13px; font-weight:600; color:#6e6e73; text-transform:uppercase; letter-spacing:0.5px; margin:20px 0 10px; }
  .tw { background:#fff; border-radius:12px; border:1px solid #e5e5ea; overflow:hidden; margin-bottom:20px; overflow-x:auto; }
  table { width:100%; border-collapse:collapse; min-width:680px; }
  thead th { background:#f9f9fb; color:#6e6e73; font-size:11px; font-weight:600; text-transform:uppercase; padding:10px 14px; text-align:right; border-bottom:1px solid #e5e5ea; white-space:nowrap; }
  thead th:first-child { text-align:left; }
  thead th.sk { background:#e8f0ff; color:#2563eb; }
  tbody tr { border-bottom:1px solid #f2f2f7; }
  tbody tr:last-child { border-bottom:none; }
  tbody tr:hover { background:#f9f9fb; }
  tbody td { padding:11px 14px; text-align:right; }
  tbody td:first-child { text-align:left; }
  .an { font-weight:500; }
  .cn { font-size:11px; color:#6e6e73; margin-top:2px; }
  .fo { color:#34c759; font-weight:600; }
  .fw { color:#ff9500; font-weight:600; }
  .fs { color:#ff3b30; font-weight:700; }
  .dp { color:#34c759; font-weight:700; }
  .ds { color:#ff9500; }
  .dn { color:#c7c7cc; }
  .cg { color:#34c759; }
  .cm { color:#ff9500; }
  .cb { color:#ff3b30; }
  .tag { display:inline-block; font-size:10px; padding:2px 6px; border-radius:10px; margin-left:4px; vertical-align:middle; }
  .ts { background:#ffe5e5; color:#ff3b30; }
  .tw2{ background:#fff3d6; color:#ff9500; }
  .tb { background:#e5f9e5; color:#1a8c1a; }
  .tt { background:#e8f0ff; color:#2563eb; }
  .tc { background:#f5e5ff; color:#7a1fc0; }
  .cg2{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; }
  .cw { background:#fff; border-radius:12px; border:1px solid #e5e5ea; padding:16px; }
  .cw canvas { max-height:180px; }
  .sugg { background:#fff; border-radius:12px; border:1px solid #e5e5ea; padding:16px 18px; margin-bottom:20px; }
  .sugg ul { list-style:none; }
  .sugg li { padding:7px 0; border-bottom:1px solid #f2f2f7; font-size:13px; }
  .sugg li:last-child { border-bottom:none; }
  .it td { color:#8e8e93; }
  footer { text-align:center; color:#c7c7cc; font-size:11px; padding:20px; }
  @media(max-width:700px){.cg2{grid-template-columns:1fr;}}
</style>
</head>
<body>
<div class="header">
  <h1>📊 廣告監控儀表板 <span id="lu"></span></h1>
  <span class="badge" id="ac">–</span>
</div>
<div class="stale" id="sw"></div>
<div class="content" id="mc"></div>
<footer>Empower Mindfulness · 由 GitHub Actions 每日自動更新</footer>
<script>
const D=__REPORT_DATA__;
function r(data){
  const active=(data.active_ads||[]).slice().sort((a,b)=>(b.follows_delta_today||0)-(a.follows_delta_today||0)||(b.follows_30d||0)-(a.follows_30d||0));
  const inactive=data.inactive_ads_summary||[];
  const fS=data.frequency_stops||[],fW=data.frequency_warnings||[],sA=data.slowdown_alerts||[];
  document.getElementById('lu').textContent='更新：'+(data.generated_at||'');
  document.getElementById('ac').textContent=active.length+' 則廣告';
  if(data.generated_at){const m=data.generated_at.match(/(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2})/);if(m){const age=(Date.now()-new Date(m[1]).getTime())/60000;if(age>180){const e=document.getElementById('sw');e.style.display='';e.innerHTML='⚠️ 報告已超過'+Math.floor(age/60)+'小時未更新';}}}
  const mD=Math.max(...active.map(a=>a.follows_delta_today||0));
  const m3=Math.max(...active.map(a=>a.follows_30d||0));
  const vC=active.filter(a=>a.cpr);const mC=vC.length?Math.min(...vC.map(a=>a.cpr)):null;
  let ah='';
  if(fS.length)ah+=`<div class="alert-card red"><div class="icon">🚨</div><div class="label">頻率超標</div><div class="val">${fS.length} 則</div><div class="detail">請立即停用</div></div>`;
  if(fW.length)ah+=`<div class="alert-card yellow"><div class="icon">⚠️</div><div class="label">頻率警告</div><div class="val">${fW.length} 則</div><div class="detail">接近上限</div></div>`;
  if(sA.length)ah+=`<div class="alert-card blue"><div class="icon">📉</div><div class="label">增速放緩</div><div class="val">${sA.length} 則</div><div class="detail">考慮換素材</div></div>`;
  if(!fS.length&&!fW.length&&!sA.length)ah+=`<div class="alert-card green"><div class="icon">✅</div><div class="label">整體狀態</div><div class="val">正常</div><div class="detail">所有廣告頻率正常</div></div>`;
  const tS=active.reduce((s,a)=>s+(a.spend||0),0);
  const tF=active.reduce((s,a)=>s+(a.follows_delta_today||0),0);
  ah+=`<div class="alert-card green"><div class="icon">💰</div><div class="label">30日總花費</div><div class="val">NT$${tS.toLocaleString()}</div><div class="detail">${active.length} 則廣告</div></div>`;
  ah+=`<div class="alert-card blue"><div class="icon">👥</div><div class="label">昨日新增粉絲</div><div class="val">${tF>0?'+'+tF:'–'}</div><div class="detail">所有廣告合計</div></div>`;
  let ar='';
  for(const ad of active){
    const fc=ad.frequency>=2?'fs':ad.frequency>=1.8?'fw':'fo';
    const ft=ad.frequency>=2?'<span class="tag ts">停！</span>':ad.frequency>=1.8?'<span class="tag tw2">警告</span>':'';
    const dv=ad.follows_delta_today;
    const dh=dv===null||dv===undefined?'<span class="dn">–</span>':ad.slowdown?`<span class="ds">+${dv} 📉</span>`:`<span class="dp">+${dv}</span>`;
    let tg=ft;
    if(dv!==null&&dv>0&&dv===mD)tg+='<span class="tag tb">💪最強</span>';
    if((ad.follows_30d||0)===m3&&m3>0)tg+='<span class="tag tt">👥粉絲王</span>';
    if(ad.cpr&&ad.cpr===mC)tg+='<span class="tag tc">⭐CPR佳</span>';
    const cs=(ad.campaign||'').replace('AB test #','#').substring(0,20);
    const cr=ad.cpr?'NT$'+Number(ad.cpr).toFixed(2):'–';
    const cv=ad.cpc?Number(ad.cpc):null;
    const ck=cv?'NT$'+cv.toFixed(2):'–';
    const cc=cv?(cv<5?'cg':cv<15?'cm':'cb'):'';
    ar+=`<tr><td><div class="an">${ad.ad_name||'–'}${tg}</div><div class="cn">${cs}</div></td><td>NT$${Number(ad.spend||0).toFixed(0)}</td><td class="${fc}">${Number(ad.frequency||0).toFixed(2)}x</td><td>${ad.follows_30d!==null&&ad.follows_30d!==undefined?ad.follows_30d:'–'}</td><td>${dh}</td><td>${cr}</td><td class="${cc}">${ck}</td></tr>`;
  }
  let ir='';
  for(const ad of inactive.slice(0,12)){
    const ic=ad.status==='PAUSED'?'⏸️':'⚫';
    ir+=`<tr><td><div class="an">${ic} ${ad.ad_name||'–'}</div><div class="cn">${(ad.campaign||'').substring(0,25)}</div></td><td>NT$${Number(ad.spend||0).toFixed(0)}</td><td>${Number(ad.frequency||0).toFixed(2)}x</td><td>${ad.cpr?'NT$'+Number(ad.cpr).toFixed(2):'–'}</td><td>${ad.follows_30d?'+'+ad.follows_30d:'–'}</td></tr>`;
  }
  const sg=(data.suggestions||[]).map(s=>`<li>${s}</li>`).join('')||'<li>🟢 所有廣告狀態正常</li>';
  const fa=active.filter(a=>a.follows_30d).sort((a,b)=>(b.follows_30d||0)-(a.follows_30d||0)).slice(0,10);
  const ca=active.filter(a=>a.cpr).sort((a,b)=>a.cpr-b.cpr).slice(0,10);
  document.getElementById('mc').innerHTML=`
    <div class="alerts">${ah}</div>
    <div class="sec">📋 廣告明細（依昨日+粉排序）</div>
    <div class="tw"><table><thead><tr><th style="text-align:left">廣告名稱</th><th>30日花費</th><th>頻率</th><th>累積粉絲</th><th class="sk">昨日+粉 ↓</th><th>CPR</th><th>CPC</th></tr></thead><tbody>${ar||'<tr><td colspan="7" style="text-align:center;padding:20px;color:#8e8e93">無廣告資料</td></tr>'}</tbody></table></div>
    <div class="cg2">
      <div class="cw"><div class="sec" style="margin-top:0">30日累積粉絲</div><canvas id="fc"></canvas></div>
      <div class="cw"><div class="sec" style="margin-top:0">CPR 比較（由低到高）</div><canvas id="cc"></canvas></div>
    </div>
    ${inactive.length?`<div class="sec">📁 停用中廣告</div><div class="tw it"><table><thead><tr><th style="text-align:left">廣告名稱</th><th>花費</th><th>頻率</th><th>CPR</th><th>30日粉絲</th></tr></thead><tbody>${ir}</tbody></table></div>`:''}
    <div class="sec">💡 今日建議</div><div class="sugg"><ul>${sg}</ul></div>`;
  const fx=document.getElementById('fc');
  if(fx&&fa.length)new Chart(fx,{type:'bar',data:{labels:fa.map(a=>a.ad_name.substring(0,10)),datasets:[{data:fa.map(a=>a.follows_30d||0),backgroundColor:'#60a5faaa',borderRadius:6}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true},x:{ticks:{font:{size:11}}}}}});
  const cx=document.getElementById('cc');
  if(cx&&ca.length)new Chart(cx,{type:'bar',data:{labels:ca.map(a=>a.ad_name.substring(0,10)),datasets:[{data:ca.map(a=>Number(a.cpr).toFixed(2)),backgroundColor:ca.map(a=>a.cpr<1?'#34c759aa':a.cpr<2?'#ff9500aa':'#ff3b30aa'),borderRadius:6}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,ticks:{callback:v=>'NT$'+v}},x:{ticks:{font:{size:11}}}}}});
}
r(D);

// 每日增粉折線圖
const SNAP=__SNAPSHOT_DATA__;
(function(){
  const names=Object.keys(SNAP);
  if(!names.length) return;
  // 收集所有日期
  const dateSet=new Set();
  names.forEach(n=>SNAP[n].forEach(p=>dateSet.add(p.date)));
  const dates=[...dateSet].sort();
  if(dates.length<2) return;
  // 顏色池
  const colors=['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#f97316','#84cc16'];
  const datasets=names.map((n,i)=>({
    label:n.substring(0,14),
    data:dates.map(d=>{const p=SNAP[n].find(x=>x.date===d);return p?p.delta:null;}),
    borderColor:colors[i%colors.length],
    backgroundColor:colors[i%colors.length]+'22',
    tension:0.3,
    spanGaps:true,
    pointRadius:4,
    borderWidth:2,
  }));
  // 插入圖表 DOM
  const wrap=document.createElement('div');
  wrap.style.cssText='background:#fff;border-radius:12px;border:1px solid #e5e5ea;padding:16px;margin-bottom:20px;';
  wrap.innerHTML='<div style="font-size:13px;font-weight:600;color:#6e6e73;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px">📈 每日增粉趨勢（各廣告）</div><canvas id="trendChart" style="max-height:220px"></canvas>';
  const mc=document.getElementById('mc');
  if(mc && mc.firstChild) mc.insertBefore(wrap, mc.firstChild);
  const ctx=document.getElementById('trendChart');
  if(ctx) new Chart(ctx,{
    type:'line',
    data:{labels:dates,datasets},
    options:{responsive:true,interaction:{mode:'index',intersect:false},
      plugins:{legend:{position:'bottom',labels:{font:{size:11},boxWidth:12}}},
      scales:{
        y:{beginAtZero:true,title:{display:true,text:'當日新增粉絲'}},
        x:{ticks:{font:{size:10},maxTicksLimit:10}}
      }
    }
  });
})();
</script>
</body>
</html>"""

def generate_html(report_data, snapshot_chart=None):
    report_json = json.dumps(report_data, ensure_ascii=False)
    snap_json   = json.dumps(snapshot_chart or {}, ensure_ascii=False)
    return DASHBOARD_TEMPLATE.replace("__REPORT_DATA__", report_json).replace("__SNAPSHOT_DATA__", snap_json)

# ── 主流程 ─────────────────────────────────────────────────────────────────
def main():
    config = load_config_from_env()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M")
    freq_warn = config["frequency_warning"]
    freq_stop = config["frequency_stop"]

    print(f"⏳ 開始拉取廣告數據... ({now})")
    ad_insights, _ = get_all_ad_insights(config)

    if not ad_insights:
        print("❌ 無法取得廣告數據")
        sys.exit(1)

    snapshot = load_snapshot()

    for ad in ad_insights:
        ad["_freq"]    = float(ad.get("frequency", 0))
        ad["_spend"]   = float(ad.get("spend", 0))
        ad["_cpr"]     = extract_cpr(ad)
        ad["_cpc"]     = float(ad["cpc"]) if ad.get("cpc") and float(ad.get("cpc", 0)) > 0 else None
        ad["_results"] = extract_results(ad)
        follows_30d    = extract_follows(ad) or 0
        ad["_follows_30d"] = follows_30d

        ad_id = ad.get("ad_id", "")
        delta, slowdown, snapshot = compute_follow_delta(
            ad_id, ad.get("ad_name", ""), follows_30d, snapshot
        )
        ad["_follows_delta"] = delta
        ad["_slowdown"]      = slowdown

    save_snapshot(snapshot)

    active_ads   = [a for a in ad_insights if a.get("ad_status") == "ACTIVE"]
    inactive_ads = [a for a in ad_insights if a.get("ad_status") != "ACTIVE"]
    freq_stops   = [a for a in active_ads if a["_freq"] >= freq_stop]
    freq_warns   = [a for a in active_ads if freq_warn <= a["_freq"] < freq_stop]
    slowdown_ads = [a for a in active_ads if a.get("_slowdown")]

    print(f"✅ ACTIVE：{len(active_ads)} 則 | 超標：{len(freq_stops)} | 警告：{len(freq_warns)}")

    # 建議
    suggestions = []
    for a in freq_stops:
        suggestions.append(f"🔴 頻率超標：{a.get('ad_name')}（{a['_freq']:.2f}x），請立即停用")
    for a in freq_warns:
        suggestions.append(f"🟡 頻率警告：{a.get('ad_name')}（{a['_freq']:.2f}x），準備新素材")
    for a in slowdown_ads:
        suggestions.append(f"📉 增速放緩：{a.get('ad_name')}，考慮換廣告素材")
    valid = [a for a in active_ads if a["_cpr"] and a["_results"] >= 5]
    if valid:
        best = min(valid, key=lambda x: x["_cpr"])
        suggestions.append(f"⭐ 最佳廣告：{best.get('ad_name')}（{best.get('campaign_name','')}），CPR NT${best['_cpr']:.2f}")
    revival = [a for a in inactive_ads if a["_cpr"] and a["_cpr"] < 2.0 and a["_freq"] < 1.5
               and a["_follows_30d"] and a["_follows_30d"] >= 5]
    if revival:
        r = min(revival, key=lambda x: x["_cpr"])
        suggestions.append(f"💡 可考慮重啟：{r.get('ad_name')}，CPR NT${r['_cpr']:.2f}，頻率 {r['_freq']:.2f}x")
    if not suggestions:
        suggestions.append("🟢 所有 ACTIVE 廣告狀態正常，繼續觀察")

    report_data = {
        "generated_at": now,
        "frequency_stops":   [{"name": a.get("ad_name"), "campaign": a.get("campaign_name"), "freq": a["_freq"]} for a in freq_stops],
        "frequency_warnings":[{"name": a.get("ad_name"), "campaign": a.get("campaign_name"), "freq": a["_freq"]} for a in freq_warns],
        "slowdown_alerts":   [{"name": a.get("ad_name"), "campaign": a.get("campaign_name")} for a in slowdown_ads],
        "active_ads": [{
            "campaign": a.get("campaign_name"), "ad_name": a.get("ad_name"),
            "spend": a["_spend"], "reach": int(a.get("reach", 0)),
            "frequency": a["_freq"], "results": a["_results"],
            "cpr": a["_cpr"], "cpc": a["_cpc"],
            "follows_30d": a["_follows_30d"], "follows_delta_today": a["_follows_delta"],
            "slowdown": a["_slowdown"], "no_data": a.get("_no_data", False),
        } for a in active_ads],
        "inactive_ads_summary": [{
            "campaign": a.get("campaign_name"), "ad_name": a.get("ad_name"),
            "status": a.get("ad_status"), "spend": a["_spend"],
            "frequency": a["_freq"], "cpr": a["_cpr"], "follows_30d": a["_follows_30d"],
        } for a in inactive_ads],
        "suggestions": suggestions,
    }

    # 從 snapshot 建立每日增粉折線圖數據（只取 active 廣告）
    active_names = {a.get("ad_name") for a in active_ads}
    snapshot_chart = {}
    for ad_id, entry in snapshot.items():
        ad_name = entry.get("ad_name", "")
        if ad_name not in active_names:
            continue
        history = entry.get("history", [])
        if len(history) < 2:
            continue
        deltas = []
        for i in range(1, len(history)):
            d = history[i]["follows"] - history[i-1]["follows"]
            deltas.append({"date": history[i]["date"], "delta": max(0, d)})
        if deltas:
            snapshot_chart[ad_name] = deltas

    # 儲存 JSON（時間戳 + latest 兩份）
    report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    os.makedirs(report_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    for fname in [f"report_{ts}.json", "latest.json"]:
        with open(os.path.join(report_dir, fname), "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
    print(f"📁 報告已儲存 (reports/report_{ts}.json + reports/latest.json)")

    # 產生 dashboard HTML
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dashboard_dir = os.path.join(repo_root, "dashboard")
    os.makedirs(dashboard_dir, exist_ok=True)
    html_path = os.path.join(dashboard_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(generate_html(report_data, snapshot_chart))
    print(f"🌐 Dashboard 已產生：dashboard/index.html")


if __name__ == "__main__":
    main()
