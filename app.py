"""
GG Bet Analyzer – Analiză statistică pentru piața „Ambele echipe marchează"
Surse date: TheSportsDB (gratuit, nelimitat)
Features v4:
  - GG% Acasă/Deplasare split contextual
  - Over 2.5 Goals (3+ goluri/meci) — NOU
  - COMBO Signal (GG + Over 2.5) — NOU
  - H2H (față în față) cu ponderare în scorul final
  - Trend ↗️↘️→ ultimele 3 vs ultimele 10 meciuri
  - Warning date insuficiente
  - Medie goluri/meci
  - Niveluri Gold / Silver / Bronze
"""

import streamlit as st
import requests
from datetime import date, datetime, timezone, timedelta

# ─────────────────────────────────────────────
# CONFIGURARE PAGINĂ
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="GG & Over 2.5 Analyzer",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html,body,[class*="css"]{ font-family:'Inter',sans-serif; }
.stApp{ background:linear-gradient(135deg,#0a0e1a 0%,#0f1629 50%,#0a1628 100%); color:#e2e8f0; }

.main-header{ text-align:center; padding:2rem 0 1.5rem 0; }
.main-header h1{
    font-size:2.8rem; font-weight:800;
    background:linear-gradient(90deg,#38bdf8,#818cf8,#f472b6);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
}
.main-header p{ color:#94a3b8; font-size:1.05rem; }

.metric-card{ background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
    border-radius:16px; padding:1.4rem 1.6rem; text-align:center; }
.metric-card .value{ font-size:2.2rem; font-weight:800; }
.metric-card .label{ font-size:0.82rem; color:#94a3b8; margin-top:0.3rem;
    text-transform:uppercase; letter-spacing:0.06em; }

.divider{ border:none; border-top:1px solid rgba(255,255,255,0.07); margin:1.5rem 0; }
.prob-bar-container{ width:100%; background:rgba(255,255,255,0.07); border-radius:999px; height:6px; margin-top:4px; }
.prob-bar{ height:6px; border-radius:999px; }

.badge-gold{ background:linear-gradient(90deg,#f59e0b,#ef4444); color:white; font-size:0.65rem;
    font-weight:700; padding:2px 8px; border-radius:999px; text-transform:uppercase; display:inline-block; margin-left:4px; }
.badge-silver{ background:linear-gradient(90deg,#94a3b8,#64748b); color:white; font-size:0.65rem;
    font-weight:700; padding:2px 8px; border-radius:999px; text-transform:uppercase; display:inline-block; margin-left:4px; }
.badge-bronze{ background:linear-gradient(90deg,#b45309,#92400e); color:white; font-size:0.65rem;
    font-weight:700; padding:2px 8px; border-radius:999px; text-transform:uppercase; display:inline-block; margin-left:4px; }
.badge-combo{ background:linear-gradient(90deg,#ec4899,#8b5cf6); color:white; font-size:0.65rem;
    font-weight:700; padding:2px 8px; border-radius:999px; text-transform:uppercase; display:inline-block; margin-left:4px; }

.stat-mini{ background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06);
    border-radius:8px; padding:4px 10px; font-size:0.72rem; color:#64748b; display:inline-block; margin:2px 3px 2px 0; }
.warn-tag{ background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.3);
    color:#fcd34d; font-size:0.68rem; font-weight:600; padding:2px 7px; border-radius:6px;
    display:inline-block; margin:2px 3px; }
.h2h-tag{ background:rgba(52,211,153,0.1); border:1px solid rgba(52,211,153,0.25);
    color:#34d399; font-size:0.72rem; font-weight:600; padding:3px 9px; border-radius:8px;
    display:inline-block; margin:2px 3px; }
.combo-tag{ background:rgba(236,72,153,0.12); border:1px solid rgba(236,72,153,0.3);
    color:#f472b6; font-size:0.72rem; font-weight:700; padding:3px 9px; border-radius:8px;
    display:inline-block; margin:2px 3px; }

.footer-note{ background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.2);
    border-radius:12px; padding:1rem 1.4rem; margin-top:2rem;
    font-size:0.82rem; color:#fca5a5; line-height:1.6; }
#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONSTANTE
# ─────────────────────────────────────────────
SPORTSDB_BASE  = "https://www.thesportsdb.com/api/v1/json/3"
THRESHOLD_GG   = 75.0
THRESHOLD_O25  = 70.0
NUM_MATCHES    = 15
MAX_MATCHES    = 50
MIN_CTX        = 3      # minim meciuri context pentru a fi considerat valid
RO_TZ          = timezone(timedelta(hours=3))

EXCLUDE_WORDS = ["Women"," W ","Youth","U20","U21","U23","Reserve","Friendly","Beach","Futsal","Indoor"]

# ─────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────
def sportsdb_get(endpoint):
    try:
        r = requests.get(f"{SPORTSDB_BASE}{endpoint}", timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# ─────────────────────────────────────────────
# FETCH DATE
# ─────────────────────────────────────────────
def fetch_todays_fixtures():
    today = date.today().strftime("%Y-%m-%d")
    data  = sportsdb_get(f"/eventsday.php?d={today}&s=Soccer")
    if not data or not data.get("events"):
        return []
    fixtures = []
    for ev in data["events"]:
        if ev.get("intHomeScore") not in (None,""):
            continue
        league_name = ev.get("strLeague","") or ""
        if any(w in league_name for w in EXCLUDE_WORDS):
            continue
        home_id = ev.get("idHomeTeam")
        away_id = ev.get("idAwayTeam")
        if not home_id or not away_id:
            continue
        time_raw = ev.get("strTime") or ""
        date_raw = ev.get("dateEvent") or today
        time_str = "N/A"
        if time_raw:
            try:
                dt = datetime.strptime(f"{date_raw} {time_raw[:8]}","%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                time_str = dt.astimezone(RO_TZ).strftime("%H:%M")
            except Exception:
                time_str = time_raw[:5] if len(time_raw)>=5 else "N/A"
        fixtures.append({
            "fixture_id":   ev.get("idEvent",""),
            "home_team":    ev.get("strHomeTeam","N/A"),
            "away_team":    ev.get("strAwayTeam","N/A"),
            "home_team_id": home_id,
            "away_team_id": away_id,
            "league":       league_name,
            "country":      ev.get("strCountry",""),
            "time":         time_str,
            "timestamp":    f"{date_raw}T{time_raw}" if time_raw else date_raw,
        })
    return sorted(fixtures, key=lambda x: x["timestamp"])[:MAX_MATCHES]


def fetch_team_last_matches(team_id):
    data = sportsdb_get(f"/eventslast.php?id={team_id}")
    if not data or not data.get("results"):
        return []
    return data["results"][:NUM_MATCHES]


def fetch_h2h(home_id, away_id):
    """Preia ultimele meciuri directe (H2H) între cele 2 echipe."""
    data = sportsdb_get(f"/lookupeventh2h.php?id1={home_id}&id2={away_id}")
    if not data or not data.get("event"):
        return []
    return data["event"][:10]


# ─────────────────────────────────────────────
# CALCUL STATISTICI (GG + OVER 2.5)
# ─────────────────────────────────────────────
def calc_stats(events, team_id):
    home_gg, home_total = 0, 0
    away_gg, away_total = 0, 0
    all_gg,  all_total  = 0, 0
    total_goals = 0
    form_5_gg = []
    recent_3_gg, recent_3_total = 0, 0

    # Over 2.5 counters
    home_o25, away_o25 = 0, 0
    all_o25 = 0
    form_5_o25 = []
    recent_3_o25 = 0

    for idx, ev in enumerate(events):
        h = ev.get("intHomeScore")
        a = ev.get("intAwayScore")
        if h in (None,"") or a in (None,""):
            continue
        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            continue

        gg = h > 0 and a > 0
        over25 = (h + a) >= 3
        all_total  += 1
        total_goals += h + a
        if gg:
            all_gg += 1
        if over25:
            all_o25 += 1

        if idx < 3:
            recent_3_total += 1
            if gg:
                recent_3_gg += 1
            if over25:
                recent_3_o25 += 1

        if len(form_5_gg) < 5:
            form_5_gg.append(gg)
        if len(form_5_o25) < 5:
            form_5_o25.append(over25)

        is_home = str(ev.get("idHomeTeam","")) == str(team_id)
        if is_home:
            home_total += 1
            if gg: home_gg += 1
            if over25: home_o25 += 1
        else:
            away_total += 1
            if gg: away_gg += 1
            if over25: away_o25 += 1

    gg_all  = round((all_gg  / all_total)  * 100, 1) if all_total  else 0.0
    gg_home = round((home_gg / home_total) * 100, 1) if home_total else 0.0
    gg_away = round((away_gg / away_total) * 100, 1) if away_total else 0.0
    r3_gg   = round((recent_3_gg / recent_3_total) * 100, 1) if recent_3_total else 0.0

    o25_all  = round((all_o25  / all_total)  * 100, 1) if all_total  else 0.0
    o25_home = round((home_o25 / home_total) * 100, 1) if home_total else 0.0
    o25_away = round((away_o25 / away_total) * 100, 1) if away_total else 0.0
    r3_o25   = round((recent_3_o25 / recent_3_total) * 100, 1) if recent_3_total else 0.0

    # Trend GG ↗️↘️→
    diff_gg = r3_gg - gg_all
    if diff_gg >= 15:
        trend_gg, trend_gg_color = "↗️ În creștere", "#34d399"
    elif diff_gg <= -15:
        trend_gg, trend_gg_color = "↘️ În scădere", "#f87171"
    else:
        trend_gg, trend_gg_color = "→ Stabil", "#94a3b8"

    # Trend Over 2.5 ↗️↘️→
    diff_o25 = r3_o25 - o25_all
    if diff_o25 >= 15:
        trend_o25, trend_o25_color = "↗️ În creștere", "#34d399"
    elif diff_o25 <= -15:
        trend_o25, trend_o25_color = "↘️ În scădere", "#f87171"
    else:
        trend_o25, trend_o25_color = "→ Stabil", "#94a3b8"

    return {
        "gg_all":    gg_all,
        "gg_home":   gg_home,
        "gg_away":   gg_away,
        "avg_goals": round(total_goals / all_total, 2) if all_total else 0.0,
        "total_m":   all_total,
        "home_m":    home_total,
        "away_m":    away_total,
        "form_5":    form_5_gg,
        "trend":     trend_gg,
        "trend_color": trend_gg_color,
        "recent_3":  r3_gg,
        # Over 2.5 stats
        "o25_all":   o25_all,
        "o25_home":  o25_home,
        "o25_away":  o25_away,
        "form_5_o25": form_5_o25,
        "trend_o25":  trend_o25,
        "trend_o25_color": trend_o25_color,
        "recent_3_o25": r3_o25,
    }


def calc_h2h_stats(events):
    """Calculează GG% și Over 2.5% din meciurile H2H."""
    gg, o25, total = 0, 0, 0
    for ev in events:
        h = ev.get("intHomeScore")
        a = ev.get("intAwayScore")
        if h in (None,"") or a in (None,""):
            continue
        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            continue
        total += 1
        if h > 0 and a > 0:
            gg += 1
        if (h + a) >= 3:
            o25 += 1
    gg_pct  = round((gg  / total) * 100, 1) if total else None
    o25_pct = round((o25 / total) * 100, 1) if total else None
    return gg_pct, o25_pct, total


def confidence_level(pct):
    if pct >= 85:
        return "gold",   "🥇 GOLD",   "#f59e0b"
    elif pct >= 75:
        return "silver", "🥈 SILVER", "#94a3b8"
    elif pct >= 65:
        return "bronze", "🥉 BRONZE", "#b45309"
    return "none", "", "#64748b"


def confidence_level_o25(pct):
    if pct >= 80:
        return "gold",   "🥇 GOLD",   "#f59e0b"
    elif pct >= 70:
        return "silver", "🥈 SILVER", "#94a3b8"
    elif pct >= 60:
        return "bronze", "🥉 BRONZE", "#b45309"
    return "none", "", "#64748b"


def analyze_match(match):
    home_events = fetch_team_last_matches(match["home_team_id"])
    away_events = fetch_team_last_matches(match["away_team_id"])
    h2h_events  = fetch_h2h(match["home_team_id"], match["away_team_id"])

    home_stats = calc_stats(home_events, match["home_team_id"])
    away_stats = calc_stats(away_events, match["away_team_id"])
    h2h_gg, h2h_o25, h2h_count = calc_h2h_stats(h2h_events)

    # GG% contextual: acasă pt gazdă, deplasare pt oaspete
    home_ctx_valid = home_stats["home_m"] >= MIN_CTX
    away_ctx_valid = away_stats["away_m"] >= MIN_CTX
    gg_home_ctx = home_stats["gg_home"] if home_ctx_valid else home_stats["gg_all"]
    gg_away_ctx = away_stats["gg_away"] if away_ctx_valid else away_stats["gg_all"]

    # Over 2.5 contextual
    o25_home_ctx = home_stats["o25_home"] if home_ctx_valid else home_stats["o25_all"]
    o25_away_ctx = away_stats["o25_away"] if away_ctx_valid else away_stats["o25_all"]

    # GG Combined
    if h2h_gg is not None and h2h_count >= 3:
        combined_gg = round(gg_home_ctx * 0.4 + gg_away_ctx * 0.4 + h2h_gg * 0.2, 1)
    else:
        combined_gg = round((gg_home_ctx + gg_away_ctx) / 2, 1)

    # Over 2.5 Combined
    if h2h_o25 is not None and h2h_count >= 3:
        combined_o25 = round(o25_home_ctx * 0.4 + o25_away_ctx * 0.4 + h2h_o25 * 0.2, 1)
    else:
        combined_o25 = round((o25_home_ctx + o25_away_ctx) / 2, 1)

    # Dacă date total insuficiente → penalizare nivel
    data_warning = (home_stats["total_m"] < 5) or (away_stats["total_m"] < 5)
    if data_warning:
        combined_gg  = max(0.0, round(combined_gg  * 0.9, 1))
        combined_o25 = max(0.0, round(combined_o25 * 0.9, 1))

    level_gg, label_gg, color_gg = confidence_level(combined_gg)
    level_o25, label_o25, color_o25 = confidence_level_o25(combined_o25)

    # Dacă date insuficiente → max SILVER (nu GOLD)
    if data_warning and level_gg == "gold":
        level_gg = "silver"
        label_gg = "🥈 SILVER"
        color_gg = "#94a3b8"
    if data_warning and level_o25 == "gold":
        level_o25 = "silver"
        label_o25 = "🥈 SILVER"
        color_o25 = "#94a3b8"

    # COMBO: GG >= 75% AND Over 2.5 >= 70%
    is_combo = combined_gg >= THRESHOLD_GG and combined_o25 >= THRESHOLD_O25

    return {
        **match,
        "gg_home_ctx":     gg_home_ctx,
        "gg_away_ctx":     gg_away_ctx,
        "combined":        combined_gg,
        "conf_level":      level_gg,
        "conf_label":      label_gg,
        "conf_color":      color_gg,
        "is_recommended":  combined_gg >= THRESHOLD_GG,
        "home_ctx_valid":  home_ctx_valid,
        "away_ctx_valid":  away_ctx_valid,
        "data_warning":    data_warning,
        "h2h_gg":          h2h_gg,
        "h2h_o25":         h2h_o25,
        "h2h_count":       h2h_count,
        "home_stats":      home_stats,
        "away_stats":      away_stats,
        "home_injured":    [],
        "away_injured":    [],
        # Over 2.5
        "o25_home_ctx":    o25_home_ctx,
        "o25_away_ctx":    o25_away_ctx,
        "combined_o25":    combined_o25,
        "conf_level_o25":  level_o25,
        "conf_label_o25":  label_o25,
        "conf_color_o25":  color_o25,
        "is_recommended_o25": combined_o25 >= THRESHOLD_O25,
        # COMBO
        "is_combo":        is_combo,
    }

# ─────────────────────────────────────────────
# DATE DEMO
# ─────────────────────────────────────────────
def demo_data():
    def mk(fid, ht, at, lg, ti, ghc, gac, h2h, h2h_c, hi, ai, dw=False,
           o25h=70.0, o25a=65.0, h2h_o25=60.0):
        comb = round(ghc*0.4 + gac*0.4 + h2h*0.2, 1) if h2h_c>=3 else round((ghc+gac)/2,1)
        comb_o25 = round(o25h*0.4 + o25a*0.4 + h2h_o25*0.2, 1) if h2h_c>=3 else round((o25h+o25a)/2,1)
        if dw:
            comb = round(comb*0.9, 1)
            comb_o25 = round(comb_o25*0.9, 1)
        lvl,lbl,col = confidence_level(comb)
        lvl_o,lbl_o,col_o = confidence_level_o25(comb_o25)
        is_combo = comb >= THRESHOLD_GG and comb_o25 >= THRESHOLD_O25
        hs = {"gg_all":ghc,"gg_home":ghc,"gg_away":ghc,"avg_goals":2.8,
              "total_m":10,"home_m":5,"away_m":5,
              "form_5":[True,True,True,False,True],"trend":"↗️ În creștere","trend_color":"#34d399","recent_3":90.0,
              "o25_all":o25h,"o25_home":o25h,"o25_away":o25h,
              "form_5_o25":[True,True,False,True,True],"trend_o25":"→ Stabil","trend_o25_color":"#94a3b8","recent_3_o25":o25h}
        as_ = {"gg_all":gac,"gg_home":gac,"gg_away":gac,"avg_goals":2.4,
               "total_m":10,"home_m":5,"away_m":5,
               "form_5":[True,False,True,True,True],"trend":"→ Stabil","trend_color":"#94a3b8","recent_3":gac,
               "o25_all":o25a,"o25_home":o25a,"o25_away":o25a,
               "form_5_o25":[True,False,True,False,True],"trend_o25":"→ Stabil","trend_o25_color":"#94a3b8","recent_3_o25":o25a}
        return {"fixture_id":fid,"home_team":ht,"away_team":at,"league":lg,"country":"","time":ti,
                "gg_home_ctx":ghc,"gg_away_ctx":gac,"combined":comb,
                "conf_level":lvl,"conf_label":lbl,"conf_color":col,"is_recommended":comb>=THRESHOLD_GG,
                "home_ctx_valid":True,"away_ctx_valid":True,"data_warning":dw,
                "h2h_gg":h2h if h2h_c>=3 else None,"h2h_o25":h2h_o25 if h2h_c>=3 else None,
                "h2h_count":h2h_c,
                "home_stats":hs,"away_stats":as_,"home_injured":hi,"away_injured":ai,
                "o25_home_ctx":o25h,"o25_away_ctx":o25a,"combined_o25":comb_o25,
                "conf_level_o25":lvl_o,"conf_label_o25":lbl_o,"conf_color_o25":col_o,
                "is_recommended_o25":comb_o25>=THRESHOLD_O25,
                "is_combo":is_combo}
    return [
        mk("1","Inter Milan","AC Milan","Serie A","20:45",88.0,84.0,80.0,8,[],[],
           o25h=85.0,o25a=80.0,h2h_o25=75.0),
        mk("2","Bayern München","Borussia Dortmund","Bundesliga","20:30",90.0,80.0,75.0,6,[],[],
           o25h=90.0,o25a=75.0,h2h_o25=80.0),
        mk("3","Manchester City","Arsenal","Premier League","18:30",82.0,76.0,70.0,5,[],[],
           o25h=78.0,o25a=72.0,h2h_o25=65.0),
        mk("4","PSG","Lyon","Ligue 1","19:00",78.0,72.0,60.0,4,[],[],
           o25h=70.0,o25a=68.0,h2h_o25=60.0),
        mk("5","Real Madrid","Atletico Madrid","La Liga","21:00",70.0,60.0,50.0,10,[],[],
           o25h=55.0,o25a=50.0,h2h_o25=45.0),
        mk("6","Feyenoord","Ajax","Eredivisie","17:45",80.0,90.0,85.0,7,[],[],
           o25h=82.0,o25a=88.0,h2h_o25=80.0),
    ]

# ─────────────────────────────────────────────
# HELPERS UI
# ─────────────────────────────────────────────
def prob_gradient(val):
    if val >= 85: return "linear-gradient(90deg,#f59e0b,#ef4444)"
    elif val >= 75: return "linear-gradient(90deg,#38bdf8,#818cf8)"
    elif val >= 65: return "linear-gradient(90deg,#b45309,#92400e)"
    return "linear-gradient(90deg,#64748b,#94a3b8)"

def val_color(val):
    if val >= 85: return "#f59e0b"
    elif val >= 75: return "#38bdf8"
    elif val >= 65: return "#cd7c2f"
    return "#94a3b8"

def form_html(form_list, label="Form"):
    if not form_list: return ""
    dots = ""
    for v in form_list:
        c = "#34d399" if v else "#f87171"
        t = "✓" if v else "✗"
        dots += f"<span title='{t}' style='display:inline-block;width:10px;height:10px;border-radius:50%;background:{c};margin:0 2px;'></span>"
    return f"<span style='font-size:0.7rem;color:#64748b;margin-right:4px;'>{label}:</span>{dots}"

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
months_ro = {
    "January":"Ianuarie","February":"Februarie","March":"Martie","April":"Aprilie",
    "May":"Mai","June":"Iunie","July":"Iulie","August":"August","September":"Septembrie",
    "October":"Octombrie","November":"Noiembrie","December":"Decembrie",
}
today_str = datetime.now(RO_TZ).strftime("%d %B %Y")
for en,ro in months_ro.items():
    today_str = today_str.replace(en, ro)

st.markdown(f"""
<div class="main-header">
    <h1>⚽ GG & Over 2.5 Analyzer</h1>
    <p>Analiză statistică · <strong>GG</strong> + <strong>Over 2.5</strong> + <strong>🔥 COMBO</strong> · {today_str}</p>
</div>""", unsafe_allow_html=True)
st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# BUTON REFRESH
# ─────────────────────────────────────────────
_, col_btn, _ = st.columns([3, 2, 3])
with col_btn:
    if st.button("🔄  Reîmprospătează Datele", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
st.markdown(
    "<div style='text-align:center;font-size:0.72rem;color:#475569;margin-top:4px;'>"
    "Date actualizate automat · TheSportsDB (gratuit, nelimitat)"
    "</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ÎNCĂRCARE DATE (cache 12h)
# ─────────────────────────────────────────────
@st.cache_data(ttl=43200, show_spinner=False)
def load_all_data():
    fixtures = fetch_todays_fixtures()
    if not fixtures:
        return demo_data(), True
    analyzed = []
    for m in fixtures:
        if not m.get("home_team_id") or not m.get("away_team_id"):
            continue
        analyzed.append(analyze_match(m))
    if not analyzed:
        return demo_data(), True
    return analyzed, False

with st.spinner("⏳ Se preiau meciurile, statistici GG, Over 2.5, H2H și trend..."):
    matches, is_demo = load_all_data()

if is_demo:
    st.info("ℹ️ **Mod demonstrativ** — Nu există meciuri programate astăzi. Datele afișate sunt exemple realiste.")

# ─────────────────────────────────────────────
# SUMAR
# ─────────────────────────────────────────────
total      = len(matches)
gold_gg    = sum(1 for m in matches if m["conf_level"]=="gold")
silver_gg  = sum(1 for m in matches if m["conf_level"]=="silver")
combo_cnt  = sum(1 for m in matches if m.get("is_combo"))
gold_o25   = sum(1 for m in matches if m.get("conf_level_o25")=="gold")

st.markdown('<hr class="divider">', unsafe_allow_html=True)
c1,c2,c3,c4,c5 = st.columns(5)
for col,val,label,color in [
    (c1, str(total),          "Meciuri analizate",  "#38bdf8"),
    (c2, f"🥇 {gold_gg}",    "GG Gold (≥85%)",     "#f59e0b"),
    (c3, f"⚽ {gold_o25}",    "O2.5 Gold (≥80%)",   "#ec4899"),
    (c4, f"🔥 {combo_cnt}",   "COMBO GG+O2.5",      "#8b5cf6"),
    (c5, f"🥈 {silver_gg}",   "GG Silver (75-85%)", "#94a3b8"),
]:
    col.markdown(
        f"<div class='metric-card'><div class='value' style='color:{color};'>{val}</div>"
        f"<div class='label'>{label}</div></div>", unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# FILTRE
# ─────────────────────────────────────────────
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("<div style='font-size:1rem;font-weight:700;color:#94a3b8;margin-bottom:0.8rem;'>🔍 Filtrare meciuri</div>",
            unsafe_allow_html=True)

all_countries = sorted(set(m["country"] for m in matches if m.get("country")))
all_leagues   = sorted(set(m["league"]  for m in matches if m.get("league")))

fcol1, fcol2, fcol3, fcol4 = st.columns([2, 2, 1, 1])

with fcol1:
    sel_countries = st.multiselect(
        "🌍 Filtrează după țară",
        options=all_countries,
        default=[],
        placeholder="Toate țările..."
    )
with fcol2:
    sel_leagues = st.multiselect(
        "🏆 Filtrează după ligă",
        options=all_leagues,
        default=[],
        placeholder="Toate ligile..."
    )
with fcol3:
    min_prob = st.slider("📈 Prob. minimă", 0, 100, 0, 5, format="%d%%")
with fcol4:
    market_filter = st.selectbox(
        "📊 Piață",
        options=["GG + Over 2.5", "Doar GG", "Doar Over 2.5", "🔥 COMBO"],
        index=0
    )

# Aplicăm filtrele
filtered_matches = [
    m for m in matches
    if (not sel_countries or m.get("country","") in sel_countries)
    and (not sel_leagues   or m.get("league","")   in sel_leagues)
    and (
        (market_filter == "Doar GG" and m["combined"] >= min_prob)
        or (market_filter == "Doar Over 2.5" and m.get("combined_o25",0) >= min_prob)
        or (market_filter == "🔥 COMBO" and m.get("is_combo", False))
        or (market_filter == "GG + Over 2.5" and max(m["combined"], m.get("combined_o25",0)) >= min_prob)
    )
]

if not filtered_matches:
    st.warning("⚠️ Niciun meci nu corespunde filtrelor selectate. Resetează filtrele.")
    filtered_matches = matches

# ─────────────────────────────────────────────
# SORTARE
# ─────────────────────────────────────────────
if market_filter == "Doar Over 2.5":
    sorted_matches = sorted(filtered_matches, key=lambda x: (
        0 if x.get("conf_level_o25")=="gold" else 1 if x.get("conf_level_o25")=="silver"
        else 2 if x.get("conf_level_o25")=="bronze" else 3, -x.get("combined_o25",0)))
elif market_filter == "🔥 COMBO":
    sorted_matches = sorted(filtered_matches, key=lambda x: (
        0 if x.get("is_combo") else 1,
        -(x["combined"] + x.get("combined_o25",0))))
else:
    sorted_matches = sorted(filtered_matches, key=lambda x: (
        0 if x["conf_level"]=="gold" else 1 if x["conf_level"]=="silver"
        else 2 if x["conf_level"]=="bronze" else 3, -x["combined"]))

# ─────────────────────────────────────────────
# TABEL
# ─────────────────────────────────────────────
market_label = {"GG + Over 2.5":"GG + Over 2.5","Doar GG":"GG","Doar Over 2.5":"Over 2.5","🔥 COMBO":"COMBO"}.get(market_filter, "GG")
st.markdown(f"<div style='font-size:1.15rem;font-weight:700;color:#e2e8f0;margin:1rem 0;'>📊 {market_label} — Analiza Meciurilor "
            f"<span style='font-size:0.8rem;color:#64748b;font-weight:400;'>({len(sorted_matches)} din {len(matches)} meciuri)</span></div>",
            unsafe_allow_html=True)

# Header tabel
h_cols = st.columns([0.6, 1.7, 1.7, 1.5, 1.2, 1.2, 1.0, 1.0])
headers = ["🕐","🏟️ Gazdă","✈️ Oaspete","🏆 Liga","🏠 GG%","✈️ GG%","⚽ O2.5","📈 Scor"]
for col,h in zip(h_cols, headers):
    col.markdown(f"<span style='font-size:0.7rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;'>{h}</span>", unsafe_allow_html=True)
st.markdown('<hr style="border-top:1px solid rgba(255,255,255,0.06);margin:0.3rem 0 0.6rem;">', unsafe_allow_html=True)

for i, m in enumerate(sorted_matches):
    lvl   = m["conf_level"]
    comb  = m["combined"]
    comb_o = m.get("combined_o25", 0)
    hs    = m["home_stats"]
    as_   = m["away_stats"]
    dw    = m.get("data_warning", False)
    combo = m.get("is_combo", False)

    # Border color based on best level
    if combo:
        border = "border-left:3px solid #ec4899;"
    elif lvl == "gold":
        border = "border-left:3px solid #f59e0b;"
    elif lvl == "silver":
        border = "border-left:3px solid #94a3b8;"
    elif lvl == "bronze":
        border = "border-left:3px solid #b45309;"
    else:
        border = "border-left:3px solid transparent;"

    badge_html = f'<span class="badge-{lvl}">{m["conf_label"]}</span>' if lvl!="none" else ""
    combo_html = '<span class="badge-combo">🔥 COMBO</span>' if combo else ""
    warn_html  = '<span class="warn-tag">⚠️ Date limitate</span>' if dw else ""

    cols = st.columns([0.6, 1.7, 1.7, 1.5, 1.2, 1.2, 1.0, 1.0])

    # Ora
    cols[0].markdown(
        f"<div style='{border}padding-left:8px;font-weight:600;color:#cbd5e1;'>{m['time']}</div>",
        unsafe_allow_html=True)

    # Gazdă
    h_form = form_html(hs.get("form_5",[]), "GG")
    trend_h = hs["trend"]
    tc_h    = hs["trend_color"]
    cols[1].markdown(
        f"<div style='font-weight:700;color:#f1f5f9;'>{m['home_team']} {badge_html} {combo_html} {warn_html}</div>"
        f"<div style='margin-top:3px;'>{h_form}"
        f"<span class='stat-mini' style='color:{tc_h};'>{trend_h}</span>"
        f"<span class='stat-mini'>⚽ {hs['avg_goals']}/meci</span></div>",
        unsafe_allow_html=True)

    # Oaspete
    a_form  = form_html(as_.get("form_5",[]), "GG")
    trend_a = as_["trend"]
    tc_a    = as_["trend_color"]
    cols[2].markdown(
        f"<div style='font-weight:500;color:#e2e8f0;'>{m['away_team']}</div>"
        f"<div style='margin-top:3px;'>{a_form}"
        f"<span class='stat-mini' style='color:{tc_a};'>{trend_a}</span>"
        f"<span class='stat-mini'>⚽ {as_['avg_goals']}/meci</span></div>",
        unsafe_allow_html=True)

    # Liga + H2H
    h2h_html = ""
    if m.get("h2h_gg") is not None:
        h2h_html = f"<br><span class='h2h-tag'>🤝 H2H GG: {m['h2h_gg']}%</span>"
    if m.get("h2h_o25") is not None:
        h2h_html += f" <span class='h2h-tag'>⚽ H2H O2.5: {m['h2h_o25']}%</span>"
    cols[3].markdown(
        f"<div style='font-size:0.8rem;color:#94a3b8;'>{m['league']}</div>"
        f"<div style='font-size:0.7rem;color:#475569;'>{m['country']}</div>"
        f"{h2h_html}",
        unsafe_allow_html=True)

    # GG% Acasă
    gg_h = m["gg_home_ctx"]
    ctx_warn_h = "" if m.get("home_ctx_valid") else " ⚠️"
    cols[4].markdown(
        f"<div style='font-size:1.05rem;font-weight:700;color:{val_color(gg_h)};'>{gg_h}%{ctx_warn_h}</div>"
        f"<div class='prob-bar-container'><div class='prob-bar' style='width:{gg_h}%;background:{prob_gradient(gg_h)};'></div></div>"
        f"<div style='font-size:0.68rem;color:#475569;margin-top:2px;'>({hs['home_m']} acasă)</div>",
        unsafe_allow_html=True)

    # GG% Deplasare
    gg_a = m["gg_away_ctx"]
    ctx_warn_a = "" if m.get("away_ctx_valid") else " ⚠️"
    cols[5].markdown(
        f"<div style='font-size:1.05rem;font-weight:700;color:{val_color(gg_a)};'>{gg_a}%{ctx_warn_a}</div>"
        f"<div class='prob-bar-container'><div class='prob-bar' style='width:{gg_a}%;background:{prob_gradient(gg_a)};'></div></div>"
        f"<div style='font-size:0.68rem;color:#475569;margin-top:2px;'>({as_['away_m']} depl.)</div>",
        unsafe_allow_html=True)

    # Over 2.5% Combined
    o25_col = val_color(comb_o)
    cols[6].markdown(
        f"<div style='text-align:center;'>"
        f"<div style='font-size:1.05rem;font-weight:700;color:{o25_col};'>{comb_o}%</div>"
        f"<div class='prob-bar-container'><div class='prob-bar' style='width:{comb_o}%;background:{prob_gradient(comb_o)};'></div></div>"
        f"<div style='font-size:0.68rem;color:#475569;margin-top:2px;'>Over 2.5</div></div>",
        unsafe_allow_html=True)

    # Prob GG combinat
    prob_bg = (
        "rgba(236,72,153,0.15)" if combo else
        "rgba(245,158,11,0.12)" if lvl=="gold" else
        "rgba(56,189,248,0.10)" if lvl=="silver" else
        "rgba(180,83,9,0.10)"   if lvl=="bronze" else
        "rgba(255,255,255,0.04)"
    )
    cols[7].markdown(
        f"<div style='text-align:center;background:{prob_bg};border-radius:10px;padding:6px 4px;'>"
        f"<span style='font-size:1.15rem;font-weight:800;color:{m['conf_color']};'>{comb}%</span>"
        f"<div style='font-size:0.6rem;color:#64748b;'>GG</div></div>",
        unsafe_allow_html=True)

    # Detalii expandabile
    with st.expander(f"📊 Detalii: {m['home_team']} vs {m['away_team']}"):
        dc1, dc2, dc3 = st.columns(3)
        with dc1:
            vc_h = "#34d399" if m.get("home_ctx_valid") else "#fcd34d"
            o25_form_h = form_html(hs.get("form_5_o25",[]), "O2.5")
            st.markdown(
                f"<div style='font-weight:700;color:#38bdf8;margin-bottom:8px;'>🏠 {m['home_team']}</div>"
                f"<div style='font-size:0.82rem;color:#94a3b8;line-height:2;'>"
                f"GG% Total: <strong style='color:#e2e8f0;'>{hs['gg_all']}%</strong><br>"
                f"GG% Acasă: <strong style='color:{vc_h};'>{hs['gg_home']}%</strong> ({hs['home_m']} meci)<br>"
                f"O2.5% Total: <strong style='color:#ec4899;'>{hs['o25_all']}%</strong><br>"
                f"O2.5% Acasă: <strong style='color:#ec4899;'>{hs['o25_home']}%</strong><br>"
                f"Medie goluri: <strong style='color:#f59e0b;'>{hs['avg_goals']}/meci</strong><br>"
                f"Trend GG: <strong style='color:{hs['trend_color']};'>{hs['trend']}</strong><br>"
                f"Trend O2.5: <strong style='color:{hs['trend_o25_color']};'>{hs['trend_o25']}</strong>"
                f"</div>"
                f"<div style='margin-top:4px;'>{o25_form_h}</div>",
                unsafe_allow_html=True)
        with dc2:
            vc_a = "#34d399" if m.get("away_ctx_valid") else "#fcd34d"
            o25_form_a = form_html(as_.get("form_5_o25",[]), "O2.5")
            st.markdown(
                f"<div style='font-weight:700;color:#818cf8;margin-bottom:8px;'>✈️ {m['away_team']}</div>"
                f"<div style='font-size:0.82rem;color:#94a3b8;line-height:2;'>"
                f"GG% Total: <strong style='color:#e2e8f0;'>{as_['gg_all']}%</strong><br>"
                f"GG% Depl.: <strong style='color:{vc_a};'>{as_['gg_away']}%</strong> ({as_['away_m']} meci)<br>"
                f"O2.5% Total: <strong style='color:#ec4899;'>{as_['o25_all']}%</strong><br>"
                f"O2.5% Depl.: <strong style='color:#ec4899;'>{as_['o25_away']}%</strong><br>"
                f"Medie goluri: <strong style='color:#f59e0b;'>{as_['avg_goals']}/meci</strong><br>"
                f"Trend GG: <strong style='color:{as_['trend_color']};'>{as_['trend']}</strong><br>"
                f"Trend O2.5: <strong style='color:{as_['trend_o25_color']};'>{as_['trend_o25']}</strong>"
                f"</div>"
                f"<div style='margin-top:4px;'>{o25_form_a}</div>",
                unsafe_allow_html=True)
        with dc3:
            if m.get("h2h_gg") is not None:
                h2h_pct = m["h2h_gg"]
                h2h_o25_pct = m.get("h2h_o25", 0)
                h2h_col = val_color(h2h_pct)
                st.markdown(
                    f"<div style='font-weight:700;color:#34d399;margin-bottom:8px;'>🤝 Față în Față (H2H)</div>"
                    f"<div style='font-size:0.82rem;color:#94a3b8;line-height:2;'>"
                    f"GG% H2H: <strong style='color:{h2h_col};font-size:1.1rem;'>{h2h_pct}%</strong><br>"
                    f"O2.5% H2H: <strong style='color:#ec4899;font-size:1.1rem;'>{h2h_o25_pct}%</strong><br>"
                    f"Meciuri analizate: <strong style='color:#e2e8f0;'>{m['h2h_count']}</strong><br>"
                    f"<span style='font-size:0.75rem;color:#475569;'>"
                    f"Ponderat 20% în scorul final</span>"
                    f"</div>", unsafe_allow_html=True)
            else:
                st.markdown(
                    f"<div style='font-weight:700;color:#475569;margin-bottom:8px;'>🤝 Față în Față (H2H)</div>"
                    f"<div style='font-size:0.8rem;color:#475569;'>"
                    f"Date H2H insuficiente<br>(sub 3 meciuri directe)</div>",
                    unsafe_allow_html=True)

    if i < len(sorted_matches)-1:
        st.markdown('<hr style="border-top:1px solid rgba(255,255,255,0.04);margin:0.5rem 0;">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# RECOMANDĂRILE ZILEI
# ─────────────────────────────────────────────
st.markdown('<hr class="divider">', unsafe_allow_html=True)

# COMBO recommendations first
combo_list = [m for m in sorted_matches if m.get("is_combo")]
if combo_list:
    st.markdown(
        "<div style='font-size:1.15rem;font-weight:700;color:#e2e8f0;margin-bottom:1rem;'>"
        "🔥 COMBO — GG + Over 2.5 "
        "<span style='font-size:0.8rem;color:#94a3b8;font-weight:400;'>"
        f"({len(combo_list)} meciuri cu ambele piețe peste prag)</span></div>",
        unsafe_allow_html=True)

    for m in combo_list:
        comb     = m["combined"]
        comb_o   = m.get("combined_o25", 0)
        home_t   = m["home_team"]
        away_t   = m["away_team"]
        league_n = m["league"]
        time_n   = m["time"]
        avg_h    = m["home_stats"]["avg_goals"]
        avg_a    = m["away_stats"]["avg_goals"]
        avg_comb_goals = round((avg_h + avg_a) / 2, 1)

        col_info, col_prob = st.columns([5, 1])
        with col_info:
            st.markdown(
                f"<div style='background:linear-gradient(135deg,rgba(236,72,153,0.08),rgba(139,92,246,0.08));"
                f"border:1px solid rgba(236,72,153,0.3);border-radius:16px;padding:1.2rem 1.5rem;'>"
                f"<div style='font-size:1.05rem;font-weight:700;color:#e2e8f0;'>"
                f"🔥 COMBO &nbsp;🏠 {home_t} <span style='color:#64748b;font-weight:400;'>vs</span> {away_t} ✈️</div>"
                f"<div style='font-size:0.8rem;color:#94a3b8;margin-top:2px;'>🏆 {league_n} &nbsp;·&nbsp; 🕐 {time_n}</div>"
                f"<div style='margin-top:0.5rem;font-size:0.82rem;color:#64748b;'>"
                f"GG: <strong style='color:#38bdf8;'>{comb}%</strong>"
                f" &nbsp;·&nbsp; Over 2.5: <strong style='color:#ec4899;'>{comb_o}%</strong>"
                f" &nbsp;·&nbsp; ⚽ Medie: <strong style='color:#f59e0b;'>{avg_comb_goals}/meci</strong></div>"
                f"</div>",
                unsafe_allow_html=True)
        with col_prob:
            st.markdown(
                f"<div style='text-align:center;background:linear-gradient(135deg,#ec4899,#8b5cf6);"
                f"border-radius:50%;width:60px;height:60px;display:flex;align-items:center;"
                f"justify-content:center;font-size:0.75rem;font-weight:800;color:white;margin:auto;'>"
                f"🔥<br>{comb}%</div>",
                unsafe_allow_html=True)

# GG recommendations
rec_list = [m for m in sorted_matches if m["conf_level"] in ("gold","silver")]
st.markdown('<hr class="divider">', unsafe_allow_html=True)

if rec_list:
    st.markdown(
        "<div style='font-size:1.15rem;font-weight:700;color:#e2e8f0;margin-bottom:1rem;'>"
        "🎯 Recomandări GG "
        "<span style='font-size:0.8rem;color:#94a3b8;font-weight:400;'>"
        "(🥇 Gold ≥85% · 🥈 Silver ≥75%)</span></div>",
        unsafe_allow_html=True)

    for m in rec_list:
        comb     = m["combined"]
        comb_o   = m.get("combined_o25", 0)
        lvl      = m["conf_level"]
        home_t   = m["home_team"]
        away_t   = m["away_team"]
        league_n = m["league"]
        time_n   = m["time"]
        gg_h     = m["gg_home_ctx"]
        gg_a     = m["gg_away_ctx"]
        avg_h    = m["home_stats"]["avg_goals"]
        avg_a    = m["away_stats"]["avg_goals"]
        avg_comb_goals = round((avg_h + avg_a) / 2, 1)
        h2h_info = ""
        if m.get("h2h_gg") is not None:
            h2h_info = f" &nbsp;·&nbsp; 🤝 H2H: <strong style='color:#34d399;'>{m['h2h_gg']}%</strong>"

        border_color = "#f59e0b" if lvl=="gold" else "#94a3b8"
        bg_l = "rgba(245,158,11,0.08),rgba(239,68,68,0.06)" if lvl=="gold" else "rgba(56,189,248,0.08),rgba(129,140,248,0.08)"
        circ_bg = "linear-gradient(135deg,#f59e0b,#ef4444)" if lvl=="gold" else "linear-gradient(135deg,#38bdf8,#818cf8)"

        col_info, col_prob = st.columns([5, 1])
        with col_info:
            st.markdown(
                f"<div style='background:linear-gradient(135deg,{bg_l});"
                f"border:1px solid {border_color}40;border-radius:16px;padding:1.2rem 1.5rem;'>"
                f"<div style='font-size:1.05rem;font-weight:700;color:#e2e8f0;'>"
                f"{m['conf_label']} &nbsp;🏠 {home_t} <span style='color:#64748b;font-weight:400;'>vs</span> {away_t} ✈️</div>"
                f"<div style='font-size:0.8rem;color:#94a3b8;margin-top:2px;'>🏆 {league_n} &nbsp;·&nbsp; 🕐 {time_n}</div>"
                f"<div style='margin-top:0.5rem;font-size:0.82rem;color:#64748b;'>"
                f"GG Acasă: <strong style='color:#38bdf8;'>{gg_h}%</strong>"
                f" &nbsp;·&nbsp; GG Depl.: <strong style='color:#818cf8;'>{gg_a}%</strong>"
                f"{h2h_info}"
                f" &nbsp;·&nbsp; O2.5: <strong style='color:#ec4899;'>{comb_o}%</strong>"
                f" &nbsp;·&nbsp; ⚽ Medie: <strong style='color:#f59e0b;'>{avg_comb_goals}/meci</strong></div>"
                f"</div>",
                unsafe_allow_html=True)
        with col_prob:
            st.markdown(
                f"<div style='text-align:center;background:{circ_bg};"
                f"border-radius:50%;width:60px;height:60px;display:flex;align-items:center;"
                f"justify-content:center;font-size:0.9rem;font-weight:800;color:white;margin:auto;'>"
                f"{comb}%</div>",
                unsafe_allow_html=True)

# Over 2.5 recommendations
rec_o25 = [m for m in sorted_matches if m.get("conf_level_o25") in ("gold","silver") and m not in rec_list]
if rec_o25:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:1.15rem;font-weight:700;color:#e2e8f0;margin-bottom:1rem;'>"
        "⚽ Recomandări Over 2.5 "
        "<span style='font-size:0.8rem;color:#94a3b8;font-weight:400;'>"
        "(🥇 Gold ≥80% · 🥈 Silver ≥70%)</span></div>",
        unsafe_allow_html=True)

    for m in rec_o25:
        comb_o   = m.get("combined_o25", 0)
        home_t   = m["home_team"]
        away_t   = m["away_team"]
        league_n = m["league"]
        time_n   = m["time"]
        avg_h    = m["home_stats"]["avg_goals"]
        avg_a    = m["away_stats"]["avg_goals"]
        avg_comb_goals = round((avg_h + avg_a) / 2, 1)

        col_info, col_prob = st.columns([5, 1])
        with col_info:
            st.markdown(
                f"<div style='background:linear-gradient(135deg,rgba(236,72,153,0.06),rgba(236,72,153,0.03));"
                f"border:1px solid rgba(236,72,153,0.2);border-radius:16px;padding:1.2rem 1.5rem;'>"
                f"<div style='font-size:1.05rem;font-weight:700;color:#e2e8f0;'>"
                f"{m.get('conf_label_o25','')} &nbsp;🏠 {home_t} <span style='color:#64748b;font-weight:400;'>vs</span> {away_t} ✈️</div>"
                f"<div style='font-size:0.8rem;color:#94a3b8;margin-top:2px;'>🏆 {league_n} &nbsp;·&nbsp; 🕐 {time_n}</div>"
                f"<div style='margin-top:0.5rem;font-size:0.82rem;color:#64748b;'>"
                f"Over 2.5: <strong style='color:#ec4899;'>{comb_o}%</strong>"
                f" &nbsp;·&nbsp; ⚽ Medie: <strong style='color:#f59e0b;'>{avg_comb_goals}/meci</strong></div>"
                f"</div>",
                unsafe_allow_html=True)
        with col_prob:
            st.markdown(
                f"<div style='text-align:center;background:linear-gradient(135deg,#ec4899,#f472b6);"
                f"border-radius:50%;width:60px;height:60px;display:flex;align-items:center;"
                f"justify-content:center;font-size:0.9rem;font-weight:800;color:white;margin:auto;'>"
                f"{comb_o}%</div>",
                unsafe_allow_html=True)

if not rec_list and not combo_list and not rec_o25:
    st.markdown(
        f"<div style='text-align:center;padding:2rem;color:#64748b;'>"
        f"<div style='font-size:2rem;'>🤔</div>"
        f"<div style='margin-top:0.5rem;'>Niciun meci nu depășește pragurile astăzi.</div></div>",
        unsafe_allow_html=True)

# ─────────────────────────────────────────────
# METODOLOGIE
# ─────────────────────────────────────────────
st.markdown('<hr class="divider">', unsafe_allow_html=True)
with st.expander("📐 Metodologie & Legendă"):
    st.markdown(f"""
**Formula de calcul (GG și Over 2.5):**

| Situație | Formula |
|---|---|
| Cu H2H (≥3 meciuri directe) | `40% × Stat_acasă + 40% × Stat_deplasare + 20% × Stat_H2H` |
| Fără H2H | `50% × Stat_acasă + 50% × Stat_deplasare` |
| Date limitate (<5 meciuri) | Probabilitate redusă cu 10% automat |

**Niveluri GG:**
| Nivel | Probabilitate | Semnificație |
|---|---|---|
| 🥇 Gold | ≥ 85% | Probabilitate ridicată |
| 🥈 Silver | 75–85% | Probabilitate bună |
| 🥉 Bronze | 65–75% | Probabilitate medie |

**Niveluri Over 2.5:**
| Nivel | Probabilitate | Semnificație |
|---|---|---|
| 🥇 Gold | ≥ 80% | Probabilitate ridicată |
| 🥈 Silver | 70–80% | Probabilitate bună |
| 🥉 Bronze | 60–70% | Probabilitate medie |

**🔥 COMBO Signal:** Apare când un meci are **GG ≥ 75% ȘI Over 2.5 ≥ 70%** — cel mai puternic semnal!

**Over 2.5:** Procentul meciurilor în care s-au marcat minim 3 goluri total (ex: 2-1, 1-2, 3-0 etc.)

**Trend:** Compară % din ultimele 3 meciuri vs media generală.
- ↗️ În creștere = ultimele 3 cu 15%+ peste medie
- ↘️ În scădere = ultimele 3 cu 15%+ sub medie

**Sursă**: [TheSportsDB](https://www.thesportsdb.com/) — gratuit, nelimitat.
""")

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown("""
<div class="footer-note">
    ⚠️ <strong>Notă importantă:</strong> Datele și procentajele afișate au caracter exclusiv
    statistic și informativ. Ele <strong>nu reprezintă o garanție de câștig</strong> și nu
    constituie sfaturi de pariuri. Parierile implică riscuri financiare. Jucați responsabil.
    Vârsta minimă legală în România: <strong>18 ani</strong>.
</div>
<div style="text-align:center;padding:1.5rem 0 0.5rem;color:#334155;font-size:0.75rem;">
    GG & Over 2.5 Analyzer v4 · Powered by TheSportsDB · Date actualizate la fiecare 12 ore
</div>
""", unsafe_allow_html=True)
