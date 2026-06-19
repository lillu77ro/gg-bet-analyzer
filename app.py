"""
GG Bet Analyzer – Analiză statistică pentru piața „Ambele echipe marchează"
Surse date:
  - TheSportsDB (gratuit, fără cheie, nelimitat) → meciuri + istoric GG
Features: GG% Acasă/Deplasare split, Medie goluri/meci, Niveluri Gold/Silver/Bronze
"""

import streamlit as st
import requests
from datetime import date, datetime, timezone, timedelta
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
.metric-card .value { font-size: 2.2rem; font-weight: 800; }
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

.badge-gold {
    background: linear-gradient(90deg, #f59e0b, #ef4444);
    color: white; font-size: 0.65rem; font-weight: 700;
    padding: 2px 8px; border-radius: 999px; text-transform: uppercase;
    display: inline-block; margin-left: 4px;
}
.badge-silver {
    background: linear-gradient(90deg, #94a3b8, #64748b);
    color: white; font-size: 0.65rem; font-weight: 700;
    padding: 2px 8px; border-radius: 999px; text-transform: uppercase;
    display: inline-block; margin-left: 4px;
}
.badge-bronze {
    background: linear-gradient(90deg, #b45309, #92400e);
    color: white; font-size: 0.65rem; font-weight: 700;
    padding: 2px 8px; border-radius: 999px; text-transform: uppercase;
    display: inline-block; margin-left: 4px;
}
.stat-mini {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px; padding: 4px 10px;
    font-size: 0.72rem; color: #64748b;
    display: inline-block; margin: 2px 3px 2px 0;
}
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
SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"
THRESHOLD_GG  = 75.0   # % minim pentru recomandare
NUM_MATCHES   = 15      # ultimele N meciuri per echipă
MAX_MATCHES   = 25      # max meciuri de azi
RO_TZ         = timezone(timedelta(hours=3))

EXCLUDE_WORDS = ["Women", " W ", "Youth", "U20", "U21", "U23",
                 "Reserve", "Friendly", "Beach", "Futsal", "Indoor"]

# ─────────────────────────────────────────────
# FUNCȚII HTTP
# ─────────────────────────────────────────────

def sportsdb_get(endpoint):
    try:
        r = requests.get(f"{SPORTSDB_BASE}{endpoint}", timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# ─────────────────────────────────────────────
# FUNCȚII DATE
# ─────────────────────────────────────────────

def fetch_todays_fixtures():
    today = date.today().strftime("%Y-%m-%d")
    data = sportsdb_get(f"/eventsday.php?d={today}&s=Soccer")
    if not data or not data.get("events"):
        return []

    fixtures = []
    for ev in data["events"]:
        if ev.get("intHomeScore") not in (None, ""):
            continue
        league_name = ev.get("strLeague", "") or ""
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
                dt = datetime.strptime(
                    f"{date_raw} {time_raw[:8]}", "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
                time_str = dt.astimezone(RO_TZ).strftime("%H:%M")
            except Exception:
                time_str = time_raw[:5] if len(time_raw) >= 5 else "N/A"

        fixtures.append({
            "fixture_id":   ev.get("idEvent", ""),
            "home_team":    ev.get("strHomeTeam", "N/A"),
            "away_team":    ev.get("strAwayTeam", "N/A"),
            "home_team_id": home_id,
            "away_team_id": away_id,
            "league":       league_name,
            "country":      ev.get("strCountry", ""),
            "time":         time_str,
            "timestamp":    f"{date_raw}T{time_raw}" if time_raw else date_raw,
        })

    return sorted(fixtures, key=lambda x: x["timestamp"])[:MAX_MATCHES]


def fetch_team_last_matches(team_id):
    data = sportsdb_get(f"/eventslast.php?id={team_id}")
    if not data or not data.get("results"):
        return []
    return data["results"][:NUM_MATCHES]


def calc_stats(events, team_id):
    """
    Calculează statistici complete:
    - GG% total, acasă, deplasare
    - Medie goluri/meci
    - Formă ultimele 5 meciuri (GG sau nu)
    """
    home_gg, home_total = 0, 0
    away_gg, away_total = 0, 0
    all_gg,  all_total  = 0, 0
    total_goals = 0
    form_5 = []   # True = GG, False = no GG (ultimele 5, cronologic desc)

    for ev in events:
        h = ev.get("intHomeScore")
        a = ev.get("intAwayScore")
        if h is None or a is None or h == "" or a == "":
            continue
        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            continue

        gg_in_match = h > 0 and a > 0
        all_total  += 1
        total_goals += h + a
        if gg_in_match:
            all_gg += 1

        # Formă ultimele 5
        if len(form_5) < 5:
            form_5.append(gg_in_match)

        # Determină dacă echipa a jucat acasă sau deplasare
        is_home = str(ev.get("idHomeTeam", "")) == str(team_id)
        if is_home:
            home_total += 1
            if gg_in_match:
                home_gg += 1
        else:
            away_total += 1
            if gg_in_match:
                away_gg += 1

    return {
        "gg_all":    round((all_gg  / all_total)  * 100, 1) if all_total  else 0.0,
        "gg_home":   round((home_gg / home_total) * 100, 1) if home_total else 0.0,
        "gg_away":   round((away_gg / away_total) * 100, 1) if away_total else 0.0,
        "avg_goals": round(total_goals / all_total, 2)       if all_total  else 0.0,
        "total_m":   all_total,
        "home_m":    home_total,
        "away_m":    away_total,
        "form_5":    form_5,
    }


def confidence_level(pct):
    """Returnează nivelul de încredere bazat pe probabilitate."""
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

    home_stats = calc_stats(home_events, match["home_team_id"])
    away_stats = calc_stats(away_events, match["away_team_id"])

    # GG% Acasă pentru echipa gazdă, GG% Deplasare pentru echipa oaspete
    # (cel mai precis calcul pentru context real al meciului)
    gg_home_ctx = home_stats["gg_home"] if home_stats["home_m"] >= 3 else home_stats["gg_all"]
    gg_away_ctx = away_stats["gg_away"] if away_stats["away_m"] >= 3 else away_stats["gg_all"]
    combined    = round((gg_home_ctx + gg_away_ctx) / 2, 1)

    level, label, color = confidence_level(combined)

    return {
        **match,
        "gg_home_ctx":  gg_home_ctx,
        "gg_away_ctx":  gg_away_ctx,
        "combined":     combined,
        "conf_level":   level,
        "conf_label":   label,
        "conf_color":   color,
        "is_recommended": combined >= THRESHOLD_GG,
        # Stats complete pentru detalii
        "home_stats":   home_stats,
        "away_stats":   away_stats,
        "home_injured": [],
        "away_injured": [],
    }

# ─────────────────────────────────────────────
# DATE DEMO
# ─────────────────────────────────────────────
def demo_data():
    def mk(fid, ht, at, lg, ti, ghc, gac, comb, hi, ai):
        lvl, lbl, col = confidence_level(comb)
        return {
            "fixture_id": fid, "home_team": ht, "away_team": at,
            "league": lg, "country": "", "time": ti,
            "gg_home_ctx": ghc, "gg_away_ctx": gac, "combined": comb,
            "conf_level": lvl, "conf_label": lbl, "conf_color": col,
            "is_recommended": comb >= THRESHOLD_GG,
            "home_stats": {
                "gg_all": ghc, "gg_home": ghc, "gg_away": ghc,
                "avg_goals": 2.8, "total_m": 10, "home_m": 5, "away_m": 5,
                "form_5": [True, True, True, False, True]
            },
            "away_stats": {
                "gg_all": gac, "gg_home": gac, "gg_away": gac,
                "avg_goals": 2.4, "total_m": 10, "home_m": 5, "away_m": 5,
                "form_5": [True, False, True, True, True]
            },
            "home_injured": hi, "away_injured": ai,
        }
    return [
        mk("1","Inter Milan","AC Milan","Serie A","20:45",
           88.0,84.0,86.0,
           [{"name":"Lautaro","reason":"Muscle","type":"Injured"}],[]),
        mk("2","Bayern München","Borussia Dortmund","Bundesliga","20:30",
           90.0,80.0,85.0,[],[{"name":"Reus","reason":"Cards","type":"Suspended"}]),
        mk("3","Manchester City","Arsenal","Premier League","18:30",
           82.0,76.0,79.0,[],[]),
        mk("4","PSG","Lyon","Ligue 1","19:00",
           78.0,72.0,75.0,[],[]),
        mk("5","Real Madrid","Atletico Madrid","La Liga","21:00",
           70.0,60.0,65.0,[],[]),
        mk("6","Feyenoord","Ajax","Eredivisie","17:45",
           80.0,90.0,85.0,[],[]),
    ]

# ─────────────────────────────────────────────
# HELPER UI
# ─────────────────────────────────────────────

def prob_gradient(val):
    if val >= 85:
        return "linear-gradient(90deg,#f59e0b,#ef4444)"
    elif val >= 75:
        return "linear-gradient(90deg,#38bdf8,#818cf8)"
    elif val >= 65:
        return "linear-gradient(90deg,#b45309,#92400e)"
    return "linear-gradient(90deg,#64748b,#94a3b8)"


def val_color(val):
    if val >= 85:
        return "#f59e0b"
    elif val >= 75:
        return "#38bdf8"
    elif val >= 65:
        return "#cd7c2f"
    return "#94a3b8"


def form_html(form_5):
    """Generează indicatoare de formă (ultimele 5 meciuri)."""
    if not form_5:
        return ""
    dots = ""
    for gg in form_5:
        color = "#34d399" if gg else "#f87171"
        title = "GG ✓" if gg else "No GG ✗"
        dots += (
            f"<span title='{title}' style='display:inline-block;width:10px;height:10px;"
            f"border-radius:50%;background:{color};margin:0 2px;'></span>"
        )
    return f"<span style='font-size:0.7rem;color:#64748b;margin-right:4px;'>Form:</span>{dots}"

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
months_ro = {
    "January":"Ianuarie","February":"Februarie","March":"Martie",
    "April":"Aprilie","May":"Mai","June":"Iunie",
    "July":"Iulie","August":"August","September":"Septembrie",
    "October":"Octombrie","November":"Noiembrie","December":"Decembrie",
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


with st.spinner("⏳ Se preiau meciurile și se calculează statisticile GG..."):
    matches, is_demo = load_all_data()

if is_demo:
    st.info(
        "ℹ️ **Mod demonstrativ** — Nu există meciuri programate astăzi "
        "(posibil pauză competițională). Datele afișate sunt exemple statistice realiste.",
    )

# ─────────────────────────────────────────────
# STATISTICI SUMAR
# ─────────────────────────────────────────────
total     = len(matches)
gold_cnt  = sum(1 for m in matches if m["conf_level"] == "gold")
silver_cnt= sum(1 for m in matches if m["conf_level"] == "silver")
bronze_cnt= sum(1 for m in matches if m["conf_level"] == "bronze")
avg_comb  = round(sum(m["combined"] for m in matches) / total, 1) if total else 0.0
max_comb  = max((m["combined"] for m in matches), default=0.0)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

c1,c2,c3,c4,c5 = st.columns(5)
cards = [
    (c1, str(total),        "Meciuri analizate",    "#38bdf8"),
    (c2, f"🥇 {gold_cnt}",  "Gold (≥85%)",          "#f59e0b"),
    (c3, f"🥈 {silver_cnt}","Silver (75-85%)",      "#94a3b8"),
    (c4, f"🥉 {bronze_cnt}","Bronze (65-75%)",      "#b45309"),
    (c5, f"{avg_comb}%",    "Probabilitate medie",  "#a78bfa"),
]
for col, val, label, color in cards:
    col.markdown(
        f"<div class='metric-card'>"
        f"<div class='value' style='color:{color};'>{val}</div>"
        f"<div class='label'>{label}</div>"
        f"</div>", unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# TABEL PRINCIPAL
# ─────────────────────────────────────────────
sorted_matches = sorted(
    matches,
    key=lambda x: (
        0 if x["conf_level"]=="gold" else 1 if x["conf_level"]=="silver"
        else 2 if x["conf_level"]=="bronze" else 3,
        -x["combined"]
    )
)

st.markdown(
    "<div style='font-size:1.15rem;font-weight:700;color:#e2e8f0;margin-bottom:1rem;'>"
    "📊 Analiza Meciurilor Zilei</div>",
    unsafe_allow_html=True)

h_cols = st.columns([0.7, 1.9, 1.9, 1.8, 1.5, 1.5, 1.5])
for col, h in zip(h_cols, ["🕐 Ora","🏟️ Gazdă","✈️ Oaspete","🏆 Liga",
                             "🏠 GG Acasă","✈️ GG Depl.","📈 Prob."]):
    col.markdown(
        f"<span style='font-size:0.7rem;color:#64748b;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:0.06em;'>{h}</span>",
        unsafe_allow_html=True)
st.markdown(
    '<hr style="border-top:1px solid rgba(255,255,255,0.06);margin:0.3rem 0 0.6rem;">',
    unsafe_allow_html=True)

for i, m in enumerate(sorted_matches):
    lvl   = m["conf_level"]
    comb  = m["combined"]
    hs    = m["home_stats"]
    as_   = m["away_stats"]

    border = (
        "border-left:3px solid #f59e0b;" if lvl == "gold" else
        "border-left:3px solid #94a3b8;" if lvl == "silver" else
        "border-left:3px solid #b45309;" if lvl == "bronze" else
        "border-left:3px solid transparent;"
    )
    badge_html = (
        f'<span class="badge-{lvl}">{m["conf_label"]}</span>'
        if lvl != "none" else ""
    )

    cols = st.columns([0.7, 1.9, 1.9, 1.8, 1.5, 1.5, 1.5])

    cols[0].markdown(
        f"<div style='{border}padding-left:8px;font-weight:600;color:#cbd5e1;'>"
        f"{m['time']}</div>", unsafe_allow_html=True)

    # Echipa gazdă + badge + avg goals + formă
    h_form = form_html(hs.get("form_5", []))
    cols[1].markdown(
        f"<div style='font-weight:700;color:#f1f5f9;'>{m['home_team']} {badge_html}</div>"
        f"<div style='margin-top:3px;'>{h_form}"
        f"<span class='stat-mini'>⚽ {hs['avg_goals']} gol/meci</span></div>",
        unsafe_allow_html=True)

    # Echipa oaspete + avg goals + formă
    a_form = form_html(as_.get("form_5", []))
    cols[2].markdown(
        f"<div style='font-weight:500;color:#e2e8f0;'>{m['away_team']}</div>"
        f"<div style='margin-top:3px;'>{a_form}"
        f"<span class='stat-mini'>⚽ {as_['avg_goals']} gol/meci</span></div>",
        unsafe_allow_html=True)

    cols[3].markdown(
        f"<div style='font-size:0.8rem;color:#94a3b8;'>{m['league']}</div>"
        f"<div style='font-size:0.7rem;color:#475569;margin-top:2px;'>{m['country']}</div>",
        unsafe_allow_html=True)

    # GG% Acasă (contextual)
    gg_h = m["gg_home_ctx"]
    cols[4].markdown(
        f"<div style='font-size:1.05rem;font-weight:700;color:{val_color(gg_h)};'>{gg_h}%</div>"
        f"<div class='prob-bar-container'>"
        f"<div class='prob-bar' style='width:{gg_h}%;background:{prob_gradient(gg_h)};'></div>"
        f"</div>"
        f"<div style='font-size:0.68rem;color:#475569;margin-top:2px;'>"
        f"({hs['home_m']} meci acasă)</div>",
        unsafe_allow_html=True)

    # GG% Deplasare (contextual)
    gg_a = m["gg_away_ctx"]
    cols[5].markdown(
        f"<div style='font-size:1.05rem;font-weight:700;color:{val_color(gg_a)};'>{gg_a}%</div>"
        f"<div class='prob-bar-container'>"
        f"<div class='prob-bar' style='width:{gg_a}%;background:{prob_gradient(gg_a)};'></div>"
        f"</div>"
        f"<div style='font-size:0.68rem;color:#475569;margin-top:2px;'>"
        f"({as_['away_m']} meci depl.)</div>",
        unsafe_allow_html=True)

    # Probabilitate combinată
    prob_bg = (
        "rgba(245,158,11,0.12)" if lvl=="gold" else
        "rgba(56,189,248,0.10)" if lvl=="silver" else
        "rgba(180,83,9,0.10)"   if lvl=="bronze" else
        "rgba(255,255,255,0.04)"
    )
    conf_color = m["conf_color"]
    cols[6].markdown(
        f"<div style='text-align:center;background:{prob_bg};"
        f"border-radius:10px;padding:6px 4px;'>"
        f"<span style='font-size:1.15rem;font-weight:800;color:{conf_color};'>"
        f"{comb}%</span></div>",
        unsafe_allow_html=True)

    # Detalii extins
    with st.expander(f"📊 Statistici detaliate: {m['home_team']} vs {m['away_team']}"):
        dc1, dc2 = st.columns(2)
        with dc1:
            st.markdown(
                f"<div style='font-weight:700;color:#38bdf8;margin-bottom:8px;'>"
                f"🏠 {m['home_team']}</div>"
                f"<div style='font-size:0.82rem;color:#94a3b8;line-height:1.8;'>"
                f"GG% Total: <strong style='color:#e2e8f0;'>{hs['gg_all']}%</strong><br>"
                f"GG% Acasă: <strong style='color:#34d399;'>{hs['gg_home']}%</strong>"
                f" ({hs['home_m']} meciuri)<br>"
                f"GG% Deplasare: <strong style='color:#f87171;'>{hs['gg_away']}%</strong>"
                f" ({hs['away_m']} meciuri)<br>"
                f"Medie goluri/meci: <strong style='color:#f59e0b;'>{hs['avg_goals']}</strong>"
                f"</div>",
                unsafe_allow_html=True)
        with dc2:
            st.markdown(
                f"<div style='font-weight:700;color:#818cf8;margin-bottom:8px;'>"
                f"✈️ {m['away_team']}</div>"
                f"<div style='font-size:0.82rem;color:#94a3b8;line-height:1.8;'>"
                f"GG% Total: <strong style='color:#e2e8f0;'>{as_['gg_all']}%</strong><br>"
                f"GG% Acasă: <strong style='color:#34d399;'>{as_['gg_home']}%</strong>"
                f" ({as_['home_m']} meciuri)<br>"
                f"GG% Deplasare: <strong style='color:#f87171;'>{as_['gg_away']}%</strong>"
                f" ({as_['away_m']} meciuri)<br>"
                f"Medie goluri/meci: <strong style='color:#f59e0b;'>{as_['avg_goals']}</strong>"
                f"</div>",
                unsafe_allow_html=True)

    if i < len(sorted_matches) - 1:
        st.markdown(
            '<hr style="border-top:1px solid rgba(255,255,255,0.04);margin:0.5rem 0;">',
            unsafe_allow_html=True)

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
        home_t   = m["home_team"]
        away_t   = m["away_team"]
        league_n = m["league"]
        time_n   = m["time"]
        gg_h     = m["gg_home_ctx"]
        gg_a     = m["gg_away_ctx"]
        avg_h    = m["home_stats"]["avg_goals"]
        avg_a    = m["away_stats"]["avg_goals"]
        lvl      = m["conf_level"]

        border_color = "#f59e0b" if lvl=="gold" else "#94a3b8"
        bg_color = (
            "rgba(245,158,11,0.08),rgba(239,68,68,0.06)"
            if lvl=="gold" else
            "rgba(56,189,248,0.08),rgba(129,140,248,0.08)"
        )

        col_info, col_prob = st.columns([5, 1])
        with col_info:
            st.markdown(
                f"<div style='background:linear-gradient(135deg,{bg_color});"
                f"border:1px solid {border_color}40;"
                f"border-radius:16px;padding:1.2rem 1.5rem;'>"
                f"<div style='font-size:1.05rem;font-weight:700;color:#e2e8f0;'>"
                f"{m['conf_label']} &nbsp; 🏠 {home_t} "
                f"<span style='color:#64748b;font-weight:400;'>vs</span>"
                f" {away_t} ✈️</div>"
                f"<div style='font-size:0.8rem;color:#94a3b8;margin-top:2px;'>"
                f"🏆 {league_n} &nbsp;·&nbsp; 🕐 {time_n}</div>"
                f"<div style='margin-top:0.5rem;font-size:0.82rem;color:#64748b;'>"
                f"GG Acasă: <strong style='color:#38bdf8;'>{gg_h}%</strong>"
                f" &nbsp;·&nbsp; "
                f"GG Deplasare: <strong style='color:#818cf8;'>{gg_a}%</strong>"
                f" &nbsp;·&nbsp; "
                f"Medie goluri: <strong style='color:#f59e0b;'>"
                f"{round((avg_h+avg_a)/2,1)}/meci</strong></div>"
                f"</div>",
                unsafe_allow_html=True)
        with col_prob:
            circ_bg = (
                "linear-gradient(135deg,#f59e0b,#ef4444)" if lvl=="gold"
                else "linear-gradient(135deg,#38bdf8,#818cf8)"
            )
            st.markdown(
                f"<div style='text-align:center;background:{circ_bg};"
                f"border-radius:50%;width:60px;height:60px;"
                f"display:flex;align-items:center;justify-content:center;"
                f"font-size:0.9rem;font-weight:800;color:white;margin:auto;'>"
                f"{comb}%</div>",
                unsafe_allow_html=True)
else:
    st.markdown(
        f"<div style='text-align:center;padding:2rem;color:#64748b;'>"
        f"<div style='font-size:2rem;'>🤔</div>"
        f"<div style='margin-top:0.5rem;'>Niciun meci nu depășește pragul de "
        f"{int(THRESHOLD_GG)}% astăzi.</div></div>",
        unsafe_allow_html=True)

# ─────────────────────────────────────────────
# LEGENDĂ NIVELURI
# ─────────────────────────────────────────────
st.markdown('<hr class="divider">', unsafe_allow_html=True)
with st.expander("📐 Metodologie & Legendă niveluri"):
    st.markdown(f"""
**Niveluri de încredere:**
| Nivel | Probabilitate | Semnificație |
|---|---|---|
| 🥇 **Gold** | ≥ 85% | Probabilitate ridicată — ambele echipe marchează în majorit. meciurilor |
| 🥈 **Silver** | 75–85% | Probabilitate bună — recomandat pentru analiză |
| 🥉 **Bronze** | 65–75% | Probabilitate medie — merită atenție |

**Cum se calculează:**
1. Preluăm ultimele **{NUM_MATCHES} meciuri** ale fiecărei echipe din TheSportsDB.
2. Calculăm **GG% contextual**: pentru echipa gazdă folosim GG% *acasă*, pentru oaspete folosim GG% *deplasare*.
3. **Probabilitate combinată** = media celor două valori contextuale.
4. Afișăm **media goluri/meci** și **forma ultimelor 5 meciuri** (🟢 GG / 🔴 No GG).

**Sursă date**: [TheSportsDB](https://www.thesportsdb.com/) — 100% gratuit, fără limite.
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
    GG Bet Analyzer · Powered by TheSportsDB · Date actualizate la fiecare 12 ore
</div>
""", unsafe_allow_html=True)
