"""
GG Bet Analyzer – Analiză statistică pentru piața „Ambele echipe marchează"
Surse de date: TheSportsDB API (gratuit, fără cheie) + fallback date demo
"""

import streamlit as st
import requests
import pandas as pd
from datetime import date, datetime, timedelta
import time
import random
from typing import Optional, List, Dict

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

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Dark background */
.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0f1629 50%, #0a1628 100%);
    color: #e2e8f0;
}

/* Header principal */
.main-header {
    text-align: center;
    padding: 2rem 0 1.5rem 0;
}
.main-header h1 {
    font-size: 2.8rem;
    font-weight: 800;
    background: linear-gradient(90deg, #38bdf8, #818cf8, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.3rem;
}
.main-header p {
    color: #94a3b8;
    font-size: 1.05rem;
    font-weight: 400;
}

/* Card metrici */
.metric-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 1.4rem 1.6rem;
    text-align: center;
    backdrop-filter: blur(12px);
}
.metric-card .value {
    font-size: 2.2rem;
    font-weight: 800;
    color: #38bdf8;
}
.metric-card .label {
    font-size: 0.82rem;
    color: #94a3b8;
    margin-top: 0.3rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* Tabel principal */
.match-table-container {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 20px;
    padding: 1.5rem;
    margin-top: 1.5rem;
    overflow-x: auto;
}
.match-table-container h3 {
    color: #e2e8f0;
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

/* Badge recomandare */
.badge-hot {
    background: linear-gradient(90deg, #f59e0b, #ef4444);
    color: white;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 10px;
    border-radius: 999px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.badge-normal {
    background: rgba(148,163,184,0.15);
    color: #94a3b8;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 999px;
}

/* Bara procentaj */
.prob-bar-container {
    width: 100%;
    background: rgba(255,255,255,0.07);
    border-radius: 999px;
    height: 6px;
    margin-top: 4px;
}
.prob-bar {
    height: 6px;
    border-radius: 999px;
}

/* Separator elegant */
.divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.07);
    margin: 1.5rem 0;
}

/* Footer */
.footer-note {
    background: rgba(248, 113, 113, 0.08);
    border: 1px solid rgba(248,113,113,0.2);
    border-radius: 12px;
    padding: 1rem 1.4rem;
    margin-top: 2rem;
    font-size: 0.82rem;
    color: #fca5a5;
    line-height: 1.6;
}

/* Stilizare dataframe Streamlit */
.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
}

/* Loading spinner text */
.loading-text {
    text-align: center;
    color: #64748b;
    font-size: 0.9rem;
    padding: 2rem;
}

/* Recomandare destacată */
.recommendation-card {
    background: linear-gradient(135deg, rgba(56,189,248,0.08) 0%, rgba(129,140,248,0.08) 100%);
    border: 1px solid rgba(56,189,248,0.25);
    border-radius: 16px;
    padding: 1.2rem 1.5rem;
    margin: 0.6rem 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.recommendation-card .teams {
    font-size: 1.05rem;
    font-weight: 700;
    color: #e2e8f0;
}
.recommendation-card .league {
    font-size: 0.8rem;
    color: #94a3b8;
    margin-top: 2px;
}
.recommendation-card .prob-circle {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: linear-gradient(135deg, #38bdf8, #818cf8);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.9rem;
    font-weight: 800;
    color: white;
    flex-shrink: 0;
}

/* Ascunde hamburger menu Streamlit */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# CONSTANTE & CONFIGURARE
# ─────────────────────────────────────────────
THRESHOLD_GG = 75.0          # Pragul de recomandare (%)
NUM_RECENT_MATCHES = 10      # Câte meciuri recente analizăm

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

# TheSportsDB API – complet gratuit, fără cheie
TSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"


# ─────────────────────────────────────────────
# FUNCȚII AJUTĂTOARE
# ─────────────────────────────────────────────

def safe_get(url: str, timeout: int = 10) -> Optional[dict]:
    """Apel HTTP cu tratare erori."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def calc_gg_percent(events: list) -> float:
    """
    Calculează % meciuri GG dintr-o listă de evenimente TheSportsDB.
    Un meci e GG dacă ambele echipe au marcat cel puțin 1 gol.
    """
    if not events:
        return 0.0
    gg_count = 0
    total = 0
    for ev in events:
        score_h = ev.get("intHomeScore")
        score_a = ev.get("intAwayScore")
        if score_h is None or score_a is None:
            continue
        try:
            h, a = int(score_h), int(score_a)
        except (ValueError, TypeError):
            continue
        total += 1
        if h > 0 and a > 0:
            gg_count += 1
    return round((gg_count / total) * 100, 1) if total > 0 else 0.0


def fetch_team_last_events(team_id: str, n: int = NUM_RECENT_MATCHES) -> list:
    """Preia ultimele n meciuri finalizate ale echipei."""
    url = f"{TSDB_BASE}/eventslast.php?id={team_id}"
    data = safe_get(url)
    if not data:
        return []
    events = data.get("results") or []
    return events[:n]


def fetch_todays_matches() -> list:
    """
    Preia meciurile de fotbal de azi via TheSportsDB.
    Returnează o listă de dict-uri cu câmpuri normalizate.
    """
    today = date.today().strftime("%Y-%m-%d")
    url = f"{TSDB_BASE}/eventsday.php?d={today}&s=Soccer"
    data = safe_get(url)
    if not data:
        return []
    events = data.get("events") or []
    matches = []
    for ev in events:
        # Filtrăm doar meciuri programate (nu finalizate)
        status = (ev.get("strStatus") or "").lower()
        if status in ("ft", "aet", "pen", "finished", "final"):
            continue
        matches.append({
            "id": ev.get("idEvent", ""),
            "home_team": ev.get("strHomeTeam", "N/A"),
            "away_team": ev.get("strAwayTeam", "N/A"),
            "home_team_id": ev.get("idHomeTeam", ""),
            "away_team_id": ev.get("idAwayTeam", ""),
            "league": ev.get("strLeague", "N/A"),
            "time": ev.get("strTime", "00:00")[:5] if ev.get("strTime") else "N/A",
            "date": ev.get("dateEvent", today),
        })
    return matches


def analyze_match(match: dict) -> dict:
    """
    Calculează % GG pentru ambele echipe și probabilitatea combinată.
    """
    home_events = fetch_team_last_events(match["home_team_id"])
    time.sleep(0.3)  # Respectăm rate-limit API
    away_events = fetch_team_last_events(match["away_team_id"])

    gg_home = calc_gg_percent(home_events)
    gg_away = calc_gg_percent(away_events)

    # Probabilitate combinată = media ponderată
    combined = round((gg_home + gg_away) / 2, 1)

    return {
        **match,
        "gg_home": gg_home,
        "gg_away": gg_away,
        "combined": combined,
        "is_recommended": combined >= THRESHOLD_GG,
        "home_matches": len(home_events),
        "away_matches": len(away_events),
    }


# ─────────────────────────────────────────────
# DATE DEMO (fallback când API-ul nu returnează date)
# ─────────────────────────────────────────────

def generate_demo_data() -> list:
    """Date demonstrative realiste pentru ziua curentă."""
    today_str = date.today().strftime("%Y-%m-%d")
    demo_matches = [
        {
            "id": "demo_1",
            "home_team": "Manchester City",
            "away_team": "Arsenal",
            "home_team_id": "",
            "away_team_id": "",
            "league": "Premier League",
            "time": "18:30",
            "date": today_str,
            "gg_home": 82.0,
            "gg_away": 76.0,
            "combined": 79.0,
            "is_recommended": True,
            "home_matches": 10,
            "away_matches": 10,
        },
        {
            "id": "demo_2",
            "home_team": "Bayern München",
            "away_team": "Borussia Dortmund",
            "home_team_id": "",
            "away_team_id": "",
            "league": "Bundesliga",
            "time": "20:30",
            "date": today_str,
            "gg_home": 90.0,
            "gg_away": 80.0,
            "combined": 85.0,
            "is_recommended": True,
            "home_matches": 10,
            "away_matches": 10,
        },
        {
            "id": "demo_3",
            "home_team": "Real Madrid",
            "away_team": "Atlético Madrid",
            "home_team_id": "",
            "away_team_id": "",
            "league": "La Liga",
            "time": "21:00",
            "date": today_str,
            "gg_home": 70.0,
            "gg_away": 60.0,
            "combined": 65.0,
            "is_recommended": False,
            "home_matches": 10,
            "away_matches": 10,
        },
        {
            "id": "demo_4",
            "home_team": "PSG",
            "away_team": "Lyon",
            "home_team_id": "",
            "away_team_id": "",
            "league": "Ligue 1",
            "time": "19:00",
            "date": today_str,
            "gg_home": 78.0,
            "gg_away": 72.0,
            "combined": 75.0,
            "is_recommended": False,
            "home_matches": 10,
            "away_matches": 10,
        },
        {
            "id": "demo_5",
            "home_team": "Inter Milan",
            "away_team": "AC Milan",
            "home_team_id": "",
            "away_team_id": "",
            "league": "Serie A",
            "time": "20:45",
            "date": today_str,
            "gg_home": 88.0,
            "gg_away": 84.0,
            "combined": 86.0,
            "is_recommended": True,
            "home_matches": 10,
            "away_matches": 10,
        },
        {
            "id": "demo_6",
            "home_team": "Sporting CP",
            "away_team": "FC Porto",
            "home_team_id": "",
            "away_team_id": "",
            "league": "Primeira Liga",
            "time": "21:15",
            "date": today_str,
            "gg_home": 60.0,
            "gg_away": 55.0,
            "combined": 57.5,
            "is_recommended": False,
            "home_matches": 10,
            "away_matches": 10,
        },
        {
            "id": "demo_7",
            "home_team": "Feyenoord",
            "away_team": "Ajax",
            "home_team_id": "",
            "away_team_id": "",
            "league": "Eredivisie",
            "time": "17:45",
            "date": today_str,
            "gg_home": 80.0,
            "gg_away": 90.0,
            "combined": 85.0,
            "is_recommended": True,
            "home_matches": 10,
            "away_matches": 10,
        },
        {
            "id": "demo_8",
            "home_team": "Galatasaray",
            "away_team": "Fenerbahçe",
            "home_team_id": "",
            "away_team_id": "",
            "league": "Süper Lig",
            "time": "20:00",
            "date": today_str,
            "gg_home": 70.0,
            "gg_away": 80.0,
            "combined": 75.0,
            "is_recommended": False,
            "home_matches": 10,
            "away_matches": 10,
        },
    ]
    return demo_matches


# ─────────────────────────────────────────────
# FUNCȚIE BARĂ DE CULOARE PENTRU PROBABILITATE
# ─────────────────────────────────────────────

def prob_color(val: float) -> str:
    """Returnează culoarea barei de progres în funcție de valoare."""
    if val >= THRESHOLD_GG:
        return "linear-gradient(90deg, #38bdf8, #818cf8)"
    elif val >= 60:
        return "linear-gradient(90deg, #f59e0b, #fb923c)"
    else:
        return "linear-gradient(90deg, #64748b, #94a3b8)"


def color_cell(val: float) -> str:
    """Culoare text pentru valorile din tabel."""
    if val >= THRESHOLD_GG:
        return "#38bdf8"
    elif val >= 60:
        return "#f59e0b"
    else:
        return "#94a3b8"


# ─────────────────────────────────────────────
# INTERFAȚA STREAMLIT
# ─────────────────────────────────────────────

# Header
st.markdown("""
<div class="main-header">
    <h1>⚽ GG Bet Analyzer</h1>
    <p>Analiză statistică în timp real · Piața <strong>Ambele Echipe Marchează</strong> · {}</p>
</div>
""".format(
    datetime.now().strftime("%d %B %Y").replace(
        "January", "Ianuarie").replace("February", "Februarie").replace(
        "March", "Martie").replace("April", "Aprilie").replace(
        "May", "Mai").replace("June", "Iunie").replace(
        "July", "Iulie").replace("August", "August").replace(
        "September", "Septembrie").replace("October", "Octombrie").replace(
        "November", "Noiembrie").replace("December", "Decembrie")
), unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─── Buton reîmprospătare ───
col_left, col_btn, col_right = st.columns([3, 2, 3])
with col_btn:
    refresh = st.button("🔄  Reîmprospătează Datele", use_container_width=True)

# ─── Încărcare & analiză date ───
@st.cache_data(ttl=1800, show_spinner=False)  # Cache 30 min
def load_and_analyze():
    """Preia și analizează meciurile zilei."""
    raw_matches = fetch_todays_matches()
    is_demo = False

    if not raw_matches:
        # Fallback la date demo
        return generate_demo_data(), True

    analyzed = []
    for m in raw_matches:
        if not m["home_team_id"] or not m["away_team_id"]:
            continue
        result = analyze_match(m)
        analyzed.append(result)
        time.sleep(0.2)

    if not analyzed:
        return generate_demo_data(), True

    return analyzed, False


if refresh:
    st.cache_data.clear()
    st.rerun()

# ─── Spinner cu mesaj ───
with st.spinner("⏳ Se preiau și se analizează meciurile zilei..."):
    matches_data, is_demo_mode = load_and_analyze()

# ─── Banner mod demo ───
if is_demo_mode:
    st.info(
        "ℹ️ **Mod demonstrativ** — API-ul public nu returnează meciuri programate pentru astăzi "
        "(posibil perioadă fără meciuri sau limită de rate). "
        "Datele afișate sunt exemple statistice realiste.",
        icon=None
    )

# ─── Statistici sumar ───
total = len(matches_data)
recomandate = sum(1 for m in matches_data if m["is_recommended"])
avg_combined = round(sum(m["combined"] for m in matches_data) / total, 1) if total > 0 else 0.0
max_combined = max((m["combined"] for m in matches_data), default=0.0)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="value">{total}</div>
        <div class="label">Meciuri analizate</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="value" style="color:#f472b6">{recomandate}</div>
        <div class="label">Recomandări GG (&gt;{int(THRESHOLD_GG)}%)</div>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="value" style="color:#a78bfa">{avg_combined}%</div>
        <div class="label">Probabilitate medie</div>
    </div>""", unsafe_allow_html=True)
with c4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="value" style="color:#34d399">{max_combined}%</div>
        <div class="label">Probabilitate maximă</div>
    </div>""", unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# TABEL PRINCIPAL
# ─────────────────────────────────────────────

# Sortăm: recomandate primul, apoi descrescător după probabilitate
sorted_matches = sorted(matches_data, key=lambda x: (-int(x["is_recommended"]), -x["combined"]))

st.markdown("""
<div style="font-size:1.15rem; font-weight:700; color:#e2e8f0; margin-bottom:1rem;">
    📊 Analiza Meciurilor Zilei
</div>
""", unsafe_allow_html=True)

# Header tabel
header_cols = st.columns([1, 2.5, 2.5, 2.5, 1.5, 2, 1.8])
headers = ["🕐 Ora", "🏟️ Echipa Gazdă", "✈️ Echipa Oaspete", "🏆 Liga",
           "🏠 % GG Acasă", "✈️ % GG Deplasare", "📈 Probabilitate"]

for col, h in zip(header_cols, headers):
    col.markdown(f"<span style='font-size:0.72rem; color:#64748b; font-weight:600; text-transform:uppercase; letter-spacing:0.06em;'>{h}</span>",
                 unsafe_allow_html=True)

st.markdown('<hr style="border-top:1px solid rgba(255,255,255,0.06); margin:0.4rem 0 0.8rem 0;">', unsafe_allow_html=True)

# Rânduri tabel
for i, m in enumerate(sorted_matches):
    rec = m["is_recommended"]
    row_bg = "rgba(56,189,248,0.04)" if rec else "transparent"
    border = "border-left: 3px solid #38bdf8;" if rec else "border-left: 3px solid transparent;"

    cols = st.columns([1, 2.5, 2.5, 2.5, 1.5, 2, 1.8])

    # Ora
    cols[0].markdown(
        f"<div style='{border} padding-left:8px; font-weight:600; color:#cbd5e1;'>{m['time']}</div>",
        unsafe_allow_html=True
    )

    # Echipa gazdă + badge
    badge = '<span class="badge-hot">⭐ TOP</span>' if rec else ""
    cols[1].markdown(
        f"<div style='font-weight:600; color:#f1f5f9;'>{m['home_team']} {badge}</div>",
        unsafe_allow_html=True
    )

    # Echipa oaspete
    cols[2].markdown(
        f"<div style='font-weight:500; color:#e2e8f0;'>{m['away_team']}</div>",
        unsafe_allow_html=True
    )

    # Liga
    cols[3].markdown(
        f"<div style='font-size:0.82rem; color:#94a3b8;'>{m['league']}</div>",
        unsafe_allow_html=True
    )

    # % GG acasă
    h_col = color_cell(m["gg_home"])
    cols[4].markdown(
        f"<div style='font-size:1.05rem; font-weight:700; color:{h_col};'>{m['gg_home']}%</div>"
        f"<div class='prob-bar-container'><div class='prob-bar' style='width:{m['gg_home']}%; background:{prob_color(m['gg_home'])};'></div></div>",
        unsafe_allow_html=True
    )

    # % GG deplasare
    a_col = color_cell(m["gg_away"])
    cols[5].markdown(
        f"<div style='font-size:1.05rem; font-weight:700; color:{a_col};'>{m['gg_away']}%</div>"
        f"<div class='prob-bar-container'><div class='prob-bar' style='width:{m['gg_away']}%; background:{prob_color(m['gg_away'])};'></div></div>",
        unsafe_allow_html=True
    )

    # Probabilitate combinată
    c_col = color_cell(m["combined"])
    prob_bg = "rgba(56,189,248,0.12)" if rec else "rgba(255,255,255,0.04)"
    cols[6].markdown(
        f"<div style='text-align:center; background:{prob_bg}; border-radius:10px; padding:6px 4px;'>"
        f"<span style='font-size:1.15rem; font-weight:800; color:{c_col};'>{m['combined']}%</span>"
        f"</div>",
        unsafe_allow_html=True
    )

    if i < len(sorted_matches) - 1:
        st.markdown(
            '<hr style="border-top:1px solid rgba(255,255,255,0.04); margin:0.5rem 0;">',
            unsafe_allow_html=True
        )

# ─────────────────────────────────────────────
# SECȚIUNEA RECOMANDĂRI ZILEI
# ─────────────────────────────────────────────

recomandate_list = [m for m in sorted_matches if m["is_recommended"]]

if recomandate_list:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:1.15rem; font-weight:700; color:#e2e8f0; margin-bottom:1rem;">
        🔥 Recomandările Zilei <span style="font-size:0.8rem; color:#94a3b8; font-weight:400;">(probabilitate &gt;{}%)</span>
    </div>
    """.format(int(THRESHOLD_GG)), unsafe_allow_html=True)

    for m in recomandate_list:
        st.markdown(f"""
        <div class="recommendation-card">
            <div>
                <div class="teams">🏠 {m['home_team']} <span style="color:#64748b; font-weight:400;">vs</span> {m['away_team']} ✈️</div>
                <div class="league">🏆 {m['league']} &nbsp;·&nbsp; 🕐 {m['time']}</div>
                <div style="margin-top:0.5rem; font-size:0.8rem; color:#64748b;">
                    Acasă: <strong style="color:#38bdf8;">{m['gg_home']}%</strong> GG &nbsp;·&nbsp;
                    Deplasare: <strong style="color:#818cf8;">{m['gg_away']}%</strong> GG
                </div>
            </div>
            <div class="prob-circle">{m['combined']}%</div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align:center; padding:2rem; color:#64748b;">
        <div style="font-size:2rem;">🤔</div>
        <div style="margin-top:0.5rem;">Niciun meci nu depășește pragul de {}% astăzi.</div>
    </div>
    """.format(int(THRESHOLD_GG)), unsafe_allow_html=True)

# ─────────────────────────────────────────────
# NOTĂ METODOLOGICĂ
# ─────────────────────────────────────────────

st.markdown('<hr class="divider">', unsafe_allow_html=True)

with st.expander("📐 Metodologie de calcul"):
    st.markdown(f"""
    **Cum se calculează probabilitatea GG?**

    1. **Date colectate**: Ultimele **{NUM_RECENT_MATCHES} meciuri** disputate de fiecare echipă (indiferent de teren).
    2. **% GG echipă**: număr meciuri în care echipa a marcat ȘI a primit gol ÷ total meciuri × 100.
    3. **Probabilitate combinată**: media aritmetică dintre % GG al echipei gazdă și % GG al echipei oaspete.
    4. **Recomandare**: meciurile cu probabilitate combinată **≥ {int(THRESHOLD_GG)}%** sunt marcate ca recomandări.

    **Sursă date**: [TheSportsDB](https://www.thesportsdb.com/) – API public și gratuit.
    """)

# Footer
st.markdown(f"""
<div class="footer-note">
    ⚠️ <strong>Notă importantă:</strong> Datele și procentajele afișate au caracter exclusiv statistic și informativ,
    bazate pe istoricul recent al echipelor. Ele <strong>nu reprezintă o garanție de câștig</strong> și nu
    constituie sfaturi de pariuri. Parierile implică riscuri financiare semnificative. Jucați responsabil.
    Vârsta minimă legală pentru pariuri sportive în România este de <strong>18 ani</strong>.
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div style="text-align:center; padding:1.5rem 0 0.5rem; color:#334155; font-size:0.75rem;">
    GG Bet Analyzer · Date actualizate la fiecare 30 de minute · Powered by TheSportsDB API
</div>
""", unsafe_allow_html=True)
