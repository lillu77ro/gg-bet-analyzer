"""
NORD ALLASKA SUPREME — VALUE BET SCANNER
Surse: API-Football PRO + Betano + Superbet
Metodologie: Expected Value (EV) = Prob. Reală - Prob. Implicită
Cote: 1.75 — 3.00 | EV minim: 5%
"""

import streamlit as st
import requests
from datetime import date, datetime, timezone, timedelta

# ─────────────────────────────────────────────
# CONFIGURARE PAGINĂ
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="NORD ALLASKA SUPREME",
    page_icon="🏔️",
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
.footer-note{ background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.2);
    border-radius:12px; padding:1rem 1.4rem; margin-top:2rem;
    font-size:0.82rem; color:#fca5a5; line-height:1.6; }
#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONSTANTE
# ─────────────────────────────────────────────
API_KEY = "281e7a0cf284eeba705e2ae11f3d7722"
API_BASE = "https://v3.football.api-sports.io"
API_HEADERS = {"x-apisports-key": API_KEY}

BETANO_ID = 32
SUPERBET_ID = 34
MIN_ODDS = 1.75
MAX_ODDS = 3.00
MIN_EV = 5.0
PROB_DISCOUNT = 0.95  # 5% conservative discount — balanced
NUM_MATCHES = 15
NUM_H2H = 10
MIN_DATA_MATCHES = 8  # minim 8 meciuri
RO_TZ = timezone(timedelta(hours=3))

EXCLUDE_WORDS = ["Women","Youth","U17","U19","U20","U21","U23",
                 "Reserve","Friendly","Friendlies","Beach","Futsal","Indoor",
                 "Esports","eSports","Cyber","Damallsvenskan","Toppserien",
                 "NWSL","Frauen","Femminile","Femenina","Feminina"]

# Also filter team names (catch " W" suffix)
EXCLUDE_TEAM_SUFFIXES = [" W", " Women", " Ladies", " Femenino", " Femminile", " Frauen"]

# ALL supported betting markets
SUPPORTED_BETS = {"Match Winner","Both Teams Score","Goals Over/Under",
                  "Double Chance","Home/Away","Goals Over/Under First Half",
                  "Goals Over/Under Second Half","Second Half Winner",
                  "First Half Winner","Asian Handicap","Total - Home",
                  "Total - Away","Clean Sheet - Home",
                  "Clean Sheet - Away","Win to Nil - Home","Win to Nil - Away",
                  "Total Cards","Total Cards - Home","Total Cards - Away",
                  "Results/Both Teams Score","To Score in Both Halves",
                  "Highest Scoring Half","Both Teams Score - First Half",
                  "Both Teams To Score - Second Half"}

# Asian Handicap ONLY from Betano (Superbet AH odds are broken!)
AH_BLOCKED_BOOKMAKERS = {"Superbet"}

# ─────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────
def api_get(endpoint, params=None):
    try:
        r = requests.get(f"{API_BASE}{endpoint}", headers=API_HEADERS, params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("response", [])
    except Exception:
        return []

def api_get_paged(endpoint, params=None):
    if params is None:
        params = {}
    params["page"] = 1
    all_results = []
    try:
        r = requests.get(f"{API_BASE}{endpoint}", headers=API_HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        all_results.extend(data.get("response", []))
        total_pages = data.get("paging", {}).get("total", 1)
        for page in range(2, min(total_pages + 1, 21)):
            params["page"] = page
            r2 = requests.get(f"{API_BASE}{endpoint}", headers=API_HEADERS, params=params, timeout=30)
            r2.raise_for_status()
            all_results.extend(r2.json().get("response", []))
    except Exception:
        pass
    return all_results

# ─────────────────────────────────────────────
# FETCH DATA
# ─────────────────────────────────────────────
def fetch_fixtures(target_date):
    events = api_get("/fixtures", {"date": target_date})
    fixtures = []
    for ev in events:
        fix = ev.get("fixture", {})
        teams = ev.get("teams", {})
        league = ev.get("league", {})
        if fix.get("status", {}).get("short") != "NS":
            continue
        ln = league.get("name", "")
        if any(w in ln for w in EXCLUDE_WORDS):
            continue
        hid = teams.get("home", {}).get("id")
        aid = teams.get("away", {}).get("id")
        if not hid or not aid:
            continue
        # Filter Women/Youth teams by name
        h_name = teams.get("home", {}).get("name", "")
        a_name = teams.get("away", {}).get("name", "")
        if any(h_name.endswith(s) or a_name.endswith(s) for s in EXCLUDE_TEAM_SUFFIXES):
            continue
        dt_str = fix.get("date", "")
        time_str = "N/A"
        if dt_str:
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                time_str = dt.astimezone(RO_TZ).strftime("%H:%M")
            except Exception:
                time_str = dt_str[11:16] if len(dt_str) > 16 else "N/A"
        fixtures.append({"fixture_id": fix.get("id"), "home_team": teams["home"]["name"],
            "away_team": teams["away"]["name"], "home_id": hid, "away_id": aid,
            "league": ln, "country": league.get("country", ""), "time": time_str, "timestamp": dt_str,
            "league_id": league.get("id"), "season": league.get("season"),
            "referee": fix.get("referee", "")})
    return sorted(fixtures, key=lambda x: x["timestamp"])

def fetch_odds_bulk(target_date, bookmaker_id):
    results = api_get_paged("/odds", {"date": target_date, "bookmaker": bookmaker_id})
    odds_map = {}
    for item in results:
        fid = item.get("fixture", {}).get("id")
        if not fid:
            continue
        bks = item.get("bookmakers", [])
        if bks:
            odds_map[fid] = bks[0].get("bets", [])
    return odds_map

def fetch_team_matches(team_id):
    events = api_get("/fixtures", {"team": team_id, "last": NUM_MATCHES})
    results = []
    for ev in events:
        t = ev.get("teams", {})
        g = ev.get("goals", {})
        gh, ga = g.get("home"), g.get("away")
        if gh is None or ga is None:
            continue
        results.append({"home_id": t.get("home", {}).get("id"), "away_id": t.get("away", {}).get("id"),
                        "home_goals": int(gh), "away_goals": int(ga)})
    return results

def fetch_team_cards(team_id, league_id, season):
    """Fetch card statistics for a team in a specific league/season."""
    if not league_id or not season:
        return None
    data = api_get("/teams/statistics", {"team": team_id, "league": league_id, "season": season})
    if not data:
        return None
    if isinstance(data, list):
        return None
    cards = data.get("cards", {})
    fixtures = data.get("fixtures", {})
    total_played = fixtures.get("played", {}).get("total", 0)
    if total_played == 0:
        return None
    total_yellow = 0
    total_red = 0
    for period in cards.get("yellow", {}).values():
        if isinstance(period, dict) and period.get("total"):
            total_yellow += period["total"]
    for period in cards.get("red", {}).values():
        if isinstance(period, dict) and period.get("total"):
            total_red += period["total"]
    total_cards = total_yellow + total_red
    avg_cards = round(total_cards / total_played, 2)
    return {"total_cards": total_cards, "total_yellow": total_yellow, "total_red": total_red,
            "matches": total_played, "avg_cards": avg_cards}

def fetch_h2h(home_id, away_id):
    events = api_get("/fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": NUM_H2H})
    results = []
    for ev in events:
        t = ev.get("teams", {})
        g = ev.get("goals", {})
        gh, ga = g.get("home"), g.get("away")
        if gh is None or ga is None:
            continue
        results.append({"home_id": t.get("home", {}).get("id"), "away_id": t.get("away", {}).get("id"),
                        "home_goals": int(gh), "away_goals": int(ga)})
    return results

def fetch_injuries(fixture_id):
    """Fetch injured/suspended players for a fixture."""
    data = api_get("/injuries", {"fixture": fixture_id})
    home_inj = []
    away_inj = []
    for item in data:
        player = item.get("player", {})
        team = item.get("team", {})
        info = {"name": player.get("name", "?"), "reason": player.get("reason", "?")}
        if item.get("team", {}).get("id"):
            # We'll sort by team later
            home_inj.append(info)  # placeholder, sorted in main logic
    return data

def fetch_standings(league_id, season):
    """Fetch league standings to determine team positions."""
    data = api_get("/standings", {"league": league_id, "season": season})
    if not data:
        return {}
    standings = {}
    league_data = data[0].get("league", {}).get("standings", [[]])
    for group in league_data:
        for team in group:
            tid = team.get("team", {}).get("id")
            if tid:
                standings[tid] = {
                    "rank": team.get("rank", 0),
                    "points": team.get("points", 0),
                    "total_teams": len(group),
                    "form": team.get("form", ""),
                    "gd": team.get("goalsDiff", 0),
                }
    return standings

def calc_rest_days(team_events):
    """Calculate average days between matches from recent fixtures."""
    if len(team_events) < 2:
        return None
    # We don't have dates in our simplified events, so we estimate
    # from the number of matches in NUM_MATCHES window
    # Average team plays ~2 matches/week = 3.5 days rest
    return 3.5  # default estimation

def adjust_probs(probs, home_id, away_id, fixture_id, league_id, season, standings_cache):
    """Adjust probabilities based on injuries, standings, and context."""
    adjustments = []

    # --- INJURIES ---
    inj_data = fetch_injuries(fixture_id)
    home_injuries = [i for i in inj_data if i.get("team", {}).get("id") == home_id]
    away_injuries = [i for i in inj_data if i.get("team", {}).get("id") == away_id]
    n_home_inj = len(home_injuries)
    n_away_inj = len(away_injuries)

    # Each injury reduces team strength by ~2-3%
    if n_home_inj >= 3:
        probs["home"] = max(probs["home"] - (n_home_inj * 2.5), 5)
        probs["away"] = min(probs["away"] + (n_home_inj * 1.5), 80)
        adjustments.append(f"⚕️ Gazdă: {n_home_inj} accidentați (-{n_home_inj*2.5:.0f}%)")
    if n_away_inj >= 3:
        probs["away"] = max(probs["away"] - (n_away_inj * 2.5), 5)
        probs["home"] = min(probs["home"] + (n_away_inj * 1.5), 80)
        adjustments.append(f"⚕️ Oaspete: {n_away_inj} accidentați (-{n_away_inj*2.5:.0f}%)")

    # --- STANDINGS ---
    if league_id and season:
        cache_key = f"{league_id}_{season}"
        if cache_key not in standings_cache:
            standings_cache[cache_key] = fetch_standings(league_id, season)
        standings = standings_cache[cache_key]

        h_pos = standings.get(home_id, {})
        a_pos = standings.get(away_id, {})

        if h_pos and a_pos:
            h_rank = h_pos.get("rank", 0)
            a_rank = a_pos.get("rank", 0)
            total_t = h_pos.get("total_teams", 20)

            # Big rank difference = adjust 1X2
            if h_rank > 0 and a_rank > 0:
                rank_diff = a_rank - h_rank  # positive = home is higher ranked
                if abs(rank_diff) >= 8:
                    adj = min(abs(rank_diff) * 0.5, 8)
                    if rank_diff > 0:  # home better
                        probs["home"] = min(probs["home"] + adj, 85)
                        probs["away"] = max(probs["away"] - adj, 3)
                        adjustments.append(f"📊 Gazdă #{h_rank} vs Oaspete #{a_rank} (+{adj:.0f}%)")
                    else:  # away better
                        probs["away"] = min(probs["away"] + adj, 75)
                        probs["home"] = max(probs["home"] - adj, 5)
                        adjustments.append(f"📊 Gazdă #{h_rank} vs Oaspete #{a_rank} (-{adj:.0f}%)")

                # Relegation battle = more defensive = less goals
                if h_rank >= total_t - 3 or a_rank >= total_t - 3:
                    probs["over25"] = max(probs["over25"] - 5, 10)
                    probs["under25"] = min(probs["under25"] + 5, 90)
                    probs["gg"] = max(probs["gg"] - 3, 10)
                    adjustments.append("⚠️ Luptă retrogradare (mai puține goluri)")

                # Title fight = more intense, variable
                if h_rank <= 3 and a_rank <= 3:
                    adjustments.append("🏆 Duel la vârf!")

    # Recalculate derived probabilities
    probs["ng"] = round(100 - probs["gg"], 1)
    probs["under15"] = round(100 - probs["over15"], 1)
    probs["under25"] = round(100 - probs["over25"], 1)
    probs["under35"] = round(100 - probs["over35"], 1)
    probs["home_draw"] = round(probs["home"] + probs["draw"], 1)
    probs["draw_away"] = round(probs["draw"] + probs["away"], 1)
    probs["home_away"] = round(probs["home"] + probs["away"], 1)
    hat = probs["home"] + probs["away"]
    if hat > 0:
        probs["dnb_home"] = round(probs["home"] / hat * 100, 1)
        probs["dnb_away"] = round(probs["away"] / hat * 100, 1)

    return probs, adjustments, n_home_inj, n_away_inj

# ─────────────────────────────────────────────
# PROBABILITY CALCULATIONS
# ─────────────────────────────────────────────
def calc_stats(events, team_id, context="all"):
    total = gg = o15 = o25 = o35 = o45 = wins = draws = losses = 0
    gs = gc = cs = odd_g = even_g = 0
    form_results = []
    w_gs = w_gc = w_total = 0  # weighted goals for Poisson
    for idx, ev in enumerate(events):
        is_home = (ev["home_id"] == team_id)
        if context == "home" and not is_home:
            continue
        if context == "away" and is_home:
            continue
        gh, ga = ev["home_goals"], ev["away_goals"]
        tg = gh + ga
        total += 1
        # Form weighting: recent matches count more
        weight = 2.0 if total <= 3 else (1.5 if total <= 5 else 1.0)
        if is_home:
            gs += gh; gc += ga
            w_gs += gh * weight; w_gc += ga * weight; w_total += weight
            if ga == 0: cs += 1
            if gh > ga: wins += 1; form_results.append("W")
            elif gh == ga: draws += 1; form_results.append("D")
            else: losses += 1; form_results.append("L")
        else:
            gs += ga; gc += gh
            w_gs += ga * weight; w_gc += gh * weight; w_total += weight
            if gh == 0: cs += 1
            if ga > gh: wins += 1; form_results.append("W")
            elif ga == gh: draws += 1; form_results.append("D")
            else: losses += 1; form_results.append("L")
        if gh > 0 and ga > 0: gg += 1
        if tg >= 2: o15 += 1
        if tg >= 3: o25 += 1
        if tg >= 4: o35 += 1
        if tg >= 5: o45 += 1
        if tg % 2 == 1: odd_g += 1
        else: even_g += 1
    if total == 0:
        return None
    pct = lambda n: round(n / total * 100, 1)
    last5 = form_results[:5]
    form_w = last5.count("W") if last5 else 0
    form_pts = (last5.count("W") * 3 + last5.count("D")) / max(len(last5), 1)
    # Weighted averages for Poisson model
    w_avg_scored = round(w_gs / w_total, 3) if w_total > 0 else round(gs / total, 3)
    w_avg_conceded = round(w_gc / w_total, 3) if w_total > 0 else round(gc / total, 3)
    return {"total": total, "gg_pct": pct(gg), "o15_pct": pct(o15), "o25_pct": pct(o25),
            "o35_pct": pct(o35), "o45_pct": pct(o45), "win_pct": pct(wins), "draw_pct": pct(draws),
            "loss_pct": pct(losses), "cs_pct": pct(cs),
            "avg_scored": round(gs/total, 2), "avg_conceded": round(gc/total, 2),
            "w_avg_scored": w_avg_scored, "w_avg_conceded": w_avg_conceded,
            "odd_pct": pct(odd_g), "even_pct": pct(even_g),
            "form_pts": round(form_pts, 2), "form_w5": form_w, "form_str": "".join(last5)}

def calc_h2h_stats(events):
    total = gg = o15 = o25 = o35 = hw = dr = aw = 0
    for ev in events:
        gh, ga = ev["home_goals"], ev["away_goals"]
        tg = gh + ga
        total += 1
        if gh > 0 and ga > 0: gg += 1
        if tg >= 2: o15 += 1
        if tg >= 3: o25 += 1
        if tg >= 4: o35 += 1
        if gh > ga: hw += 1
        elif gh == ga: dr += 1
        else: aw += 1
    if total == 0:
        return None
    pct = lambda n: round(n / total * 100, 1)
    return {"total": total, "gg_pct": pct(gg), "o15_pct": pct(o15), "o25_pct": pct(o25),
            "o35_pct": pct(o35), "home_win_pct": pct(hw), "draw_pct": pct(dr), "away_win_pct": pct(aw)}

def calc_real_probs(hs, aws, h2h):
    import math
    def poisson_pmf(k, lam):
        if lam <= 0: lam = 0.01
        return (lam**k * math.exp(-lam)) / math.factorial(k)
    def poisson_cdf(k, lam):
        return sum(poisson_pmf(i, lam) for i in range(k+1))

    def blend(h, a, hh):
        if hh is not None:
            return round(h * 0.4 + a * 0.4 + hh * 0.2, 1)
        return round((h + a) / 2, 1)
    p = {}
    # --- POISSON MODEL ---
    # Expected goals using weighted averages (recent form weighted 2x)
    h_attack = hs["w_avg_scored"]    # Home team attacking strength
    h_defend = hs["w_avg_conceded"]  # Home team defensive weakness
    a_attack = aws["w_avg_scored"]   # Away team attacking strength
    a_defend = aws["w_avg_conceded"] # Away team defensive weakness
    # Expected goals per team
    lambda_home = max(0.3, (h_attack + a_defend) / 2 * 1.1)  # home advantage +10%
    lambda_away = max(0.2, (a_attack + h_defend) / 2 * 0.9)  # away penalty -10%
    lambda_total = lambda_home + lambda_away
    # --- GOAL PROBABILITIES via Poisson ---
    # Over/Under with Poisson (MUCH more accurate than counting percentages)
    p_o15 = round((1 - poisson_cdf(1, lambda_total)) * 100, 1)
    p_o25 = round((1 - poisson_cdf(2, lambda_total)) * 100, 1)
    p_o35 = round((1 - poisson_cdf(3, lambda_total)) * 100, 1)
    p_o45 = round((1 - poisson_cdf(4, lambda_total)) * 100, 1)
    # Blend Poisson (60%) with historical (40%) for robustness
    hgg = h2h["gg_pct"] if h2h else None
    p["gg"] = blend(hs["gg_pct"], aws["gg_pct"], hgg)
    p["ng"] = round(100 - p["gg"], 1)
    ho15 = h2h["o15_pct"] if h2h else None
    ho25 = h2h["o25_pct"] if h2h else None
    ho35 = h2h["o35_pct"] if h2h else None
    hist_o15 = blend(hs["o15_pct"], aws["o15_pct"], ho15)
    hist_o25 = blend(hs["o25_pct"], aws["o25_pct"], ho25)
    hist_o35 = blend(hs["o35_pct"], aws["o35_pct"], ho35)
    p["over15"] = round(p_o15 * 0.6 + hist_o15 * 0.4, 1)
    p["over25"] = round(p_o25 * 0.6 + hist_o25 * 0.4, 1)
    p["over35"] = round(p_o35 * 0.6 + hist_o35 * 0.4, 1)
    p["over45"] = round(p_o45 * 0.6 + blend(hs.get("o45_pct",0), aws.get("o45_pct",0), None) * 0.4, 1)
    for k in ["over15","over25","over35","over45"]:
        p[k] = max(2, min(98, p[k]))
        p[k.replace("over","under")] = round(100 - p[k], 1)
    # --- 1X2 via Poisson matrix ---
    max_goals = 7
    p_home_win = p_draw = p_away_win = 0
    for i in range(max_goals):
        for j in range(max_goals):
            prob_ij = poisson_pmf(i, lambda_home) * poisson_pmf(j, lambda_away)
            if i > j: p_home_win += prob_ij
            elif i == j: p_draw += prob_ij
            else: p_away_win += prob_ij
    # Blend Poisson 1X2 (55%) with historical (45%)
    hhw = h2h["home_win_pct"] if h2h else None
    hdw = h2h["draw_pct"] if h2h else None
    haw = h2h["away_win_pct"] if h2h else None
    hist_home = blend(hs["win_pct"], aws["loss_pct"], hhw)
    hist_draw = blend(hs["draw_pct"], aws["draw_pct"], hdw)
    hist_away = blend(hs["loss_pct"], aws["win_pct"], haw)
    raw_home = p_home_win * 100 * 0.55 + hist_home * 0.45
    raw_draw = p_draw * 100 * 0.55 + hist_draw * 0.45
    raw_away = p_away_win * 100 * 0.55 + hist_away * 0.45
    t = raw_home + raw_draw + raw_away
    if t > 0:
        p["home"] = round(raw_home/t*100,1); p["draw"] = round(raw_draw/t*100,1); p["away"] = round(raw_away/t*100,1)
    else:
        p["home"]=40.0; p["draw"]=30.0; p["away"]=30.0
    p["home_draw"] = round(p["home"]+p["draw"],1)
    p["draw_away"] = round(p["draw"]+p["away"],1)
    p["home_away"] = round(p["home"]+p["away"],1)
    hat = p["home"]+p["away"]
    if hat > 0:
        p["dnb_home"]=round(p["home"]/hat*100,1); p["dnb_away"]=round(p["away"]/hat*100,1)
    else:
        p["dnb_home"]=50.0; p["dnb_away"]=50.0
    # First Half (Poisson-derived)
    lam_fh = lambda_total * 0.44  # ~44% of goals in first half
    p["fh_over05"]=round(max(2, min(98, (1-poisson_cdf(0, lam_fh))*100)),1)
    p["fh_over15"]=round(max(2, min(95, (1-poisson_cdf(1, lam_fh))*100)),1)
    p["fh_under05"]=round(100-p["fh_over05"],1)
    p["fh_under15"]=round(100-p["fh_over15"],1)
    p["fh_home"]=round(min(p["home"]*0.9,80),1)
    p["fh_draw"]=round(min(45,p["draw"]*1.4),1)
    p["fh_away"]=round(max(5, 100-p["fh_home"]-p["fh_draw"]),1)
    # Second Half
    lam_sh = lambda_total * 0.56  # ~56% of goals in second half
    p["sh_over05"]=round(max(2, min(98, (1-poisson_cdf(0, lam_sh))*100)),1)
    p["sh_over15"]=round(max(2, min(95, (1-poisson_cdf(1, lam_sh))*100)),1)
    p["sh_under05"]=round(100-p["sh_over05"],1)
    p["sh_under15"]=round(100-p["sh_over15"],1)
    p["sh_home"]=round(p["home"]*0.95,1)
    p["sh_draw"]=round(min(42,p["draw"]*1.2),1)
    p["sh_away"]=round(max(5, 100-p["sh_home"]-p["sh_draw"]),1)
    # Odd/Even goals
    p["odd"]=blend(hs.get("odd_pct",50), aws.get("odd_pct",50), None)
    p["even"]=round(100-p["odd"],1)
    # Team total goals (Poisson per team)
    p["home_o05"]=round(max(2, min(98, (1-poisson_pmf(0, lambda_home))*100)),1); p["home_u05"]=round(100-p["home_o05"],1)
    p["home_o15"]=round(max(2, min(95, (1-poisson_cdf(1, lambda_home))*100)),1); p["home_u15"]=round(100-p["home_o15"],1)
    p["away_o05"]=round(max(2, min(98, (1-poisson_pmf(0, lambda_away))*100)),1); p["away_u05"]=round(100-p["away_o05"],1)
    p["away_o15"]=round(max(2, min(95, (1-poisson_cdf(1, lambda_away))*100)),1); p["away_u15"]=round(100-p["away_o15"],1)
    # Asian Handicap probabilities (Poisson-based)
    # -0.5: team must WIN (not draw). P(home win) from Poisson matrix
    p["ah_home_-05"]=round(p_home_win*100,1); p["ah_away_+05"]=round(100-p["ah_home_-05"],1)
    # +0.5: team can WIN or DRAW
    p["ah_home_+05"]=round((p_home_win+p_draw)*100,1); p["ah_away_-05"]=round(100-p["ah_home_+05"],1)
    # -1: must win by 2+
    p_hw2 = sum(poisson_pmf(i, lambda_home)*poisson_pmf(j, lambda_away) for i in range(max_goals) for j in range(max_goals) if i-j>=2)
    p["ah_home_-10"]=round(max(2, p_hw2*100),1); p["ah_away_+10"]=round(100-p["ah_home_-10"],1)
    # +1: can lose by 1 or less
    p_not_lose2 = sum(poisson_pmf(i, lambda_home)*poisson_pmf(j, lambda_away) for i in range(max_goals) for j in range(max_goals) if i-j>=-1)
    p["ah_home_+10"]=round(min(98, p_not_lose2*100),1); p["ah_away_-10"]=round(100-p["ah_home_+10"],1)
    # -1.5: must win by 2+
    p["ah_home_-15"]=round(max(2, p_hw2*100),1); p["ah_away_+15"]=round(100-p["ah_home_-15"],1)
    # +1.5: can lose by 1 or less
    p["ah_home_+15"]=round(min(98, p_not_lose2*100),1); p["ah_away_-15"]=round(100-p["ah_home_+15"],1)
    # -2: must win by 3+
    p_hw3 = sum(poisson_pmf(i, lambda_home)*poisson_pmf(j, lambda_away) for i in range(max_goals) for j in range(max_goals) if i-j>=3)
    p["ah_home_-20"]=round(max(1, p_hw3*100),1); p["ah_away_+20"]=round(100-p["ah_home_-20"],1)
    p["ah_home_-25"]=round(max(1, p_hw3*100),1); p["ah_away_+25"]=round(100-p["ah_home_-25"],1)
    # Quarter lines (average of adjacent)
    p["ah_home_-025"]=round((p["ah_home_-05"]+p["ah_home_+05"])/2,1); p["ah_away_+025"]=round(100-p["ah_home_-025"],1)
    p["ah_home_-075"]=round((p["ah_home_-05"]+p["ah_home_-10"])/2,1); p["ah_away_+075"]=round(100-p["ah_home_-075"],1)
    p["ah_home_-125"]=round((p["ah_home_-10"]+p["ah_home_-15"])/2,1); p["ah_away_+125"]=round(100-p["ah_home_-125"],1)
    p["ah_home_+025"]=round((p["ah_home_+05"]+p["ah_home_-05"])/2+p_draw*50,1); p["ah_away_-025"]=round(100-p["ah_home_+025"],1)
    # Clean Sheet (Poisson: P(0 goals) for opponent)
    p["cs_home_yes"]=round(max(2, min(60, poisson_pmf(0, lambda_away)*100)),1)
    p["cs_home_no"]=round(100-p["cs_home_yes"],1)
    p["cs_away_yes"]=round(max(2, min(50, poisson_pmf(0, lambda_home)*100)),1)
    p["cs_away_no"]=round(100-p["cs_away_yes"],1)
    # Win to Nil
    p["wtn_home"]=round(p["home"]*p["cs_home_yes"]/100,1)
    p["wtn_home_no"]=round(100-p["wtn_home"],1)
    p["wtn_away"]=round(p["away"]*p["cs_away_yes"]/100,1)
    p["wtn_away_no"]=round(100-p["wtn_away"],1)
    # GG Poisson: P(both score) = 1 - P(home=0) - P(away=0) + P(both=0)
    p_gg_poisson = (1 - poisson_pmf(0, lambda_home) - poisson_pmf(0, lambda_away) + poisson_pmf(0, lambda_home)*poisson_pmf(0, lambda_away)) * 100
    p["gg"] = round(p["gg"] * 0.4 + p_gg_poisson * 0.6, 1)  # blend with Poisson
    p["gg"] = max(5, min(95, p["gg"]))
    p["ng"] = round(100 - p["gg"], 1)
    # Results/Both Teams Score combo
    p["home_gg_yes"]=round(p["home"]*p["gg"]/100,1)
    p["draw_gg_yes"]=round(p["draw"]*p["gg"]/100,1)
    p["away_gg_yes"]=round(p["away"]*p["gg"]/100,1)
    p["home_gg_no"]=round(p["home"]*p["ng"]/100,1)
    p["draw_gg_no"]=round(p["draw"]*p["ng"]/100,1)
    p["away_gg_no"]=round(p["away"]*p["ng"]/100,1)
    # To Score in Both Halves
    fh_goal_pct = min(p["fh_over05"], 95)
    sh_goal_pct = min(p["sh_over05"], 95)
    p["score_both_halves_yes"] = round(fh_goal_pct * sh_goal_pct / 100, 1)
    p["score_both_halves_no"] = round(100 - p["score_both_halves_yes"], 1)
    # Highest Scoring Half
    p["highest_1st"] = round(max(20, 100 - sh_goal_pct * 0.6), 1)
    p["highest_2nd"] = round(max(30, sh_goal_pct * 0.6), 1)
    p["highest_draw"] = round(max(5, 100 - p["highest_1st"] - p["highest_2nd"]), 1)
    # Both Teams Score - First Half
    fh_gg = round(p["gg"] * 0.40, 1)
    p["fh_gg_yes"] = max(3, min(fh_gg, 40))
    p["fh_gg_no"] = round(100 - p["fh_gg_yes"], 1)
    # Both Teams Score - Second Half
    sh_gg = round(p["gg"] * 0.52, 1)
    p["sh_gg_yes"] = max(4, min(sh_gg, 48))
    p["sh_gg_no"] = round(100 - p["sh_gg_yes"], 1)
    # Store lambdas for Kelly
    p["_lambda_home"] = round(lambda_home, 3)
    p["_lambda_away"] = round(lambda_away, 3)
    return p

def add_card_probs(p, h_cards, a_cards):
    """Add card probabilities based on team card averages."""
    if not h_cards or not a_cards:
        return p
    # Combined average cards per match
    avg_total = h_cards["avg_cards"] + a_cards["avg_cards"]
    # Use Poisson-like estimation for over/under
    import math
    def poisson_over(lam, k):
        # P(X >= k) = 1 - P(X < k)
        p_under = sum((lam**i * math.exp(-lam)) / math.factorial(i) for i in range(k))
        return round(min(max(p_under * 100, 1), 99) if k == 0 else min(max((1 - p_under) * 100, 1), 99), 1)
    p["cards_o25"] = poisson_over(avg_total, 3)
    p["cards_u25"] = round(100 - p["cards_o25"], 1)
    p["cards_o35"] = poisson_over(avg_total, 4)
    p["cards_u35"] = round(100 - p["cards_o35"], 1)
    p["cards_o45"] = poisson_over(avg_total, 5)
    p["cards_u45"] = round(100 - p["cards_o45"], 1)
    p["cards_o55"] = poisson_over(avg_total, 6)
    p["cards_u55"] = round(100 - p["cards_o55"], 1)
    # Home/Away cards
    h_avg = h_cards["avg_cards"]
    a_avg = a_cards["avg_cards"]
    p["hcards_o05"] = poisson_over(h_avg, 1)
    p["hcards_u05"] = round(100 - p["hcards_o05"], 1)
    p["hcards_o15"] = poisson_over(h_avg, 2)
    p["hcards_u15"] = round(100 - p["hcards_o15"], 1)
    p["acards_o05"] = poisson_over(a_avg, 1)
    p["acards_u05"] = round(100 - p["acards_o05"], 1)
    p["acards_o15"] = poisson_over(a_avg, 2)
    p["acards_u15"] = round(100 - p["acards_o15"], 1)
    return p

def calc_confidence(ev, prob, home_stats, away_stats, h2h_stats, league_name=""):
    """Confidence 1-100: EV + Prob + Form + Liga + H2H."""
    score = 0
    score += min(ev * 1.5, 25)
    score += round(min(prob / 100 * 30, 30))
    h_form = home_stats.get("form_pts", 1.0)
    a_form = away_stats.get("form_pts", 1.0)
    score += round(min((h_form + a_form) / 2 / 3 * 20, 20))
    score += {1: 15, 2: 10, 3: 5}.get(get_league_tier(league_name), 5)
    if h2h_stats and h2h_stats["total"] >= 3: score += 10
    elif h2h_stats: score += 5
    return min(max(int(score), 1), 100)

TIER1 = {"premier league","la liga","serie a","bundesliga","ligue 1",
    "champions league","europa league","conference league","eredivisie",
    "primeira liga","championship","serie b","bundesliga 2","mls",
    "liga mx","brasileirao serie a","copa libertadores"}
TIER2 = {"scottish premiership","super league","belgian pro league",
    "ekstraklasa","czech liga","austrian bundesliga","danish superliga",
    "allsvenskan","eliteserien","k league 1","j1 league","a-league",
    "brasileirao serie b","liga profesional argentina","superettan",
    "jupiler pro league","super lig","copa sudamericana"}

def get_league_tier(ln):
    ll = ln.lower()
    if any(t in ll for t in TIER1): return 1
    if any(t in ll for t in TIER2): return 2
    return 3

def calc_kelly(prob, odds):
    """Kelly/4 conservative: max 10% of bankroll."""
    p = prob / 100; b = odds - 1
    if b <= 0: return 0
    k = (p * b - (1-p)) / b
    return round(min(max(k / 4 * 100, 0), 10), 1)

# ─────────────────────────────────────────────
# EV CALCULATION
# ─────────────────────────────────────────────
def map_odds_to_prob(bn, v, p):
    v = v.strip()
    if bn == "Match Winner":
        return {"Home":p.get("home"),"Draw":p.get("draw"),"Away":p.get("away")}.get(v)
    elif bn == "Both Teams Score":
        return {"Yes":p.get("gg"),"No":p.get("ng")}.get(v)
    elif bn == "Goals Over/Under":
        m = {"Over 1.5":"over15","Under 1.5":"under15","Over 2.5":"over25",
             "Under 2.5":"under25","Over 3.5":"over35","Under 3.5":"under35",
             "Over 4.5":"over45","Under 4.5":"under45"}
        return p.get(m.get(v))
    elif bn == "Double Chance":
        m = {"Home/Draw":"home_draw","Draw/Away":"draw_away","Home/Away":"home_away"}
        return p.get(m.get(v))
    elif bn == "Home/Away":
        return {"Home":p.get("dnb_home"),"Away":p.get("dnb_away")}.get(v)
    elif bn == "Goals Over/Under First Half":
        if "Over 0.5" in v: return p.get("fh_over05")
        elif "Under 0.5" in v: return p.get("fh_under05")
        elif "Over 1.5" in v: return p.get("fh_over15")
        elif "Under 1.5" in v: return p.get("fh_under15")
    elif bn == "Goals Over/Under Second Half":
        if "Over 0.5" in v: return p.get("sh_over05")
        elif "Under 0.5" in v: return p.get("sh_under05")
        elif "Over 1.5" in v: return p.get("sh_over15")
        elif "Under 1.5" in v: return p.get("sh_under15")
    elif bn == "Second Half Winner":
        return {"Home":p.get("sh_home"),"Draw":p.get("sh_draw"),"Away":p.get("sh_away")}.get(v)
    elif bn == "First Half Winner":
        return {"Home":p.get("fh_home"),"Draw":p.get("fh_draw"),"Away":p.get("fh_away")}.get(v)
    elif bn == "Odd/Even":
        return {"Odd":p.get("odd"),"Even":p.get("even")}.get(v)
    elif bn == "Total - Home":
        if "Over 0.5" in v: return p.get("home_o05")
        elif "Under 0.5" in v: return p.get("home_u05")
        elif "Over 1.5" in v: return p.get("home_o15")
        elif "Under 1.5" in v: return p.get("home_u15")
    elif bn == "Total - Away":
        if "Over 0.5" in v: return p.get("away_o05")
        elif "Under 0.5" in v: return p.get("away_u05")
        elif "Over 1.5" in v: return p.get("away_o15")
        elif "Under 1.5" in v: return p.get("away_u15")
    elif bn == "Asian Handicap":
        # Only standard lines — quarter lines (±0.25, ±0.75, ±1.25) have fake API odds!
        m = {"Home -0.5":"ah_home_-05","Away +0.5":"ah_away_+05",
             "Home -1":"ah_home_-10","Away +1":"ah_away_+10",
             "Home -1.5":"ah_home_-15","Away +1.5":"ah_away_+15",
             "Home -2":"ah_home_-20","Away +2":"ah_away_+20",
             "Home -2.5":"ah_home_-25","Away +2.5":"ah_away_+25",
             "Home +0.5":"ah_home_+05","Away -0.5":"ah_away_-05",
             "Home +1":"ah_home_+10","Away -1":"ah_away_-10",
             "Home +1.5":"ah_home_+15","Away -1.5":"ah_away_-15"}
        return p.get(m.get(v))
    elif bn == "Clean Sheet - Home":
        return {"Yes":p.get("cs_home_yes"),"No":p.get("cs_home_no")}.get(v)
    elif bn == "Clean Sheet - Away":
        return {"Yes":p.get("cs_away_yes"),"No":p.get("cs_away_no")}.get(v)
    elif bn == "Win to Nil - Home":
        return {"Yes":p.get("wtn_home"),"No":p.get("wtn_home_no")}.get(v)
    elif bn == "Win to Nil - Away":
        return {"Yes":p.get("wtn_away"),"No":p.get("wtn_away_no")}.get(v)
    elif bn == "Double Chance - First Half":
        return {"Home/Draw":p.get("fh_1x"),"Draw/Away":p.get("fh_x2"),"Home/Away":p.get("fh_12")}.get(v)
    elif bn == "Total Cards":
        m = {"Over 2.5":"cards_o25","Under 2.5":"cards_u25",
             "Over 3.5":"cards_o35","Under 3.5":"cards_u35",
             "Over 4.5":"cards_o45","Under 4.5":"cards_u45",
             "Over 5.5":"cards_o55","Under 5.5":"cards_u55"}
        return p.get(m.get(v))
    elif bn == "Total Cards - Home":
        m = {"Over 0.5":"hcards_o05","Under 0.5":"hcards_u05",
             "Over 1.5":"hcards_o15","Under 1.5":"hcards_u15"}
        return p.get(m.get(v))
    elif bn == "Total Cards - Away":
        m = {"Over 0.5":"acards_o05","Under 0.5":"acards_u05",
             "Over 1.5":"acards_o15","Under 1.5":"acards_u15"}
        return p.get(m.get(v))
    elif bn == "Results/Both Teams Score":
        m = {"Home/Yes":"home_gg_yes","Draw/Yes":"draw_gg_yes","Away/Yes":"away_gg_yes",
             "Home/No":"home_gg_no","Draw/No":"draw_gg_no","Away/No":"away_gg_no"}
        return p.get(m.get(v))
    elif bn == "To Score in Both Halves":
        return {"Yes":p.get("score_both_halves_yes"),"No":p.get("score_both_halves_no")}.get(v)
    elif bn == "Highest Scoring Half":
        return {"1st Half":p.get("highest_1st"),"2nd Half":p.get("highest_2nd"),"Draw":p.get("highest_draw")}.get(v)
    elif bn == "Both Teams Score - First Half":
        return {"Yes":p.get("fh_gg_yes"),"No":p.get("fh_gg_no")}.get(v)
    elif bn == "Both Teams To Score - Second Half":
        return {"Yes":p.get("sh_gg_yes"),"No":p.get("sh_gg_no")}.get(v)
    return None

def translate_bet(bn, v):
    v = v.strip()
    if bn == "Match Winner":
        return {"Home":"1 Gazdă","Draw":"X Egal","Away":"2 Oaspete"}.get(v, v)
    elif bn == "Both Teams Score":
        return {"Yes":"GG Da","No":"GG Nu"}.get(v, v)
    elif bn == "Goals Over/Under":
        return v.replace("Over","Peste").replace("Under","Sub")
    elif bn == "Double Chance":
        return {"Home/Draw":"1X","Draw/Away":"X2","Home/Away":"12"}.get(v, v)
    elif bn == "Home/Away":
        return {"Home":"Gazdă DNB","Away":"Oaspete DNB"}.get(v, v)
    elif bn == "Goals Over/Under First Half":
        return "R1 " + v.replace("Over","Peste").replace("Under","Sub")
    elif bn == "Goals Over/Under Second Half":
        return "R2 " + v.replace("Over","Peste").replace("Under","Sub")
    elif bn == "Second Half Winner":
        return {"Home":"R2 1 Gazdă","Draw":"R2 X Egal","Away":"R2 2 Oaspete"}.get(v, v)
    elif bn == "First Half Winner":
        return {"Home":"R1 1 Gazdă","Draw":"R1 X Egal","Away":"R1 2 Oaspete"}.get(v, v)
    elif bn == "Odd/Even":
        return {"Odd":"Impar","Even":"Par"}.get(v, v)
    elif bn == "Total - Home":
        return "Gazdă " + v.replace("Over","Peste").replace("Under","Sub")
    elif bn == "Total - Away":
        return "Oaspete " + v.replace("Over","Peste").replace("Under","Sub")
    elif bn == "Asian Handicap":
        return "AH " + v.replace("Home","Gazdă").replace("Away","Oaspete")
    elif bn == "Clean Sheet - Home":
        return {"Yes":"CS Gazdă Da","No":"CS Gazdă Nu"}.get(v, v)
    elif bn == "Clean Sheet - Away":
        return {"Yes":"CS Oaspete Da","No":"CS Oaspete Nu"}.get(v, v)
    elif bn == "Win to Nil - Home":
        return {"Yes":"Gazdă la 0 Da","No":"Gazdă la 0 Nu"}.get(v, v)
    elif bn == "Win to Nil - Away":
        return {"Yes":"Oaspete la 0 Da","No":"Oaspete la 0 Nu"}.get(v, v)
    elif bn == "Double Chance - First Half":
        return {"Home/Draw":"R1 1X","Draw/Away":"R1 X2","Home/Away":"R1 12"}.get(v, v)
    elif bn == "Total Cards":
        return "🟨 " + v.replace("Over","Peste").replace("Under","Sub") + " cart."
    elif bn == "Total Cards - Home":
        return "🟨 Gazdă " + v.replace("Over","Peste").replace("Under","Sub") + " cart."
    elif bn == "Total Cards - Away":
        return "🟨 Oaspete " + v.replace("Over","Peste").replace("Under","Sub") + " cart."
    elif bn == "Results/Both Teams Score":
        m = {"Home/Yes":"1 & GG","Draw/Yes":"X & GG","Away/Yes":"2 & GG",
             "Home/No":"1 & NG","Draw/No":"X & NG","Away/No":"2 & NG"}
        return m.get(v, v)
    elif bn == "To Score in Both Halves":
        return {"Yes":"Gol ambele reprize","No":"NU gol ambele reprize"}.get(v, v)
    elif bn == "Highest Scoring Half":
        return {"1st Half":"R1 mai multe goluri","2nd Half":"R2 mai multe goluri","Draw":"Egal goluri"}.get(v, v)
    elif bn == "Both Teams Score - First Half":
        return {"Yes":"GG Repriza 1","No":"NG Repriza 1"}.get(v, v)
    elif bn == "Both Teams To Score - Second Half":
        return {"Yes":"GG Repriza 2","No":"NG Repriza 2"}.get(v, v)
    return v

def find_value_bets(bets_list, probs, bookmaker_name):
    vbs = []
    for bet in bets_list:
        bn = bet.get("name", "")
        if bn not in SUPPORTED_BETS:
            continue
        # Skip AH from bookmakers with broken odds (Superbet)
        if bn == "Asian Handicap" and bookmaker_name in AH_BLOCKED_BOOKMAKERS:
            continue
        for val in bet.get("values", []):
            try:
                odds = float(val.get("odd", "0"))
            except (ValueError, TypeError):
                continue
            if odds < MIN_ODDS or odds > MAX_ODDS:
                continue
            vl = str(val.get("value", ""))
            rp = map_odds_to_prob(bn, vl, probs)
            if rp is None:
                continue
            ip = round(1/odds*100, 1)
            # 10% discount — our model tends to overestimate
            rp_adj = round(rp * 0.90, 1)
            ev = round(rp_adj - ip, 1)
            # Collect at EV >= 3% (picks #2,#3 need alternatives)
            # Match only qualifies if at least 1 bet has EV >= MIN_EV (5%)
            if ev >= 3.0 and rp_adj >= 50:
                vbs.append({"market": translate_bet(bn, vl), "odds": odds,
                    "real_prob": rp_adj, "implied_prob": ip, "ev": ev, "bookmaker": bookmaker_name})
    return vbs

# ─────────────────────────────────────────────
# MAIN DATA LOADING
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_all_data():
    today = date.today().strftime("%Y-%m-%d")
    fixtures = fetch_fixtures(today)
    if not fixtures:
        return [], today
    betano_odds = fetch_odds_bulk(today, BETANO_ID)
    superbet_odds = fetch_odds_bulk(today, SUPERBET_ID)
    fwo = []
    for f in fixtures:
        fid = f["fixture_id"]
        bo = betano_odds.get(fid, [])
        so = superbet_odds.get(fid, [])
        if bo or so:
            f["betano_bets"] = bo
            f["superbet_bets"] = so
            fwo.append(f)
    results = []
    team_cache = {}
    standings_cache = {}
    for fix in fwo[:120]:
        hid, aid = fix["home_id"], fix["away_id"]
        if hid not in team_cache:
            team_cache[hid] = fetch_team_matches(hid)
        if aid not in team_cache:
            team_cache[aid] = fetch_team_matches(aid)
        hstats = calc_stats(team_cache[hid], hid, "home")
        astats = calc_stats(team_cache[aid], aid, "away")
        if not hstats or not astats:
            continue
        # Minimum data filter
        if hstats["total"] < MIN_DATA_MATCHES or astats["total"] < MIN_DATA_MATCHES:
            continue
        h2h_ev = fetch_h2h(hid, aid)
        h2h_st = calc_h2h_stats(h2h_ev) if len(h2h_ev) >= 2 else None
        probs = calc_real_probs(hstats, astats, h2h_st)
        # Adjust probabilities with injuries + standings
        probs, adjustments, n_h_inj, n_a_inj = adjust_probs(
            probs, hid, aid, fix["fixture_id"],
            fix.get("league_id"), fix.get("season"), standings_cache)
        # Card probabilities
        h_cards = fetch_team_cards(hid, fix.get("league_id"), fix.get("season"))
        a_cards = fetch_team_cards(aid, fix.get("league_id"), fix.get("season"))
        probs = add_card_probs(probs, h_cards, a_cards)
        all_vb = []
        all_vb.extend(find_value_bets(fix.get("betano_bets",[]), probs, "Betano"))
        all_vb.extend(find_value_bets(fix.get("superbet_bets",[]), probs, "Superbet"))
        if not all_vb:
            continue
        best_by_mkt = {}
        for vb in all_vb:
            k = vb["market"]
            if k not in best_by_mkt or vb["odds"] > best_by_mkt[k]["odds"]:
                best_by_mkt[k] = vb
        sorted_vb = sorted(best_by_mkt.values(), key=lambda x: x["ev"] * 0.4 + x["real_prob"] * 0.6, reverse=True)
        # Top 3 picks
        top3 = sorted_vb[:3]
        for pick in top3:
            pick["kelly"] = calc_kelly(pick["real_prob"], pick["odds"])
            # Confidence level: 🟢🟡🔴
            if pick["ev"] >= 8 and pick["real_prob"] >= 58:
                pick["level"] = "🟢"
            elif pick["ev"] >= 5 and pick["real_prob"] >= 55:
                pick["level"] = "🟡"
            else:
                pick["level"] = "🔴"
        best = top3[0]
        # Match only qualifies if best pick has EV >= MIN_EV
        if best["ev"] < MIN_EV:
            continue
        conf = calc_confidence(best["ev"], best["real_prob"], hstats, astats, h2h_st, fix["league"])
        results.append({"time": fix["time"], "timestamp": fix["timestamp"],
            "home_team": fix["home_team"], "away_team": fix["away_team"],
            "league": fix["league"], "country": fix["country"],
            "referee": fix.get("referee", ""),
            "top3": top3, "confidence": conf,
            "home_form": hstats.get("form_str",""), "away_form": astats.get("form_str","")})
    results.sort(key=lambda x: x["timestamp"])
    return results, today

# ─────────────────────────────────────────────
# EV COLOR
# ─────────────────────────────────────────────
def ev_color(ev):
    if ev >= 15: return "#34d399"
    elif ev >= 10: return "#f59e0b"
    return "#38bdf8"

def ev_bg(ev):
    if ev >= 15: return "rgba(52,211,153,0.15)"
    elif ev >= 10: return "rgba(245,158,11,0.12)"
    return "rgba(56,189,248,0.10)"

# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────
today_str = datetime.now(RO_TZ).strftime("%d %B %Y")
st.markdown(f"""
<div class="main-header">
    <h1>🏔️ NORD ALLASKA SUPREME</h1>
    <p>Value Bet Scanner · Betano + Superbet · {today_str}</p>
</div>
""", unsafe_allow_html=True)

col_r = st.columns([1, 2, 1])
with col_r[1]:
    refresh = st.button("🔄 Scanează Value Bets", use_container_width=True, type="primary")
    st.markdown("<div style='text-align:center;font-size:0.75rem;color:#475569;margin-top:4px;'>"
                "API-Football PRO · Betano + Superbet · Cote 1.75–3.00 · EV > 5%</div>",
                unsafe_allow_html=True)
if refresh:
    st.cache_data.clear()

with st.spinner("⏳ Scanez meciurile și cotele de pe Betano + Superbet..."):
    matches, data_date = load_all_data()

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# SUMMARY
total_vb = len(matches)
total_picks = sum(len(m["top3"]) for m in matches)
green_picks = sum(1 for m in matches for p in m["top3"] if p["level"] == "🟢")
avg_ev = round(sum(m["top3"][0]["ev"] for m in matches) / max(total_vb, 1), 1) if matches else 0

mc = st.columns(4)
for col, (icon, val, label, color) in zip(mc, [
    ("🎯", str(total_vb), "Meciuri analizate", "#38bdf8"),
    ("🟢", str(green_picks), "Încredere MARE", "#34d399"),
    ("⚽", str(total_picks), "Total pariuri", "#f59e0b"),
    ("📈", f"+{avg_ev}%", "EV Mediu #1", "#a78bfa")]):
    col.markdown(f"<div class='metric-card'><div class='value' style='color:{color};'>{icon} {val}</div>"
                 f"<div class='label'>{label}</div></div>", unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# MATCHES
if not matches:
    st.markdown("<div style='text-align:center;padding:3rem;color:#64748b;font-size:1.2rem;'>"
                "🔍 Nu am găsit value bets azi.<br>"
                "<span style='font-size:0.85rem;'>Meciurile nu au cote între 1.75–3.00 cu EV > 5%</span>"
                "</div>", unsafe_allow_html=True)
else:
    st.markdown(f"<div style='font-size:1.15rem;font-weight:700;color:#e2e8f0;margin:1rem 0;'>"
                f"🎯 {total_vb} meciuri cu valoare — TOP 3 pariuri per meci</div>", unsafe_allow_html=True)
    for i, m in enumerate(matches):
        top3 = m["top3"]
        best = top3[0]
        # Build form HTML
        form_colors = {"W": "#34d399", "D": "#f59e0b", "L": "#ef4444"}
        hf_html = ""
        for c in m.get("home_form", "")[:5]:
            col = form_colors.get(c, "#64748b")
            hf_html += f"<span style='color:{col};font-weight:800;font-size:0.8rem;margin:0 1px;'>{c}</span>"
        af_html = ""
        for c in m.get("away_form", "")[:5]:
            col = form_colors.get(c, "#64748b")
            af_html += f"<span style='color:{col};font-weight:800;font-size:0.8rem;margin:0 1px;'>{c}</span>"
        st.markdown(f"""
<div style='background:rgba(30,41,59,0.7);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:16px;margin:12px 0;'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;'>
    <div>
      <span style='font-size:0.8rem;color:#64748b;margin-right:12px;'>🕐 {m['time']}</span>
      <span style='font-weight:800;font-size:1.1rem;color:#f1f5f9;'>{m['home_team']} <span style='color:#475569;'>vs</span> {m['away_team']}</span>
    </div>
    <div style='text-align:right;'>
      <span style='font-size:0.8rem;color:#94a3b8;'>{m['league']}</span>
      <span style='font-size:0.7rem;color:#475569;margin-left:8px;'>{m['country']}</span>
    </div>
  </div>
  <div style='display:flex;gap:6px;margin-bottom:12px;'>
    <span style='font-size:0.7rem;color:#64748b;'>Formă gazdă:</span>
    {hf_html}
    <span style='font-size:0.7rem;color:#475569;margin:0 6px;'>|</span>
    <span style='font-size:0.7rem;color:#64748b;'>Formă oaspete:</span>
    {af_html}
  </div>
""", unsafe_allow_html=True)
        # Pick #1 — GREEN BOX "JOACĂ"
        p1 = top3[0]
        bk_c1 = "#f59e0b" if p1["bookmaker"] == "Betano" else "#ec4899"
        st.markdown(f"""
  <div style='background:rgba(34,197,94,0.12);border:2px solid #22c55e;border-radius:10px;padding:12px 16px;margin-bottom:8px;'>
    <div style='display:flex;justify-content:space-between;align-items:center;'>
      <div style='display:flex;align-items:center;gap:12px;'>
        <span style='background:#22c55e;color:#000;font-weight:900;font-size:0.8rem;padding:4px 12px;border-radius:6px;'>🎯 JOACĂ</span>
        <span style='color:#22c55e;font-weight:700;font-size:1rem;'>{p1['market']}</span>
        <span style='color:#f1f5f9;font-weight:800;font-size:1.1rem;'>{p1['odds']}</span>
      </div>
      <div style='display:flex;align-items:center;gap:16px;'>
        <span style='color:#34d399;font-weight:800;'>{p1['real_prob']}%</span>
        <span style='color:#38bdf8;font-weight:800;'>+{p1['ev']}%</span>
        <span style='font-size:1.1rem;'>{p1['level']}</span>
        <span style='color:#a78bfa;font-size:0.85rem;'>Miză {p1['kelly']}%</span>
        <span style='color:{bk_c1};font-size:0.8rem;font-weight:600;'>{p1['bookmaker']}</span>
      </div>
    </div>
  </div>
""", unsafe_allow_html=True)
        # Pick #2 and #3
        for j, pk in enumerate(top3[1:], 2):
            bk_c = "#f59e0b" if pk["bookmaker"] == "Betano" else "#ec4899"
            st.markdown(f"""
  <div style='background:rgba(51,65,85,0.4);border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:8px 16px;margin-bottom:4px;'>
    <div style='display:flex;justify-content:space-between;align-items:center;'>
      <div style='display:flex;align-items:center;gap:12px;'>
        <span style='color:#64748b;font-weight:700;font-size:0.75rem;'>#{j}</span>
        <span style='color:#94a3b8;font-weight:600;font-size:0.9rem;'>{pk['market']}</span>
        <span style='color:#cbd5e1;font-weight:700;'>{pk['odds']}</span>
      </div>
      <div style='display:flex;align-items:center;gap:16px;'>
        <span style='color:#94a3b8;font-weight:700;'>{pk['real_prob']}%</span>
        <span style='color:#64748b;font-weight:700;'>+{pk['ev']}%</span>
        <span>{pk['level']}</span>
        <span style='color:#a78bfa;font-size:0.8rem;'>Miză {pk['kelly']}%</span>
        <span style='color:{bk_c};font-size:0.75rem;'>{pk['bookmaker']}</span>
      </div>
    </div>
  </div>
""", unsafe_allow_html=True)
        # Close card
        st.markdown("</div>", unsafe_allow_html=True)

# Legend
st.markdown("""
<div style='text-align:center;padding:1rem;color:#64748b;font-size:0.8rem;'>
🟢 ÎNCREDERE MARE (date solide, edge clar) · 🟡 ÎNCREDERE MEDIE (edge posibil) · 🔴 ÎNCREDERE MICĂ (risc ridicat)
</div>
""", unsafe_allow_html=True)

# FOOTER
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown(
    "<div class='footer-note'>"
    "⚠️ <strong>Disclaimer:</strong> Pariurile sportive implică riscuri financiare. "
    "EV pozitiv NU garantează profit pe termen scurt. Joacă responsabil.<br><br>"
    f"<strong>Sursă:</strong> API-Football PRO · Betano + Superbet · Cote {MIN_ODDS}–{MAX_ODDS} · EV > +{MIN_EV}%"
    "</div>", unsafe_allow_html=True)
