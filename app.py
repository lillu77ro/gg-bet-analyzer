"""
NORD ALLASKA SUPREME — VALUE BET SCANNER
Surse: API-Football PRO + Betano
Metodologie: Expected Value (EV) = Prob. Reală - Prob. Implicită
Cote: 1.75 — 3.00 | EV minim: 5%
"""

import streamlit as st
import requests
from datetime import date, datetime, timezone, timedelta
import base64 as _b64

st.set_page_config(page_title="NORD ALLASKA SUPREME", page_icon="🏔️", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html,body,[class*="css"]{ font-family:'Inter',sans-serif; }
.stApp{ background:linear-gradient(135deg,#0a0e1a 0%,#0f1629 50%,#0a1628 100%); color:#e2e8f0; }
.main-header{ text-align:center; padding:2rem 0 1.5rem 0; }
.main-header h1{ font-size:2.8rem; font-weight:800; background:linear-gradient(90deg,#38bdf8,#818cf8,#f472b6); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
.main-header p{ color:#94a3b8; font-size:1.05rem; }
.metric-card{ background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:16px; padding:1.4rem 1.6rem; text-align:center; }
.metric-card .value{ font-size:2.2rem; font-weight:800; }
.metric-card .label{ font-size:0.82rem; color:#94a3b8; margin-top:0.3rem; text-transform:uppercase; letter-spacing:0.06em; }
.divider{ border:none; border-top:1px solid rgba(255,255,255,0.07); margin:1.5rem 0; }
.footer-note{ background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.2); border-radius:12px; padding:1rem 1.4rem; margin-top:2rem; font-size:0.82rem; color:#fca5a5; line-height:1.6; }
#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}
</style>
""", unsafe_allow_html=True)

API_KEY = _b64.b64decode(b'MjgxZTdhMGNmMjg0ZWViYTcwNWUyYWUxMWYzZDc3MjI=').decode()
API_BASE = "https://v3.football.api-sports.io"
API_HEADERS = {"x-apisports-key": API_KEY}
BETANO_ID = 32
MIN_ODDS = 1.75
MAX_ODDS = 3.00
MIN_EV = 5.0
NUM_MATCHES = 15
MIN_DATA = 5
RO_TZ = timezone(timedelta(hours=3))
EXCLUDE_WORDS = ["Women","Youth","U17","U19","U20","U21","U23","U18","U22","Reserve","Reserves","Amateur","Amateurs","Beach Soccer","Futsal","Indoor","eSoccer","Esports","SRL","Simulated","Virtual","Cyber","Friendlies","Friendly"]
EXCLUDE_TEAM = [" W"," Women"," Ladies"," Femenino"," Femminile"," Frauen"]
SUPPORTED_BETS = ["Match Winner","Both Teams Score","Goals Over/Under","Double Chance","Home/Away","Goals Over/Under First Half","Goals Over/Under Second Half","First Half Winner","Second Half Winner","Total - Home","Total - Away","Clean Sheet - Home","Clean Sheet - Away","Win to Nil - Home","Win to Nil - Away","Both Teams Score - First Half","Both Teams Score - Second Half","Highest Scoring Half","To Score In Both Halves"]


def api_get(ep, params=None):
    try:
        return requests.get(f"{API_BASE}/{ep}", headers=API_HEADERS, params=params, timeout=20).json().get("response", [])
    except:
        return []

def fetch_fixtures(ds):
    out = []
    for f in api_get("fixtures", {"date": ds}):
        fx = f.get("fixture",{}); lg = f.get("league",{}); ts = f.get("teams",{})
        if fx.get("status",{}).get("short") != "NS": continue
        ln = lg.get("name",""); cn = lg.get("country","")
        if any(w.lower() in f"{ln} {cn}".lower() for w in EXCLUDE_WORDS): continue
        hn = ts.get("home",{}).get("name",""); an = ts.get("away",{}).get("name","")
        if any(hn.endswith(s) or an.endswith(s) for s in EXCLUDE_TEAM): continue
        try:
            dt = datetime.fromisoformat(fx.get("date","").replace("Z","+00:00")).astimezone(RO_TZ)
            t_str = dt.strftime("%H:%M"); stamp = dt.timestamp()
        except: t_str = ""; stamp = 0
        out.append({"fid": fx.get("id"), "time": t_str, "ts": stamp, "home": hn, "away": an, "hid": ts.get("home",{}).get("id"), "aid": ts.get("away",{}).get("id"), "league": ln, "country": cn})
    return out

def fetch_all_odds(ds, bk_id):
    out = {}; page = 1
    while page <= 21:
        data = requests.get(f"{API_BASE}/odds", headers=API_HEADERS, params={"date": ds, "bookmaker": bk_id, "page": page}, timeout=20).json()
        for item in data.get("response",[]):
            fid = item.get("fixture",{}).get("id"); bets = []
            for b in item.get("bookmakers",[]): bets.extend(b.get("bets",[]))
            if fid: out[fid] = bets
        if page >= data.get("paging",{}).get("total",1): break
        page += 1
    return out

def calc_stats(matches, tid, ctx="all"):
    w=d=l=gg=o15=o25=o35=cs=gf=ga=n=0; form=[]
    for m in matches:
        t=m.get("teams",{}); g=m.get("goals",{}); hid=t.get("home",{}).get("id"); gh=g.get("home"); gav=g.get("away")
        if gh is None or gav is None: continue
        is_h = hid == tid
        if ctx=="home" and not is_h: continue
        if ctx=="away" and is_h: continue
        n+=1; sc=gh if is_h else gav; co=gav if is_h else gh; tot=gh+gav; gf+=sc; ga+=co
        if sc>co: w+=1; form.append("W")
        elif sc==co: d+=1; form.append("D")
        else: l+=1; form.append("L")
        if gh>0 and gav>0: gg+=1
        if tot>=2: o15+=1
        if tot>=3: o25+=1
        if tot>=4: o35+=1
        if co==0: cs+=1
    if n==0: return None
    return {"n":n,"w":w,"d":d,"l":l,"win_pct":round(w/n*100,1),"draw_pct":round(d/n*100,1),"loss_pct":round(l/n*100,1),"gg_pct":round(gg/n*100,1),"o15_pct":round(o15/n*100,1),"o25_pct":round(o25/n*100,1),"o35_pct":round(o35/n*100,1),"cs_pct":round(cs/n*100,1),"avg_gf":round(gf/n,2),"avg_ga":round(ga/n,2),"form":"".join(form[:5])}

def calc_probs(hs, has, h2):
    p = {}
    def bl(hv,av,h2v=None):
        return round(hv*0.4+av*0.4+h2v*0.2,1) if h2v is not None else round(hv*0.5+av*0.5,1)
    h2s = h2 if h2 else None
    p1r=(hs["win_pct"]+has["loss_pct"])/2+3; p2r=(has["win_pct"]+hs["loss_pct"])/2; pxr=100-p1r-p2r
    if pxr<5: pxr=15; p1r=(100-15)*p1r/(p1r+p2r); p2r=100-15-p1r
    tot=p1r+pxr+p2r; p["p1"]=round(p1r/tot*100,1); p["px"]=round(pxr/tot*100,1); p["p2"]=round(p2r/tot*100,1)
    p["p1x"]=round(p["p1"]+p["px"],1); p["px2"]=round(p["px"]+p["p2"],1); p["p12"]=round(p["p1"]+p["p2"],1)
    p["dnb_h"]=p["p1x"]; p["dnb_a"]=p["px2"]
    p["gg"]=bl(hs["gg_pct"],has["gg_pct"],h2s["gg_pct"] if h2s else None); p["ng"]=round(100-p["gg"],1)
    for ln,k in [("15","o15_pct"),("25","o25_pct"),("35","o35_pct")]:
        p[f"o{ln}"]=bl(hs[k],has[k],h2s[k] if h2s else None); p[f"u{ln}"]=round(100-p[f"o{ln}"],1)
    p["cs_h_y"]=round(hs["cs_pct"]*0.5+(100-has["gg_pct"])*0.5,1); p["cs_h_n"]=round(100-p["cs_h_y"],1)
    p["cs_a_y"]=round(has["cs_pct"]*0.5+(100-hs["gg_pct"])*0.5,1); p["cs_a_n"]=round(100-p["cs_a_y"],1)
    p["wtn_h"]=round(p["p1"]*p["cs_h_y"]/100,1); p["wtn_a"]=round(p["p2"]*p["cs_a_y"]/100,1)
    p["wtn_h_n"]=round(100-p["wtn_h"],1); p["wtn_a_n"]=round(100-p["wtn_a"],1)
    p["fh_o05"]=round(p["o15"]*0.85,1); p["fh_o15"]=round(p["o25"]*0.70,1); p["fh_o25"]=round(p["o35"]*0.50,1)
    p["fh_u05"]=round(100-p["fh_o05"],1); p["fh_u15"]=round(100-p["fh_o15"],1); p["fh_u25"]=round(100-p["fh_o25"],1)
    p["sh_o05"]=round(p["o15"]*0.90,1); p["sh_o15"]=round(p["o25"]*0.75,1); p["sh_o25"]=round(p["o35"]*0.55,1)
    p["sh_u05"]=round(100-p["sh_o05"],1); p["sh_u15"]=round(100-p["sh_o15"],1); p["sh_u25"]=round(100-p["sh_o25"],1)
    p["fh1"]=round(p["p1"]*0.65,1); p["fh2"]=round(p["p2"]*0.60,1); p["fhx"]=round(100-p["fh1"]-p["fh2"],1)
    p["sh1"]=round(p["p1"]*0.60,1); p["sh2"]=round(p["p2"]*0.55,1); p["shx"]=round(100-p["sh1"]-p["sh2"],1)
    ha=hs["avg_gf"]; aa=has["avg_gf"]
    p["ho05"]=min(95,round(85+ha*5,1)); p["ho15"]=round(min(90,ha/(ha+0.5)*100),1); p["ho25"]=round(min(85,ha/(ha+1)*100*0.7),1)
    p["hu05"]=round(100-p["ho05"],1); p["hu15"]=round(100-p["ho15"],1); p["hu25"]=round(100-p["ho25"],1)
    p["ao05"]=min(95,round(80+aa*5,1)); p["ao15"]=round(min(90,aa/(aa+0.5)*100),1); p["ao25"]=round(min(85,aa/(aa+1)*100*0.7),1)
    p["au05"]=round(100-p["ao05"],1); p["au15"]=round(100-p["ao15"],1); p["au25"]=round(100-p["ao25"],1)
    p["gg_fh"]=round(p["gg"]*0.55,1); p["ng_fh"]=round(100-p["gg_fh"],1)
    p["gg_sh"]=round(p["gg"]*0.60,1); p["ng_sh"]=round(100-p["gg_sh"],1)
    p["ah_h-05"]=p["p1"]; p["ah_a+05"]=round(100-p["p1"],1)
    p["ah_h+05"]=round(p["p1"]+p["px"],1); p["ah_a-05"]=p["p2"]
    p["ah_h-10"]=round(p["p1"]*0.75,1); p["ah_a+10"]=round(100-p["ah_h-10"],1)
    p["ah_h+10"]=min(95,round(p["p1"]+p["px"]+p["p2"]*0.3,1)); p["ah_a-10"]=round(100-p["ah_h+10"],1)
    p["ah_h-15"]=round(p["p1"]*0.55,1); p["ah_a+15"]=round(100-p["ah_h-15"],1)
    p["ah_h+15"]=min(97,round(p["p1"]+p["px"]+p["p2"]*0.5,1)); p["ah_a-15"]=round(100-p["ah_h+15"],1)
    p["ah_h-20"]=round(p["p1"]*0.40,1); p["ah_a+20"]=round(100-p["ah_h-20"],1)
    p["ah_h-25"]=round(p["p1"]*0.30,1); p["ah_a+25"]=round(100-p["ah_h-25"],1)
    p["hsh1"]=45.0; p["hsh2"]=48.0; p["hshe"]=7.0
    p["tsibh_h"]=round(p["p1"]*0.35,1); p["tsibh_a"]=round(p["p2"]*0.30,1)
    return p

def map_prob(bn, vl, p):
    M = {
        ("Match Winner","Home"):p.get("p1"),("Match Winner","Draw"):p.get("px"),("Match Winner","Away"):p.get("p2"),
        ("Both Teams Score","Yes"):p.get("gg"),("Both Teams Score","No"):p.get("ng"),
        ("Double Chance","Home/Draw"):p.get("p1x"),("Double Chance","Draw/Away"):p.get("px2"),("Double Chance","Home/Away"):p.get("p12"),
        ("Home/Away","Home"):p.get("dnb_h"),("Home/Away","Away"):p.get("dnb_a"),
        ("First Half Winner","Home"):p.get("fh1"),("First Half Winner","Draw"):p.get("fhx"),("First Half Winner","Away"):p.get("fh2"),
        ("Second Half Winner","Home"):p.get("sh1"),("Second Half Winner","Draw"):p.get("shx"),("Second Half Winner","Away"):p.get("sh2"),
        ("Clean Sheet - Home","Yes"):p.get("cs_h_y"),("Clean Sheet - Home","No"):p.get("cs_h_n"),
        ("Clean Sheet - Away","Yes"):p.get("cs_a_y"),("Clean Sheet - Away","No"):p.get("cs_a_n"),
        ("Win to Nil - Home","Yes"):p.get("wtn_h"),("Win to Nil - Home","No"):p.get("wtn_h_n"),
        ("Win to Nil - Away","Yes"):p.get("wtn_a"),("Win to Nil - Away","No"):p.get("wtn_a_n"),
        ("Both Teams Score - First Half","Yes"):p.get("gg_fh"),("Both Teams Score - First Half","No"):p.get("ng_fh"),
        ("Both Teams Score - Second Half","Yes"):p.get("gg_sh"),("Both Teams Score - Second Half","No"):p.get("ng_sh"),
        ("Highest Scoring Half","1st Half"):p.get("hsh1"),("Highest Scoring Half","2nd Half"):p.get("hsh2"),("Highest Scoring Half","Equal"):p.get("hshe"),
        ("To Score In Both Halves","Home"):p.get("tsibh_h"),("To Score In Both Halves","Away"):p.get("tsibh_a"),
    }
    key = (bn, vl)
    if key in M: return M[key]
    OU = {"Goals Over/Under":{"Over 1.5":"o15","Under 1.5":"u15","Over 2.5":"o25","Under 2.5":"u25","Over 3.5":"o35","Under 3.5":"u35"},
          "Goals Over/Under First Half":{"Over 0.5":"fh_o05","Under 0.5":"fh_u05","Over 1.5":"fh_o15","Under 1.5":"fh_u15","Over 2.5":"fh_o25","Under 2.5":"fh_u25"},
          "Goals Over/Under Second Half":{"Over 0.5":"sh_o05","Under 0.5":"sh_u05","Over 1.5":"sh_o15","Under 1.5":"sh_u15","Over 2.5":"sh_o25","Under 2.5":"sh_u25"},
          "Total - Home":{"Over 0.5":"ho05","Under 0.5":"hu05","Over 1.5":"ho15","Under 1.5":"hu15","Over 2.5":"ho25","Under 2.5":"hu25"},
          "Total - Away":{"Over 0.5":"ao05","Under 0.5":"au05","Over 1.5":"ao15","Under 1.5":"au15","Over 2.5":"ao25","Under 2.5":"au25"}}
    if bn in OU and vl in OU[bn]: return p.get(OU[bn][vl])
    AH = {"Home -0.5":"ah_h-05","Away +0.5":"ah_a+05","Home -1":"ah_h-10","Away +1":"ah_a+10","Home -1.5":"ah_h-15","Away +1.5":"ah_a+15","Home -2":"ah_h-20","Away +2":"ah_a+20","Home -2.5":"ah_h-25","Away +2.5":"ah_a+25","Home +0.5":"ah_h+05","Away -0.5":"ah_a-05","Home +1":"ah_h+10","Away -1":"ah_a-10","Home +1.5":"ah_h+15","Away -1.5":"ah_a-15"}
    if bn=="Asian Handicap" and vl in AH: return p.get(AH[vl])
    return None

def tr_bet(bn, vl):
    T = {("Match Winner","Home"):"1 Gazdă",("Match Winner","Draw"):"X Egal",("Match Winner","Away"):"2 Oaspete",("Both Teams Score","Yes"):"GG Da",("Both Teams Score","No"):"GG Nu",("Double Chance","Home/Draw"):"1X",("Double Chance","Draw/Away"):"X2",("Double Chance","Home/Away"):"12",("Home/Away","Home"):"Gazdă DNB",("Home/Away","Away"):"Oaspete DNB",("First Half Winner","Home"):"R1 Gazdă",("First Half Winner","Draw"):"R1 Egal",("First Half Winner","Away"):"R1 Oaspete",("Second Half Winner","Home"):"R2 Gazdă",("Second Half Winner","Draw"):"R2 Egal",("Second Half Winner","Away"):"R2 Oaspete",("Clean Sheet - Home","Yes"):"CS Gazdă Da",("Clean Sheet - Home","No"):"CS Gazdă Nu",("Clean Sheet - Away","Yes"):"CS Oaspete Da",("Clean Sheet - Away","No"):"CS Oaspete Nu",("Win to Nil - Home","Yes"):"Gazdă fără gol",("Win to Nil - Away","Yes"):"Oaspete fără gol",("Both Teams Score - First Half","Yes"):"GG R1",("Both Teams Score - First Half","No"):"NG R1",("Both Teams Score - Second Half","Yes"):"GG R2",("Both Teams Score - Second Half","No"):"NG R2"}
    if (bn,vl) in T: return T[(bn,vl)]
    if "Over" in vl or "Under" in vl:
        pts=vl.split(" ")
        if len(pts)==2:
            d="Peste" if pts[0]=="Over" else "Sub"; pre=""
            if "First Half" in bn: pre="R1 "
            elif "Second Half" in bn: pre="R2 "
            elif "Home" in bn: pre="Gazdă "
            elif "Away" in bn: pre="Oaspete "
            return f"{pre}{d} {pts[1]}"
    if "Handicap" in bn: return f"AH {vl}"
    return f"{bn} {vl}"

def find_vb(bets, probs, bk):
    vbs = []
    for bet in bets:
        bn = bet.get("name","")
        if bn not in SUPPORTED_BETS: continue
        for val in bet.get("values",[]):
            try: odds = float(val.get("odd","0"))
            except: continue
            if odds < MIN_ODDS or odds > MAX_ODDS: continue
            vl = str(val.get("value",""))
            rp = map_prob(bn, vl, probs)
            if rp is None: continue
            ip = round(1/odds*100,1); ev = round(rp-ip,1)
            if ev >= MIN_EV and rp >= 85:
                vbs.append({"market":tr_bet(bn,vl),"odds":odds,"rp":rp,"ip":ip,"ev":ev,"bk":bk})
    return vbs

@st.cache_data(ttl=3600)
def load_data():
    today = date.today().strftime("%Y-%m-%d")
    fixes = fetch_fixtures(today)
    b_odds = fetch_all_odds(today, BETANO_ID)
    for f in fixes: f["b_bets"]=b_odds.get(f["fid"],[])
    results = []
    for f in fixes:
        if not f["b_bets"]: continue
        hm = api_get("fixtures",{"team":f["hid"],"last":NUM_MATCHES})
        am = api_get("fixtures",{"team":f["aid"],"last":NUM_MATCHES})
        h2h = api_get("fixtures/headtohead",{"h2h":f"{f['hid']}-{f['aid']}","last":10})
        hs = calc_stats(hm,f["hid"],"home"); has_=calc_stats(am,f["aid"],"away")
        h2s = calc_stats(h2h,f["hid"],"all") if h2h else None
        if not hs or not has_: continue
        if hs["n"]<MIN_DATA or has_["n"]<MIN_DATA: continue
        probs = calc_probs(hs, has_, h2s)
        vb = find_vb(f["b_bets"],probs,"Betano")
        if not vb: continue
        best_m = {}
        for v in vb:
            k=v["market"]
            if k not in best_m or v["odds"]>best_m[k]["odds"]: best_m[k]=v
        sv = sorted(best_m.values(),key=lambda x:x["ev"],reverse=True)
        b = sv[0]
        results.append({"time":f["time"],"ts":f["ts"],"home":f["home"],"away":f["away"],"league":f["league"],"country":f["country"],"market":b["market"],"odds":b["odds"],"ev":b["ev"],"prob":b["rp"],"bk":b["bk"],"hf":hs.get("form",""),"af":has_.get("form","")})
    results.sort(key=lambda x:x["ts"])
    return results, today

def ev_color(ev):
    if ev>=15: return "#34d399"
    elif ev>=10: return "#f59e0b"
    return "#38bdf8"

def ev_bg(ev):
    if ev>=15: return "rgba(52,211,153,0.15)"
    elif ev>=10: return "rgba(245,158,11,0.12)"
    return "rgba(56,189,248,0.10)"

today_str = datetime.now(RO_TZ).strftime("%d %B %Y")
st.markdown(f'<div class="main-header"><h1>🏔️ NORD ALLASKA SUPREME</h1><p>Value Bet Scanner · Betano · {today_str}</p></div>', unsafe_allow_html=True)
col_r = st.columns([1,2,1])
with col_r[1]:
    refresh = st.button("🔄 Scanează Value Bets", use_container_width=True, type="primary")
    st.markdown("<div style='text-align:center;font-size:0.75rem;color:#475569;margin-top:4px;'>API-Football PRO · Betano · Cote 1.75–3.00 · EV > 5%</div>", unsafe_allow_html=True)
if refresh: st.cache_data.clear()

with st.spinner("⏳ Scanez meciurile și cotele de pe Betano..."):
    matches, dd = load_data()

st.markdown('<hr class="divider">', unsafe_allow_html=True)
total = len(matches); high = len([m for m in matches if m["ev"]>=15]); avg = round(sum(m["ev"] for m in matches)/max(total,1),1)
mc = st.columns(4)
for col,(ic,v,lb,c) in zip(mc,[("🎯",str(total),"Value Bets","#38bdf8"),("🔥",str(high),"High EV (>15%)","#34d399"),("⚽",str(total),"Meciuri","#f59e0b"),("📈",f"+{avg}%","EV Mediu","#a78bfa")]):
    col.markdown(f"<div class='metric-card'><div class='value' style='color:{c};'>{ic} {v}</div><div class='label'>{lb}</div></div>", unsafe_allow_html=True)
st.markdown('<hr class="divider">', unsafe_allow_html=True)

if not matches:
    st.markdown("<div style='text-align:center;padding:3rem;color:#64748b;font-size:1.2rem;'>🔍 Nu am găsit value bets azi.<br><span style='font-size:0.85rem;'>Meciurile nu au cote între 1.75–3.00 cu EV > 5%</span></div>", unsafe_allow_html=True)
else:
    st.markdown(f"<div style='font-size:1.15rem;font-weight:700;color:#e2e8f0;margin:1rem 0;'>🎯 Value Bets — {total} meciuri cu valoare</div>", unsafe_allow_html=True)
    hc = st.columns([0.5,1.8,1.0,0.5,1.3,0.5,0.5,0.5,0.6])
    for col,h in zip(hc,["🕐","⚽ Meci","🏆 Liga","🌍","🎯 Pariu","💰 Cotă","✅ Prob","📈 EV","🏦"]):
        col.markdown(f"<span style='font-size:0.7rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;'>{h}</span>", unsafe_allow_html=True)
    st.markdown('<hr style="border-top:1px solid rgba(255,255,255,0.06);margin:0.3rem 0 0.6rem;">', unsafe_allow_html=True)
    for i,m in enumerate(matches):
        ev=m["ev"]; c=ev_color(ev); bg=ev_bg(ev)
        cols = st.columns([0.5,1.8,1.0,0.5,1.3,0.5,0.5,0.5,0.6])
        cols[0].markdown(f"<div style='border-left:4px solid {c};padding-left:10px;font-weight:700;color:#cbd5e1;'>{m['time']}</div>", unsafe_allow_html=True)
        cols[1].markdown(f"<div style='font-weight:700;color:#f1f5f9;font-size:0.95rem;'>{m['home']} <span style='color:#64748b;'>vs</span> {m['away']}</div>", unsafe_allow_html=True)
        cols[2].markdown(f"<div style='font-size:0.8rem;color:#94a3b8;'>{m['league']}</div>", unsafe_allow_html=True)
        cols[3].markdown(f"<div style='font-size:0.75rem;color:#475569;'>{m['country']}</div>", unsafe_allow_html=True)
        cols[4].markdown(f"<span style='display:inline-block;background:{bg};border:1px solid {c};color:{c};font-size:0.85rem;font-weight:700;padding:4px 12px;border-radius:10px;'>{m['market']}</span>", unsafe_allow_html=True)
        cols[5].markdown(f"<div style='font-size:1.05rem;font-weight:700;color:#f1f5f9;'>{m['odds']}</div>", unsafe_allow_html=True)
        pc="#34d399" if m["prob"]>=70 else "#f59e0b" if m["prob"]>=60 else "#ef4444"
        cols[6].markdown(f"<div style='font-size:1rem;font-weight:800;color:{pc};'>{m['prob']}%</div>", unsafe_allow_html=True)
        cols[7].markdown(f"<div style='font-size:1rem;font-weight:800;color:{c};'>+{ev}%</div>", unsafe_allow_html=True)
        bkc="#f59e0b" if m["bk"]=="Betano" else "#ec4899"
        cols[8].markdown(f"<div style='font-size:0.85rem;font-weight:600;color:{bkc};'>{m['bk']}</div>", unsafe_allow_html=True)
        if i<len(matches)-1: st.markdown('<hr style="border-top:1px solid rgba(255,255,255,0.04);margin:0.3rem 0;">', unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown(f"<div class='footer-note'>⚠️ <strong>Disclaimer:</strong> Pariurile sportive implică riscuri financiare. EV pozitiv NU garantează profit pe termen scurt. Joacă responsabil.<br><br><strong>Sursă:</strong> API-Football PRO · Betano · Cote {MIN_ODDS}–{MAX_ODDS} · EV > +{MIN_EV}%</div>", unsafe_allow_html=True)
