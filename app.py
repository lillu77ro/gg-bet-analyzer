"""
GG Bet Analyzer – Analiză statistică pentru piața „Ambele echipe marchează"
Sursă date: API-Football (api-sports.io) – 100 cereri/zi gratuit
Include: GG%, accidentați & suspendați per meci
"""

import streamlit as st
import requests
from datetime import date, datetime, timezone, timedelta
from typing import Optional, List
import time

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
# CSS PERSONALIZAT
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0f1629 50%, #0a1628 100%);
    color: #e2e8f0;
}
.main-header { text-align: center; padding: 2rem 0 1.5rem 0; }
.main-header h1 {
    font-size: 2.8rem; font-weight: 800;
    background: linear-gradient(90deg, #38bdf8, #818cf8, #f472b6);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; margin-bottom: 0.3rem;
}
.main-header p { color: #94a3b8; font-size: 1.05rem; }

.metric-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px; padding: 1.4rem 1.6rem; text-align: center;
}
.metric-card .value { font-size: 2.2rem; font-weight: 800; color: #38bdf8; }
.metric-card .label {
    font-size: 0.82rem; color: #94a3b8; margin-top: 0.3rem;
    text-transform: uppercase; letter-spacing: 0.06em;
}
.divider { border: none; border-top: 1px solid rgba(255,255,255,0.07); margin: 1.5rem 0; }

.prob-bar-container {
    width: 100%; background: rgba(255,255,255,0.07);
    border-radius: 999px; height: 6px; margin-top: 4px;
}
.prob-bar { height: 6px; border-radius: 999px; }

.badge-hot {
    background: linear-gradient(90deg, #f59e0b, #ef4444);
    color: white; font-size: 0.65rem; font-weight: 700;
    padding: 2px 8px; border-radius: 999px; text-transform: uppercase;
}
.injury-card {
    background: rgba(248,113,113,0.07);
    border: 1px solid rgba(248,113,113,0.2);
    border-radius: 10px; padding: 0.6rem 0.9rem; margin-top: 0.4rem;
}
.injury-card .title {
    font-size: 0.72rem; font-weight: 700; color: #fca5a5;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem;
}
.injury-tag {
    display: inline-block;
    background: rgba(239,68,68,0.15);
    border: 1px solid rgba(239,68,68,0.3);
    color: #fca5a5; font-size: 0.72rem; font-weight: 600;
    padding: 2px 8px; border-radius: 6px; margin: 2px 3px 2px 0;
}
.suspension-tag {
    display: inline-block;
    background: rgba(245,158,11,0.15);
    border: 1px solid rgba(245,158,11,0.3);
    color: #fcd34d; font-size: 0.72rem; font-weight: 600;
    padding: 2px 8px; border-radius: 6px; margin: 2px 3px 2px 0;
}
.no-injury { font-size: 0.75rem; color: #34d399; font-weight: 500; }
.footer-note {
    background: rgba(248,113,113,0.08);
    border: 1px solid rgba(248,113,113,0.2);
    border-radius: 12px; padding: 1rem 1.4rem; margin-top: 2rem;
    font-size: 0.82rem; color: #fca5a5; line-height: 1.6;
}
#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONSTANTE
# ─────────────────────────────────────────────
API_KEY      = "dfa5287647ea0d419182bbeec6f924c3"
API_BASE     = "https://v3.football.api-sports.io"
THRESHOLD_GG = 75.0
NUM_MATCHES  = 10
RO_TZ        = timezone(timedelta(hours=3))
MAX_MATCHES  = 20

# ─────────────────────────────────────────────
# FUNCȚII API
# ─────────────────────────────────────────────

def api_get(endpoint, params=None):
    headers = {"x-apisports-key": API_KEY, "Accept": "application/json"}
    try:
        r = requests.get(f"{API_BASE}{endpoint}", headers=headers,
                         params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_todays_fixtures():
    today = date.today().strftime("%Y-%m-%d")
    data = api_get("/fixtures", {"date": today})
    if not data or not data.get("response"):
        return []

    FINISHED = {"FT", "AET", "PEN", "FT_PEN", "AWD", "WO", "CANC", "ABD", "INT", "PST"}
    EXCLUDE  = [" W", "Women", "Youth", "U20", "U21", "U23", "Reserve", "Friendly"]
    fixtures = []

    for f in data["response"]:
        fi     = f.get("fixture", {})
        teams  = f.get("teams", {})
        league = f.get("league", {})

        if fi.get("status", {}).get("short", "") in FINISHED:
            continue

        league_name = league.get("name", "")
        if any(x in league_name for x in EXCLUDE):
            continue

        raw_date = fi.get("date", "")
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            time_str = dt.astimezone(RO_TZ).strftime("%H:%M")
        except Exception:
            time_str = "N/A"

        fixtures.append({
            "fixture_id":   fi.get("id"),
            "home_team":    teams.get("home", {}).get("name", "N/A"),
            "away_team":    teams.get("away", {}).get("name", "N/A"),
            "home_team_id": teams.get("home", {}).get("id"),
            "away_team_id": teams.get("away", {}).get("id"),
            "league":       league_name,
            "country":      league.get("country", ""),
            "time":         time_str,
            "timestamp":    fi.get("timestamp", 0),
        })

    return sorted(fixtures, key=lambda x: x["timestamp"])[:MAX_MATCHES]


def fetch_team_last_matches(team_id):
    data = api_get("/fixtures", {"team": team_id, "last": NUM_MATCHES})
    if not data or not data.get("response"):
        return []
    finished = {"FT", "AET", "PEN", "FT_PEN", "AWD", "WO"}
    return [
        f for f in data["response"]
        if f.get("fixture", {}).get("status", {}).get("short", "") in finished
    ]


def calc_gg(fixtures_data):
    gg, total = 0, 0
    for f in fixtures_data:
        goals = f.get("goals", {})
        h, a = goals.get("home"), goals.get("away")
        if h is None or a is None:
            continue
        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            continue
        total += 1
        if h > 0 and a > 0:
            gg += 1
    return round((gg / total) * 100, 1) if total > 0 else 0.0


def fetch_injuries(fixture_id, home_id, away_id):
    data = api_get("/injuries", {"fixture": fixture_id})
    result = {"home": [], "away": []}
    if not data or not data.get("response"):
        return result
    for entry in data["response"]:
        player = entry.get("player", {})
        team   = entry.get("team", {})
        info = {
            "name":   player.get("name", "Unknown"),
            "reason": player.get("reason") or "N/A",
            "type":   player.get("type", "Unknown"),
        }
        tid = team.get("id")
        if tid == home_id:
            result["home"].append(info)
        elif tid == away_id:
            result["away"].append(info)
    return result


def analyze_match(match):
    home_matches = fetch_team_last_matches(match["home_team_id"])
    time.sleep(0.25)
    away_matches = fetch_team_last_matches(match["away_team_id"])
    time.sleep(0.25)

    gg_home = calc_gg(home_matches)
    gg_away = calc_gg(away_matches)
    combined = round((gg_home + gg_away) / 2, 1)

    injuries = fetch_injuries(
        match["fixture_id"],
        match["home_team_id"],
        match["away_team_id"]
    )
    time.sleep(0.25)

    return {
        **match,
        "gg_home":        gg_home,
        "gg_away":        gg_away,
        "combined":       combined,
        "is_recommended": combined >= THRESHOLD_GG,
        "home_injured":   injuries["home"],
        "away_injured":   injuries["away"],
        "home_n":         len(home_matches),
        "away_n":         len(away_matches),
    }


# ─────────────────────────────────────────────
# DATE DEMO
# ─────────────────────────────────────────────
def demo_data():
    return [
        {"fixture_id": 1, "home_team": "Manchester City", "away_team": "Arsenal",
         "league": "Premier League", "country": "England", "time": "18:30",
         "gg_home": 82.0, "gg_away": 76.0, "combined": 79.0, "is_recommended": True,
         "home_injured": [{"name": "Kevin De Bruyne", "reason": "Knee", "type": "Injured"}],
         "away_injured": [], "home_n": 10, "away_n": 10},
        {"fixture_id": 2, "home_team": "Bayern München", "away_team": "Borussia Dortmund",
         "league": "Bundesliga", "country": "Germany", "time": "20:30",
         "gg_home": 90.0, "gg_away": 80.0, "combined": 85.0, "is_recommended": True,
         "home_injured": [],
         "away_injured": [{"name": "Marco Reus", "reason": "Yellow Cards", "type": "Suspended"}],
         "home_n": 10, "away_n": 10},
        {"fixture_id": 3, "home_team": "Real Madrid", "away_team": "Atletico Madrid",
         "league": "La Liga", "country": "Spain", "time": "21:00",
         "gg_home": 70.0, "gg_away": 60.0, "combined": 65.0, "is_recommended": False,
         "home_injured": [], "away_injured": [], "home_n": 10, "away_n": 10},
        {"fixture_id": 4, "home_team": "Inter Milan", "away_team": "AC Milan",
         "league": "Serie A", "country": "Italy", "time": "20:45",
         "gg_home": 88.0, "gg_away": 84.0, "combined": 86.0, "is_recommended": True,
         "home_injured": [{"name": "Lautaro Martinez", "reason": "Muscle", "type": "Injured"}],
         "away_injured": [{"name": "Theo Hernandez", "reason": "Red Card", "type": "Suspended"}],
         "home_n": 10, "away_n": 10},
        {"fixture_id": 5, "home_team": "PSG", "away_team": "Lyon",
         "league": "Ligue 1", "country": "France", "time": "19:00",
         "gg_home": 78.0, "gg_away": 72.0, "combined": 75.0, "is_recommended": False,
         "home_injured": [], "away_injured": [], "home_n": 10, "away_n": 10},
        {"fixture_id": 6, "home_team": "Feyenoord", "away_team": "Ajax",
         "league": "Eredivisie", "country": "Netherlands", "time": "17:45",
         "gg_home": 80.0, "gg_away": 90.0, "combined": 85.0, "is_recommended": True,
         "home_injured": [], "away_injured": [], "home_n": 10, "away_n": 10},
    ]


# ─────────────────────────────────────────────
# FUNCȚII HELPER UI
# ─────────────────────────────────────────────

def prob_gradient(val):
    if val >= THRESHOLD_GG:
        return "linear-gradient(90deg, #38bdf8, #818cf8)"
    elif val >= 60:
        return "linear-gradient(90deg, #f59e0b, #fb923c)"
    return "linear-gradient(90deg, #64748b, #94a3b8)"


def val_color(val):
    if val >= THRESHOLD_GG:
        return "#38bdf8"
    elif val >= 60:
        return "#f59e0b"
    return "#94a3b8"


def render_injuries(players, team_name):
    if not players:
        return '<span class="no-injury">✅ Fără absențe cunoscute</span>'
    html = ""
    for p in players:
        reason = p["reason"] if p["reason"] != "N/A" else "Accidentat"
        if p["type"] == "Injured":
            html += f'<span class="injury-tag">🚑 {p["name"]} · {reason}</span>'
        else:
            html += f'<span class="suspension-tag">🟨 {p["name"]} · {reason}</span>'
    return html


# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
months_ro = {
    "January": "Ianuarie", "February": "Februarie", "March": "Martie",
    "April": "Aprilie", "May": "Mai", "June": "Iunie",
    "July": "Iulie", "August": "August", "September": "Septembrie",
    "October": "Octombrie", "November": "Noiembrie", "December": "Decembrie"
}
today_str = datetime.now(RO_TZ).strftime("%d %B %Y")
for en, ro in months_ro.items():
    today_str = today_str.replace(en, ro)

st.markdown(f"""
<div class="main-header">
    <h1>⚽ GG Bet Analyzer</h1>
    <p>Analiză statistică · Piața <strong>Ambele Echipe Marchează</strong> · {today_str}</p>
</div>
""", unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# BUTON REÎMPROSPĂTARE
# ─────────────────────────────────────────────
_, col_btn, _ = st.columns([3, 2, 3])
with col_btn:
    if st.button("🔄  Reîmprospătează Datele", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
st.markdown(
    "<div style='text-align:center;font-size:0.72rem;color:#475569;margin-top:4px;'>"
    "⚠️ Reîmprospătarea manuală consumă din cota zilnică de API (100 cereri/zi). "
    "Datele se actualizează automat o dată pe zi."
    "</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ÎNCĂRCARE DATE (cache 24h — econom cereri API)
# ─────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def load_all_data():
    fixtures = fetch_todays_fixtures()

    if not fixtures:
        return demo_data(), True

    analyzed = []
    for m in fixtures:
        if not m.get("home_team_id") or not m.get("away_team_id"):
            continue
        result = analyze_match(m)
        analyzed.append(result)

    if not analyzed:
        return demo_data(), True

    return analyzed, False


with st.spinner("⏳ Se preiau meciurile, statisticile GG și informațiile despre accidentați..."):
    matches, is_demo = load_all_data()

if is_demo:
    st.info(
        "ℹ️ **Mod demonstrativ** — API-ul nu returnează meciuri programate pentru astăzi "
        "(posibil pauză competițională). Datele afișate sunt exemple statistice realiste.",
    )

# ─────────────────────────────────────────────
# STATISTICI SUMAR
# ─────────────────────────────────────────────
total       = len(matches)
recomandate = sum(1 for m in matches if m["is_recommended"])
avg_comb    = round(sum(m["combined"] for m in matches) / total, 1) if total else 0.0
max_comb    = max((m["combined"] for m in matches), default=0.0)
total_abs   = sum(len(m["home_injured"]) + len(m["away_injured"]) for m in matches)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)
cards = [
    (c1, str(total),       "Meciuri analizate",            "#38bdf8"),
    (c2, str(recomandate), f"Recomandări GG (>{int(THRESHOLD_GG)}%)", "#f472b6"),
    (c3, f"{avg_comb}%",   "Probabilitate medie",          "#a78bfa"),
    (c4, f"{max_comb}%",   "Probabilitate maximă",         "#34d399"),
    (c5, str(total_abs),   "Absențe identificate",         "#fb923c"),
]
for col, val, label, color in cards:
    col.markdown(f"""
    <div class="metric-card">
        <div class="value" style="color:{color};">{val}</div>
        <div class="label">{label}</div>
    </div>""", unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# TABEL PRINCIPAL
# ─────────────────────────────────────────────
sorted_matches = sorted(matches, key=lambda x: (-int(x["is_recommended"]), -x["combined"]))

st.markdown("""
<div style="font-size:1.15rem; font-weight:700; color:#e2e8f0; margin-bottom:1rem;">
    📊 Analiza Meciurilor Zilei
</div>""", unsafe_allow_html=True)

h_cols = st.columns([0.8, 2.2, 2.2, 2.2, 1.4, 1.6, 1.6])
for col, h in zip(h_cols, ["🕐 Ora", "🏟️ Gazdă", "✈️ Oaspete", "🏆 Liga",
                             "🏠 GG Acasă", "✈️ GG Depl.", "📈 Prob."]):
    col.markdown(
        f"<span style='font-size:0.7rem;color:#64748b;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:0.06em;'>{h}</span>",
        unsafe_allow_html=True)
st.markdown('<hr style="border-top:1px solid rgba(255,255,255,0.06);margin:0.3rem 0 0.6rem;">',
            unsafe_allow_html=True)

for i, m in enumerate(sorted_matches):
    rec     = m["is_recommended"]
    h_inj   = m.get("home_injured", [])
    a_inj   = m.get("away_injured", [])
    any_abs = h_inj or a_inj

    cols    = st.columns([0.8, 2.2, 2.2, 2.2, 1.4, 1.6, 1.6])
    border  = "border-left:3px solid #38bdf8;" if rec else "border-left:3px solid transparent;"
    badge   = '<span class="badge-hot">⭐ TOP</span>' if rec else ""
    abs_icon = " ⚠️" if any_abs else ""

    cols[0].markdown(
        f"<div style='{border}padding-left:8px;font-weight:600;color:#cbd5e1;'>{m['time']}</div>",
        unsafe_allow_html=True)
    cols[1].markdown(
        f"<div style='font-weight:700;color:#f1f5f9;'>{m['home_team']} {badge}</div>",
        unsafe_allow_html=True)
    cols[2].markdown(
        f"<div style='font-weight:500;color:#e2e8f0;'>{m['away_team']}{abs_icon}</div>",
        unsafe_allow_html=True)
    cols[3].markdown(
        f"<div style='font-size:0.8rem;color:#94a3b8;'>{m['league']}</div>",
        unsafe_allow_html=True)

    for col, val in [(cols[4], m["gg_home"]), (cols[5], m["gg_away"])]:
        col.markdown(
            f"<div style='font-size:1.05rem;font-weight:700;color:{val_color(val)};'>{val}%</div>"
            f"<div class='prob-bar-container'><div class='prob-bar' "
            f"style='width:{val}%;background:{prob_gradient(val)};'></div></div>",
            unsafe_allow_html=True)

    prob_bg  = "rgba(56,189,248,0.12)" if rec else "rgba(255,255,255,0.04)"
    combined = m["combined"]
    comb_col = val_color(combined)
    cols[6].markdown(
        f"<div style='text-align:center;background:{prob_bg};border-radius:10px;padding:6px 4px;'>"
        f"<span style='font-size:1.15rem;font-weight:800;color:{comb_col};'>"
        f"{combined}%</span></div>",
        unsafe_allow_html=True)

    if any_abs:
        with st.expander(f"⚠️ Absențe: {m['home_team']} vs {m['away_team']}"):
            col_h, col_a = st.columns(2)
            with col_h:
                st.markdown(
                    f"<div class='injury-card'>"
                    f"<div class='title'>🏠 {m['home_team']}</div>"
                    f"{render_injuries(h_inj, m['home_team'])}"
                    f"</div>", unsafe_allow_html=True)
            with col_a:
                st.markdown(
                    f"<div class='injury-card'>"
                    f"<div class='title'>✈️ {m['away_team']}</div>"
                    f"{render_injuries(a_inj, m['away_team'])}"
                    f"</div>", unsafe_allow_html=True)

    if i < len(sorted_matches) - 1:
        st.markdown('<hr style="border-top:1px solid rgba(255,255,255,0.04);margin:0.5rem 0;">',
                    unsafe_allow_html=True)

# ─────────────────────────────────────────────
# RECOMANDĂRILE ZILEI
# ─────────────────────────────────────────────
rec_list = [m for m in sorted_matches if m["is_recommended"]]
st.markdown('<hr class="divider">', unsafe_allow_html=True)

if rec_list:
    st.markdown(f"""
    <div style="font-size:1.15rem;font-weight:700;color:#e2e8f0;margin-bottom:1rem;">
        🔥 Recomandările Zilei
        <span style="font-size:0.8rem;color:#94a3b8;font-weight:400;">
            (probabilitate >{int(THRESHOLD_GG)}%)
        </span>
    </div>""", unsafe_allow_html=True)

    for m in rec_list:
        total_abs_m = len(m.get("home_injured", [])) + len(m.get("away_injured", []))
        gg_h    = m["gg_home"]
        gg_a    = m["gg_away"]
        comb    = m["combined"]
        home_t  = m["home_team"]
        away_t  = m["away_team"]
        league_n = m["league"]
        time_n   = m["time"]

        with st.container():
            col_info, col_prob = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"<div style='background:linear-gradient(135deg,rgba(56,189,248,0.08),"
                    f"rgba(129,140,248,0.08));border:1px solid rgba(56,189,248,0.25);"
                    f"border-radius:16px;padding:1.2rem 1.5rem;'>"
                    f"<div style='font-size:1.05rem;font-weight:700;color:#e2e8f0;'>"
                    f"🏠 {home_t} <span style='color:#64748b;'>vs</span> {away_t} ✈️</div>"
                    f"<div style='font-size:0.8rem;color:#94a3b8;margin-top:2px;'>"
                    f"🏆 {league_n} &nbsp;·&nbsp; 🕐 {time_n}</div>"
                    f"<div style='margin-top:0.4rem;font-size:0.8rem;color:#64748b;'>"
                    f"GG Acasă: <strong style='color:#38bdf8;'>{gg_h}%</strong>"
                    f" &nbsp;·&nbsp; "
                    f"GG Deplasare: <strong style='color:#818cf8;'>{gg_a}%</strong></div>"
                    + (f"<div style='font-size:0.75rem;color:#fb923c;margin-top:4px;'>"
                       f"⚠️ {total_abs_m} absențe identificate</div>" if total_abs_m else "")
                    + "</div>",
                    unsafe_allow_html=True)
            with col_prob:
                st.markdown(
                    f"<div style='text-align:center;"
                    f"background:linear-gradient(135deg,#38bdf8,#818cf8);"
                    f"border-radius:50%;width:60px;height:60px;"
                    f"display:flex;align-items:center;justify-content:center;"
                    f"font-size:0.9rem;font-weight:800;color:white;margin:auto;'>"
                    f"{comb}%</div>",
                    unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div style="text-align:center;padding:2rem;color:#64748b;">
        <div style="font-size:2rem;">🤔</div>
        <div style="margin-top:0.5rem;">Niciun meci nu depășește pragul de {int(THRESHOLD_GG)}% astăzi.</div>
    </div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# METODOLOGIE
# ─────────────────────────────────────────────
st.markdown('<hr class="divider">', unsafe_allow_html=True)

with st.expander("📐 Metodologie de calcul"):
    st.markdown(f"""
**Cum se calculează probabilitatea GG?**

1. **Date colectate**: Ultimele **{NUM_MATCHES} meciuri** finalizate ale fiecărei echipe (via API-Football).
2. **% GG echipă**: meciuri cu gol de ambele echipe ÷ total meciuri × 100.
3. **Probabilitate combinată**: media aritmetică între % GG gazdă și % GG oaspete.
4. **Recomandare**: meciuri cu probabilitate ≥ **{int(THRESHOLD_GG)}%**.

**Accidentați & suspendați**: date preluate în timp real de la API-Football pentru fiecare meci.

**Sursă date**: [API-Football](https://www.api-football.com/) – 100 cereri/zi (plan gratuit).
**Cache**: datele sunt stocate 24h pentru a economisi cererile API.
""")

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown("""
<div class="footer-note">
    ⚠️ <strong>Notă importantă:</strong> Datele și procentajele afișate au caracter exclusiv
    statistic și informativ, bazate pe istoricul recent al echipelor.
    Ele <strong>nu reprezintă o garanție de câștig</strong> și nu constituie sfaturi de pariuri.
    Parierile implică riscuri financiare semnificative. Jucați responsabil.
    Vârsta minimă legală pentru pariuri sportive în România este de <strong>18 ani</strong>.
</div>
<div style="text-align:center;padding:1.5rem 0 0.5rem;color:#334155;font-size:0.75rem;">
    GG Bet Analyzer · Date actualizate zilnic · Powered by API-Football
</div>
""", unsafe_allow_html=True)
