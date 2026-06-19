"""
GG Bet Analyzer – Analiză statistică pentru piața „Ambele echipe marchează"
Surse date: TheSportsDB (gratuit, nelimitat)
Features v3:
  - GG% Acasă/Deplasare split contextual
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
    page_title="GG Bet Analyzer – Ambele Echipe Marchează",
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

.stat-mini{ background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06);
    border-radius:8px; padding:4px 10px; font-size:0.72rem; color:#64748b; display:inline-block; margin:2px 3px 2px 0; }
.warn-tag{ background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.3);
    color:#fcd34d; font-size:0.68rem; font-weight:600; padding:2px 7px; border-radius:6px;
    display:inline-block; margin:2px 3px; }
.h2h-tag{ background:rgba(52,211,153,0.1); border:1px solid rgba(52,211,153,0.25);
    color:#34d399; font-size:0.72rem; font-weight:600; padding:3px 9px; border-radius:8px;
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
SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"
THRESHOLD_GG  = 75.0
NUM_MATCHES   = 15
MAX_MATCHES   = 25
MIN_CTX       = 3      # minim meciuri context pentru a fi considerat valid
RO_TZ         = timezone(timedelta(hours=3))

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
    data = sportsdb_get(f"/eventsh2h.php?idHomeTeam={home_id}&idAwayTeam={away_id}")
    if not data or not data.get("results"):
        return []
    return data["results"][:10]


def calc_stats(events, team_id):
    """Statistici complete: GG% total/acasă/deplasare, avg goals, trend, formă 5."""
    home_gg, home_total = 0, 0
    away_gg, away_total = 0, 0
    all_gg,  all_total  = 0, 0
    total_goals = 0
    form_5 = []
    recent_3_gg, recent_3_total = 0, 0

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
        all_total  += 1
        total_goals += h + a
        if gg:
            all_gg += 1

        if idx < 3:
            recent_3_total += 1
            if gg:
                recent_3_gg += 1

        if len(form_5) < 5:
            form_5.append(gg)

        is_home = str(ev.get("idHomeTeam","")) == str(team_id)
        if is_home:
            home_total += 1
            if gg: home_gg += 1
        else:
            away_total += 1
            if gg: away_gg += 1

    gg_all  = round((all_gg  / all_total)  * 100, 1) if all_total  else 0.0
    gg_home = round((home_gg / home_total) * 100, 1) if home_total else 0.0
    gg_away = round((away_gg / away_total) * 100, 1) if away_total else 0.0
    r3      = round((recent_3_gg / recent_3_total) * 100, 1) if recent_3_total else 0.0

    # Trend ↗️↘️→
    diff = r3 - gg_all
    if diff >= 15:
        trend, trend_color = "↗️ În creștere", "#34d399"
    elif diff <= -15:
        trend, trend_color = "↘️ În scădere", "#f87171"
    else:
        trend, trend_color = "→ Stabil", "#94a3b8"

    return {
        "gg_all":    gg_all,
        "gg_home":   gg_home,
        "gg_away":   gg_away,
        "avg_goals": round(total_goals / all_total, 2) if all_total else 0.0,
        "total_m":   all_total,
        "home_m":    home_total,
        "away_m":    away_total,
        "form_5":    form_5,
        "trend":     trend,
        "trend_color": trend_color,
        "recent_3":  r3,
    }


def calc_h2h_gg(events):
    """Calculează GG% din meciurile H2H."""
    gg, total = 0, 0
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
    return round((gg / total) * 100, 1) if total else None, total


def confidence_level(pct):
    if pct >= 85:
        return "gold",   "🥇 GOLD",   "#f59e0b"
    elif pct >= 75:
        return "silver", "🥈 SILVER", "#94a3b8"
    elif pct >= 65:
        return "bronze", "🥉 BRONZE", "#b45309"
    return "none", "", "#64748b"


def analyze_match(match):
    home_events = fetch_team_last_matches(match["home_team_id"])
    away_events = fetch_team_last_matches(match["away_team_id"])
    h2h_events  = fetch_h2h(match["home_team_id"], match["away_team_id"])

    home_stats = calc_stats(home_events, match["home_team_id"])
    away_stats = calc_stats(away_events, match["away_team_id"])
    h2h_gg, h2h_count = calc_h2h_gg(h2h_events)

    # GG% contextual: acasă pt gazdă, deplasare pt oaspete
    # Dacă date insuficiente → fallback la gg_all
    home_ctx_valid = home_stats["home_m"] >= MIN_CTX
    away_ctx_valid = away_stats["away_m"] >= MIN_CTX
    gg_home_ctx = home_stats["gg_home"] if home_ctx_valid else home_stats["gg_all"]
    gg_away_ctx = away_stats["gg_away"] if away_ctx_valid else away_stats["gg_all"]

    # Combinat: ponderăm H2H dacă avem date suficiente
    if h2h_gg is not None and h2h_count >= 3:
        # 40% gazdă + 40% oaspete + 20% H2H
        combined = round(gg_home_ctx * 0.4 + gg_away_ctx * 0.4 + h2h_gg * 0.2, 1)
    else:
        combined = round((gg_home_ctx + gg_away_ctx) / 2, 1)

    # Dacă date total insuficiente → penalizare nivel
    data_warning = (home_stats["total_m"] < 5) or (away_stats["total_m"] < 5)
    if data_warning:
        # Reducem probabilitatea cu 10% pentru a reflecta incertitudinea
        combined = max(0.0, round(combined * 0.9, 1))

    level, label, color = confidence_level(combined)

    # Dacă date insuficiente → max SILVER (nu GOLD)
    if data_warning and level == "gold":
        level = "silver"
        label = "🥈 SILVER"
        color = "#94a3b8"

    return {
        **match,
        "gg_home_ctx":     gg_home_ctx,
        "gg_away_ctx":     gg_away_ctx,
        "combined":        combined,
        "conf_level":      level,
        "conf_label":      label,
        "conf_color":      color,
        "is_recommended":  combined >= THRESHOLD_GG,
        "home_ctx_valid":  home_ctx_valid,
        "away_ctx_valid":  away_ctx_valid,
        "data_warning":    data_warning,
        "h2h_gg":          h2h_gg,
        "h2h_count":       h2h_count,
        "home_stats":      home_stats,
        "away_stats":      away_stats,
        "home_injured":    [],
        "away_injured":    [],
    }

# ─────────────────────────────────────────────
# DATE DEMO
# ─────────────────────────────────────────────
def demo_data():
    def mk(fid, ht, at, lg, ti, ghc, gac, h2h, h2h_c, hi, ai, dw=False):
        comb = round(ghc*0.4 + gac*0.4 + h2h*0.2, 1) if h2h_c>=3 else round((ghc+gac)/2,1)
        if dw: comb = round(comb*0.9, 1)
        lvl,lbl,col = confidence_level(comb)
        hs = {"gg_all":ghc,"gg_home":ghc,"gg_away":ghc,"avg_goals":2.8,
              "total_m":10,"home_m":5,"away_m":5,
              "form_5":[True,True,True,False,True],"trend":"↗️ În creștere","trend_color":"#34d399","recent_3":90.0}
        as_ = {"gg_all":gac,"gg_home":gac,"gg_away":gac,"avg_goals":2.4,
               "total_m":10,"home_m":5,"away_m":5,
               "form_5":[True,False,True,True,True],"trend":"→ Stabil","trend_color":"#94a3b8","recent_3":gac}
        return {"fixture_id":fid,"home_team":ht,"away_team":at,"league":lg,"country":"","time":ti,
                "gg_home_ctx":ghc,"gg_away_ctx":gac,"combined":comb,
                "conf_level":lvl,"conf_label":lbl,"conf_color":col,"is_recommended":comb>=THRESHOLD_GG,
                "home_ctx_valid":True,"away_ctx_valid":True,"data_warning":dw,
                "h2h_gg":h2h if h2h_c>=3 else None,"h2h_count":h2h_c,
                "home_stats":hs,"away_stats":as_,"home_injured":hi,"away_injured":ai}
    return [
        mk("1","Inter Milan","AC Milan","Serie A","20:45",88.0,84.0,80.0,8,
           [{"name":"Lautaro","reason":"Muscle","type":"Injured"}],[]),
        mk("2","Bayern München","Borussia Dortmund","Bundesliga","20:30",90.0,80.0,75.0,6,
           [],[{"name":"Reus","reason":"Cards","type":"Suspended"}]),
        mk("3","Manchester City","Arsenal","Premier League","18:30",82.0,76.0,70.0,5,[],[]),
        mk("4","PSG","Lyon","Ligue 1","19:00",78.0,72.0,60.0,4,[],[]),
        mk("5","Real Madrid","Atletico Madrid","La Liga","21:00",70.0,60.0,50.0,10,[],[]),
        mk("6","Feyenoord","Ajax","Eredivisie","17:45",80.0,90.0,85.0,7,[],[]),
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

def form_html(form_5):
    if not form_5: return ""
    dots = ""
    for gg in form_5:
        c = "#34d399" if gg else "#f87171"
        t = "GG ✓" if gg else "No GG ✗"
        dots += f"<span title='{t}' style='display:inline-block;width:10px;height:10px;border-radius:50%;background:{c};margin:0 2px;'></span>"
    return f"<span style='font-size:0.7rem;color:#64748b;margin-right:4px;'>Form:</span>{dots}"

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
    <h1>⚽ GG Bet Analyzer</h1>
    <p>Analiză statistică · Piața <strong>Ambele Echipe Marchează</strong> · {today_str}</p>
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

with st.spinner("⏳ Se preiau meciurile, statistici GG, H2H și trend..."):
    matches, is_demo = load_all_data()

if is_demo:
    st.info("ℹ️ **Mod demonstrativ** — Nu există meciuri programate astăzi. Datele afișate sunt exemple realiste.")

# ─────────────────────────────────────────────
# SUMAR
# ─────────────────────────────────────────────
total      = len(matches)
gold_cnt   = sum(1 for m in matches if m["conf_level"]=="gold")
silver_cnt = sum(1 for m in matches if m["conf_level"]=="silver")
bronze_cnt = sum(1 for m in matches if m["conf_level"]=="bronze")
avg_comb   = round(sum(m["combined"] for m in matches)/total,1) if total else 0.0
h2h_cnt    = sum(1 for m in matches if m.get("h2h_gg") is not None)

st.markdown('<hr class="divider">', unsafe_allow_html=True)
c1,c2,c3,c4,c5 = st.columns(5)
for col,val,label,color in [
    (c1, str(total),          "Meciuri analizate",  "#38bdf8"),
    (c2, f"🥇 {gold_cnt}",    "Gold (≥85%)",        "#f59e0b"),
    (c3, f"🥈 {silver_cnt}",  "Silver (75-85%)",    "#94a3b8"),
    (c4, f"🥉 {bronze_cnt}",  "Bronze (65-75%)",    "#b45309"),
    (c5, f"🤝 {h2h_cnt}",     "Cu date H2H",        "#34d399"),
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

# Extragem valorile unice din date
all_countries = sorted(set(m["country"] for m in matches if m.get("country")))
all_leagues   = sorted(set(m["league"]  for m in matches if m.get("league")))

fcol1, fcol2, fcol3 = st.columns([2, 2, 1])

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

# Aplicăm filtrele
filtered_matches = [
    m for m in matches
    if (not sel_countries or m.get("country","") in sel_countries)
    and (not sel_leagues   or m.get("league","")   in sel_leagues)
    and m["combined"] >= min_prob
]

if not filtered_matches:
    st.warning("⚠️ Niciun meci nu corespunde filtrelor selectate. Resetează filtrele.")
    filtered_matches = matches  # fallback la toate

# ─────────────────────────────────────────────
# TABEL
# ─────────────────────────────────────────────
sorted_matches = sorted(filtered_matches, key=lambda x: (
    0 if x["conf_level"]=="gold" else 1 if x["conf_level"]=="silver"
    else 2 if x["conf_level"]=="bronze" else 3, -x["combined"]))

st.markdown(f"<div style='font-size:1.15rem;font-weight:700;color:#e2e8f0;margin:1rem 0;'>📊 Analiza Meciurilor Zilei "
            f"<span style='font-size:0.8rem;color:#64748b;font-weight:400;'>({len(sorted_matches)} din {len(matches)} meciuri)</span></div>",
            unsafe_allow_html=True)

h_cols = st.columns([0.7,1.9,1.9,1.8,1.5,1.5,1.5])
for col,h in zip(h_cols,["🕐 Ora","🏟️ Gazdă","✈️ Oaspete","🏆 Liga","🏠 GG Acasă","✈️ GG Depl.","📈 Prob."]):
    col.markdown(f"<span style='font-size:0.7rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;'>{h}</span>", unsafe_allow_html=True)
st.markdown('<hr style="border-top:1px solid rgba(255,255,255,0.06);margin:0.3rem 0 0.6rem;">', unsafe_allow_html=True)

for i, m in enumerate(sorted_matches):
    lvl   = m["conf_level"]
    comb  = m["combined"]
    hs    = m["home_stats"]
    as_   = m["away_stats"]
    dw    = m.get("data_warning", False)

    border = (
        "border-left:3px solid #f59e0b;" if lvl=="gold" else
        "border-left:3px solid #94a3b8;" if lvl=="silver" else
        "border-left:3px solid #b45309;" if lvl=="bronze" else
        "border-left:3px solid transparent;"
    )
    badge_html = f'<span class="badge-{lvl}">{m["conf_label"]}</span>' if lvl!="none" else ""
    warn_html  = '<span class="warn-tag">⚠️ Date limitate</span>' if dw else ""

    cols = st.columns([0.7,1.9,1.9,1.8,1.5,1.5,1.5])

    cols[0].markdown(
        f"<div style='{border}padding-left:8px;font-weight:600;color:#cbd5e1;'>{m['time']}</div>",
        unsafe_allow_html=True)

    h_form = form_html(hs.get("form_5",[]))
    trend_h = hs["trend"]
    tc_h    = hs["trend_color"]
    cols[1].markdown(
        f"<div style='font-weight:700;color:#f1f5f9;'>{m['home_team']} {badge_html} {warn_html}</div>"
        f"<div style='margin-top:3px;'>{h_form}"
        f"<span class='stat-mini' style='color:{tc_h};'>{trend_h}</span>"
        f"<span class='stat-mini'>⚽ {hs['avg_goals']}/meci</span></div>",
        unsafe_allow_html=True)

    a_form  = form_html(as_.get("form_5",[]))
    trend_a = as_["trend"]
    tc_a    = as_["trend_color"]
    cols[2].markdown(
        f"<div style='font-weight:500;color:#e2e8f0;'>{m['away_team']}</div>"
        f"<div style='margin-top:3px;'>{a_form}"
        f"<span class='stat-mini' style='color:{tc_a};'>{trend_a}</span>"
        f"<span class='stat-mini'>⚽ {as_['avg_goals']}/meci</span></div>",
        unsafe_allow_html=True)

    h2h_html = ""
    if m.get("h2h_gg") is not None:
        h2h_html = f"<br><span class='h2h-tag'>🤝 H2H: {m['h2h_gg']}% ({m['h2h_count']} meciuri)</span>"
    cols[3].markdown(
        f"<div style='font-size:0.8rem;color:#94a3b8;'>{m['league']}</div>"
        f"<div style='font-size:0.7rem;color:#475569;'>{m['country']}</div>"
        f"{h2h_html}",
        unsafe_allow_html=True)

    gg_h = m["gg_home_ctx"]
    ctx_warn_h = "" if m.get("home_ctx_valid") else " ⚠️"
    cols[4].markdown(
        f"<div style='font-size:1.05rem;font-weight:700;color:{val_color(gg_h)};'>{gg_h}%{ctx_warn_h}</div>"
        f"<div class='prob-bar-container'><div class='prob-bar' style='width:{gg_h}%;background:{prob_gradient(gg_h)};'></div></div>"
        f"<div style='font-size:0.68rem;color:#475569;margin-top:2px;'>({hs['home_m']} meci acasă)</div>",
        unsafe_allow_html=True)

    gg_a = m["gg_away_ctx"]
    ctx_warn_a = "" if m.get("away_ctx_valid") else " ⚠️"
    cols[5].markdown(
        f"<div style='font-size:1.05rem;font-weight:700;color:{val_color(gg_a)};'>{gg_a}%{ctx_warn_a}</div>"
        f"<div class='prob-bar-container'><div class='prob-bar' style='width:{gg_a}%;background:{prob_gradient(gg_a)};'></div></div>"
        f"<div style='font-size:0.68rem;color:#475569;margin-top:2px;'>({as_['away_m']} meci depl.)</div>",
        unsafe_allow_html=True)

    conf_color = m["conf_color"]
    prob_bg = (
        "rgba(245,158,11,0.12)" if lvl=="gold" else
        "rgba(56,189,248,0.10)" if lvl=="silver" else
        "rgba(180,83,9,0.10)"   if lvl=="bronze" else
        "rgba(255,255,255,0.04)"
    )
    cols[6].markdown(
        f"<div style='text-align:center;background:{prob_bg};border-radius:10px;padding:6px 4px;'>"
        f"<span style='font-size:1.15rem;font-weight:800;color:{conf_color};'>{comb}%</span></div>",
        unsafe_allow_html=True)

    with st.expander(f"📊 Detalii: {m['home_team']} vs {m['away_team']}"):
        dc1, dc2, dc3 = st.columns(3)
        with dc1:
            vc_h = "#34d399" if m.get("home_ctx_valid") else "#fcd34d"
            st.markdown(
                f"<div style='font-weight:700;color:#38bdf8;margin-bottom:8px;'>🏠 {m['home_team']}</div>"
                f"<div style='font-size:0.82rem;color:#94a3b8;line-height:2;'>"
                f"GG% Total: <strong style='color:#e2e8f0;'>{hs['gg_all']}%</strong><br>"
                f"GG% Acasă: <strong style='color:{vc_h};'>{hs['gg_home']}%</strong> ({hs['home_m']} meci)<br>"
                f"GG% Depl.: <strong style='color:#94a3b8;'>{hs['gg_away']}%</strong> ({hs['away_m']} meci)<br>"
                f"Medie goluri: <strong style='color:#f59e0b;'>{hs['avg_goals']}/meci</strong><br>"
                f"Trend: <strong style='color:{hs['trend_color']};'>{hs['trend']}</strong><br>"
                f"Ultimele 3: <strong style='color:#e2e8f0;'>{hs['recent_3']}%</strong>"
                f"</div>", unsafe_allow_html=True)
        with dc2:
            vc_a = "#34d399" if m.get("away_ctx_valid") else "#fcd34d"
            st.markdown(
                f"<div style='font-weight:700;color:#818cf8;margin-bottom:8px;'>✈️ {m['away_team']}</div>"
                f"<div style='font-size:0.82rem;color:#94a3b8;line-height:2;'>"
                f"GG% Total: <strong style='color:#e2e8f0;'>{as_['gg_all']}%</strong><br>"
                f"GG% Acasă: <strong style='color:#94a3b8;'>{as_['gg_home']}%</strong> ({as_['home_m']} meci)<br>"
                f"GG% Depl.: <strong style='color:{vc_a};'>{as_['gg_away']}%</strong> ({as_['away_m']} meci)<br>"
                f"Medie goluri: <strong style='color:#f59e0b;'>{as_['avg_goals']}/meci</strong><br>"
                f"Trend: <strong style='color:{as_['trend_color']};'>{as_['trend']}</strong><br>"
                f"Ultimele 3: <strong style='color:#e2e8f0;'>{as_['recent_3']}%</strong>"
                f"</div>", unsafe_allow_html=True)
        with dc3:
            if m.get("h2h_gg") is not None:
                h2h_pct = m["h2h_gg"]
                h2h_col = val_color(h2h_pct)
                st.markdown(
                    f"<div style='font-weight:700;color:#34d399;margin-bottom:8px;'>🤝 Față în Față (H2H)</div>"
                    f"<div style='font-size:0.82rem;color:#94a3b8;line-height:2;'>"
                    f"GG% H2H: <strong style='color:{h2h_col};font-size:1.1rem;'>{h2h_pct}%</strong><br>"
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
rec_list = [m for m in sorted_matches if m["conf_level"] in ("gold","silver")]
st.markdown('<hr class="divider">', unsafe_allow_html=True)

if rec_list:
    st.markdown(
        "<div style='font-size:1.15rem;font-weight:700;color:#e2e8f0;margin-bottom:1rem;'>"
        "🔥 Recomandările Zilei "
        "<span style='font-size:0.8rem;color:#94a3b8;font-weight:400;'>"
        "(🥇 Gold ≥85% · 🥈 Silver ≥75%)</span></div>",
        unsafe_allow_html=True)

    for m in rec_list:
        comb     = m["combined"]
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
else:
    st.markdown(
        f"<div style='text-align:center;padding:2rem;color:#64748b;'>"
        f"<div style='font-size:2rem;'>🤔</div>"
        f"<div style='margin-top:0.5rem;'>Niciun meci nu depășește pragul de {int(THRESHOLD_GG)}% astăzi.</div></div>",
        unsafe_allow_html=True)

# ─────────────────────────────────────────────
# METODOLOGIE
# ─────────────────────────────────────────────
st.markdown('<hr class="divider">', unsafe_allow_html=True)
with st.expander("📐 Metodologie & Legendă"):
    st.markdown(f"""
**Formula de calcul:**

| Situație | Formula |
|---|---|
| Cu H2H (≥3 meciuri directe) | `40% × GG_acasă + 40% × GG_deplasare + 20% × GG_H2H` |
| Fără H2H | `50% × GG_acasă + 50% × GG_deplasare` |
| Date limitate (<5 meciuri) | Probabilitate redusă cu 10% automat |

**Niveluri de încredere:**
| Nivel | Probabilitate | Semnificație |
|---|---|---|
| 🥇 Gold | ≥ 85% | Probabilitate ridicată |
| 🥈 Silver | 75–85% | Probabilitate bună — recomandat |
| 🥉 Bronze | 65–75% | Probabilitate medie |

**Trend:** Compară GG% din ultimele 3 meciuri vs media generală.
- ↗️ În creștere = ultimele 3 cu 15%+ peste medie
- ↘️ În scădere = ultimele 3 cu 15%+ sub medie

**⚠️ Date limitate**: apare când echipa are sub 5 meciuri în baza de date.

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
    GG Bet Analyzer v3 · Powered by TheSportsDB · Date actualizate la fiecare 12 ore
</div>
""", unsafe_allow_html=True)
