import streamlit as st
import requests
import json
import re
from datetime import datetime, timezone, timedelta

# ==========================================
# CONFIG & SECRETS
# ==========================================
API_KEY = st.secrets["API_KEY"]
GEMINI_KEY = st.secrets["GEMINI_KEY"]

HEADERS = {
    'x-apisports-key': API_KEY
}
API_BASE_URL = 'https://v3.football.api-sports.io'
GEMINI_URL = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro:generateContent?key={GEMINI_KEY}'

RO_TZ = timezone(timedelta(hours=3)) # UTC+3

EXCLUDE_WORDS = ["Women", "Youth", "U17", "U19", "U20", "U21", "U23",
                 "U18", "U22", "Reserve", "Reserves", "Amateur", "Amateurs",
                 "Beach Soccer", "Futsal", "Indoor", "eSoccer", "Esports",
                 "SRL", "Simulated", "Virtual", "Cyber", "Friendlies"]
EXCLUDE_TEAM_SUFFIXES = [" W", " Women", " Ladies", " Femenino", " Femminile", " Frauen"]

st.set_page_config(page_title="Nord Allaska Supreme", layout="wide")

# ==========================================
# CSS CUSTOMIZATION
# ==========================================
st.markdown("""
<style>
    .match-card {
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        border-left: 5px solid #4CAF50;
    }
    .pick-box {
        background-color: #2D2D2D;
        padding: 15px;
        border-radius: 8px;
        margin-top: 10px;
        border: 1px solid #333;
    }
    .pick-box.green { border-left: 4px solid #4CAF50; }
    .pick-box.yellow { border-left: 4px solid #FFC107; }
    .pick-box.red { border-left: 4px solid #F44336; }
    .badge-play {
        background-color: #4CAF50;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: bold;
        font-size: 12px;
    }
    .risk-note {
        color: #FF5252;
        font-size: 14px;
        margin-top: 15px;
        font-style: italic;
    }
    .summary-metric {
        background-color: #1E1E1E;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        border: 1px solid #333;
    }
    .form-w { color: #4CAF50; font-weight: bold; }
    .form-d { color: #9E9E9E; font-weight: bold; }
    .form-l { color: #F44336; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# API FETCHING FUNCTIONS (CACHED)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_fixtures(date_str):
    url = f"{API_BASE_URL}/fixtures?date={date_str}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200: return []
    
    data = res.json().get("response", [])
    valid_fixtures = []
    
    for f in data:
        status = f["fixture"]["status"]["short"]
        if status != "NS":
            continue
            
        league_name = f["league"]["name"]
        team_home = f["teams"]["home"]["name"]
        team_away = f["teams"]["away"]["name"]
        
        # Exclude checks
        if any(w.lower() in league_name.lower() for w in EXCLUDE_WORDS): continue
        if any(team_home.endswith(s) for s in EXCLUDE_TEAM_SUFFIXES): continue
        if any(team_away.endswith(s) for s in EXCLUDE_TEAM_SUFFIXES): continue
        
        valid_fixtures.append(f)
        
    return valid_fixtures

@st.cache_data(ttl=3600)
def fetch_odds(date_str):
    odds_dict = {}
    for bookmaker in [32, 34]:
        page = 1
        total_pages = 1
        while page <= total_pages and page <= 21:
            url = f"{API_BASE_URL}/odds?date={date_str}&bookmaker={bookmaker}&page={page}"
            res = requests.get(url, headers=HEADERS)
            if res.status_code != 200: break
            
            data = res.json()
            if not data.get("response"): break
            
            total_pages = data.get("paging", {}).get("total", 1)
            for item in data["response"]:
                fid = item["fixture"]["id"]
                if fid not in odds_dict:
                    odds_dict[fid] = []
                odds_dict[fid].append(item)
            page += 1
    return odds_dict

@st.cache_data(ttl=3600)
def fetch_team_matches(team_id):
    url = f"{API_BASE_URL}/fixtures?team={team_id}&last=15"
    res = requests.get(url, headers=HEADERS)
    return res.json().get("response", []) if res.status_code == 200 else []

@st.cache_data(ttl=3600)
def fetch_h2h(team1, team2):
    url = f"{API_BASE_URL}/fixtures/headtohead?h2h={team1}-{team2}&last=10"
    res = requests.get(url, headers=HEADERS)
    return res.json().get("response", []) if res.status_code == 200 else []

@st.cache_data(ttl=3600)
def fetch_injuries(fixture_id):
    url = f"{API_BASE_URL}/injuries?fixture={fixture_id}"
    res = requests.get(url, headers=HEADERS)
    return res.json().get("response", []) if res.status_code == 200 else []

# ==========================================
# DATA PROCESSING HELPER FUNCTIONS
# ==========================================
def parse_odds(odds_data):
    formatted = []
    for item in odds_data:
        bm_name = item["bookmakers"][0]["name"]
        bets = item["bookmakers"][0]["bets"]
        book_odds = []
        for bet in bets:
            bet_name = bet["name"]
            values = " ".join([f"{v['value']}={v['odd']}" for v in bet["values"]])
            book_odds.append(f"{bet_name}: {values}")
        formatted.append(f"[{bm_name}] " + " | ".join(book_odds))
    return "\n".join(formatted)

def process_matches(matches, main_team_id):
    if not matches:
        return "Nu există date.", "W:0 D:0 L:0 | Meciuri: 0"
        
    details = []
    w, d, l = 0, 0, 0
    gg, over25 = 0, 0
    goals_scored, goals_conceded = 0, 0
    clean_sheets = 0
    
    home_w, home_d, home_l = 0, 0, 0
    home_gg, home_goals_scored, home_goals_conceded = 0, 0, 0
    home_matches_count = 0
    
    for i, m in enumerate(matches[:5]): # Form for last 5
        is_home = m["teams"]["home"]["id"] == main_team_id
        opp_name = m["teams"]["away"]["name"] if is_home else m["teams"]["home"]["name"]
        loc = "H" if is_home else "A"
        
        score_home = m["goals"]["home"]
        score_away = m["goals"]["away"]
        
        if score_home is None or score_away is None: continue
        
        team_goals = score_home if is_home else score_away
        opp_goals = score_away if is_home else score_home
        
        res = "D"
        if team_goals > opp_goals: res = "W"
        elif team_goals < opp_goals: res = "L"
        
        gg_str = "Da" if (score_home > 0 and score_away > 0) else "Nu"
        o25_str = "Da" if (score_home + score_away > 2.5) else "Nu"
        
        details.append(f"{i+1}. vs {opp_name} ({loc}) {team_goals}-{opp_goals} {res} | goluri: {team_goals}M {opp_goals}P | GG:{gg_str} | O2.5:{o25_str}")

    # Stats for all 15
    for m in matches:
        is_home = m["teams"]["home"]["id"] == main_team_id
        score_home = m["goals"]["home"]
        score_away = m["goals"]["away"]
        
        if score_home is None or score_away is None: continue
        
        team_goals = score_home if is_home else score_away
        opp_goals = score_away if is_home else score_home
        
        goals_scored += team_goals
        goals_conceded += opp_goals
        
        if team_goals > opp_goals: w += 1
        elif team_goals < opp_goals: l += 1
        else: d += 1
        
        if score_home > 0 and score_away > 0: gg += 1
        if score_home + score_away > 2.5: over25 += 1
        if opp_goals == 0: clean_sheets += 1
        
        if is_home:
            home_matches_count += 1
            home_goals_scored += team_goals
            home_goals_conceded += opp_goals
            if team_goals > opp_goals: home_w += 1
            elif team_goals < opp_goals: home_l += 1
            else: home_d += 1
            if score_home > 0 and score_away > 0: home_gg += 1

    total = len([m for m in matches if m["goals"]["home"] is not None])
    if total == 0: total = 1
    
    details_str = "\n".join(details)
    summary_form = f"Rezumat forma (ultimele): {w}W {d}D {l}L | GG:{int((gg/total)*100)}% | Over2.5:{int((over25/total)*100)}% | Avg goluri M:{round(goals_scored/total,1)} P:{round(goals_conceded/total,1)}"
    
    stats_str = f"Meciuri: {total} | W:{w} D:{d} L:{l} | GG:{int((gg/total)*100)}% | O2.5:{int((over25/total)*100)}% | Avg goluri M:{round(goals_scored/total,1)} P:{round(goals_conceded/total,1)} | Clean Sheet:{int((clean_sheets/total)*100)}%\n"
    if home_matches_count > 0:
        stats_str += f"Acasă: W:{home_w} D:{home_d} L:{home_l} | GG:{int((home_gg/home_matches_count)*100)}% | Avg goluri M:{round(home_goals_scored/home_matches_count,1)} P:{round(home_goals_conceded/home_matches_count,1)}"
    
    return details_str + "\n" + summary_form, stats_str

def process_h2h(matches):
    if not matches: return "Fara meciuri directe."
    
    details = []
    h_w, a_w, d = 0, 0, 0
    gg, goals = 0, 0
    
    for i, m in enumerate(matches[:5]):
        date = m["fixture"]["date"][:10]
        t1 = m["teams"]["home"]["name"]
        t2 = m["teams"]["away"]["name"]
        s1 = m["goals"]["home"]
        s2 = m["goals"]["away"]
        
        if s1 is None or s2 is None: continue
        
        if s1 > s2: h_w += 1
        elif s2 > s1: a_w += 1
        else: d += 1
        
        goals += (s1 + s2)
        is_gg = "Da" if s1 > 0 and s2 > 0 else "Nu"
        is_o25 = "Da" if (s1+s2) > 2.5 else "Nu"
        if s1 > 0 and s2 > 0: gg += 1
        
        details.append(f"{i+1}. {date}: {t1} {s1}-{s2} {t2} | GG:{is_gg} | O2.5:{is_o25}")
        
    total = len([m for m in matches if m["goals"]["home"] is not None])
    if total == 0: total = 1
    summary = f"Rezumat: {h_w}W gazdă, {d}D, {a_w}W oaspete | GG:{int((gg/total)*100)}% | Avg total goluri: {round(goals/total, 2)}"
    return "\n".join(details) + "\n" + summary

def extract_injuries(injuries_data, team_id):
    team_inj = [i["player"]["name"] for i in injuries_data if i["team"]["id"] == team_id]
    return ", ".join(team_inj) if team_inj else "Niciuna raportată"

# ==========================================
# GEMINI ANALYSIS
# ==========================================
def analyze_match_with_gemini(match_data):
    prompt = f"""
Ești un analist expert de pariuri sportive (Quant). Răspunde în ROMÂNĂ.

Analizează acest meci:
🏟️ {match_data['home_team']} vs {match_data['away_team']}
📅 {match_data['date']}, {match_data['time']}
🏆 {match_data['league']} ({match_data['country']})

📊 DATE DISPONIBILE:

Formă gazdă (ultimele 5): 
{match_data['home_form']}

Formă oaspete (ultimele 5): 
{match_data['away_form']}

H2H (ultimele meciuri directe): 
{match_data['h2h']}

Accidentări gazdă: {match_data['home_inj']}
Accidentări oaspete: {match_data['away_inj']}

Cote Betano/Superbet: 
{match_data['odds']}

Statistici gazdă: 
{match_data['home_stats']}

Statistici oaspete: 
{match_data['away_stats']}

RĂSPUNDE EXACT ÎN ACEST FORMAT JSON (nimic altceva, fara text inainte sau dupa):
{{
  "picks": [
    {{"rank": 1, "market": "NUMELE PARIULUI", "odds": 1.95, "bookmaker": "Betano", "prob": 65, "ev": 13.7, "level": "green", "stake": 3, "reason": "motivul scurt"}},
    {{"rank": 2, "market": "...", "odds": 2.10, "bookmaker": "...", "prob": 55, "ev": 5.0, "level": "yellow", "stake": 2, "reason": "..."}},
    {{"rank": 3, "market": "...", "odds": 1.80, "bookmaker": "...", "prob": 50, "ev": -5.5, "level": "red", "stake": 1, "reason": "..."}}
  ], 
  "risk": "cel mai mare risc al meciului"
}}

REGULI:
- Dă MEREU 3 picks, sortate de la cel mai bun la cel mai slab
- level: "green" = încredere mare, "yellow" = medie, "red" = mică
- prob = probabilitatea ta reală în procente
- ev = prob - (100/odds), calculat de tine
- odds = cota REALĂ din datele de mai sus
- stake = 1-5 unități recomandate
- Cote minim 1.75, maxim 3.00
- Piețe posibile: Over/Under, GG/NG, 1X2, Double Chance, AH, Half Time
- Analizează formă, H2H, accidentări, context liga
- Fii SINCER cu nivelul de încredere
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"code_execution": {}}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096}
    }
    
    res = requests.post(GEMINI_URL, json=payload, timeout=60)
    if res.status_code != 200:
        return None
        
    try:
        parts = res.json()["candidates"][0]["content"]["parts"]
        # With code_execution, Gemini returns multiple parts - collect all text
        text = ""
        for part in parts:
            if "text" in part:
                text += part["text"]
        # Extract JSON using regex to handle markdown blocks
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        return json.loads(text)
    except Exception as e:
        return None

# ==========================================
# MAIN APP
# ==========================================
def main():
    today = datetime.now(RO_TZ)
    today_str = today.strftime('%Y-%m-%d')
    
    st.markdown(f"<h1>🏔️ NORD ALLASKA SUPREME</h1>", unsafe_allow_html=True)
    st.markdown(f"<h4>AI Value Bet Analyzer · Gemini AI + API-Football · {today_str}</h4>", unsafe_allow_html=True)
    st.divider()

    if st.button("🚀 Scanează & Analizează Meciurile de Azi", use_container_width=True):
        
        with st.spinner("Preluare date din API-Football..."):
            fixtures = fetch_fixtures(today_str)
            odds_data = fetch_odds(today_str)
            
        # Filter fixtures that actually have odds
        analyzable_fixtures = [f for f in fixtures if f["fixture"]["id"] in odds_data]
        
        # Limit to 15 for Gemini API tier
        if len(analyzable_fixtures) > 15:
            analyzable_fixtures = analyzable_fixtures[:15]
            
        if not analyzable_fixtures:
            st.warning("Nu s-au găsit meciuri cu cote disponibile pentru astăzi conform filtrelos curente.")
            return
            
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        metrics = {"total_analyzed": len(analyzable_fixtures), "high_conf": 0, "total_picks": 0, "total_ev": 0.0}
        
        for idx, f in enumerate(analyzable_fixtures):
            fid = f["fixture"]["id"]
            home_id = f["teams"]["home"]["id"]
            away_id = f["teams"]["away"]["id"]
            
            status_text.text(f"Analizez ({idx+1}/{len(analyzable_fixtures)}): {f['teams']['home']['name']} vs {f['teams']['away']['name']}...")
            
            # Fetch additional data
            f_odds = odds_data[fid]
            home_matches = fetch_team_matches(home_id)
            away_matches = fetch_team_matches(away_id)
            h2h_matches = fetch_h2h(home_id, away_id)
            injuries = fetch_injuries(fid)
            
            # Process data
            home_form, home_stats = process_matches(home_matches, home_id)
            away_form, away_stats = process_matches(away_matches, away_id)
            h2h_str = process_h2h(h2h_matches)
            
            dt = datetime.fromisoformat(f["fixture"]["date"]).astimezone(RO_TZ)
            
            match_data = {
                "home_team": f["teams"]["home"]["name"],
                "away_team": f["teams"]["away"]["name"],
                "date": dt.strftime("%d-%m-%Y"),
                "time": dt.strftime("%H:%M"),
                "league": f["league"]["name"],
                "country": f["league"]["country"],
                "home_form": home_form,
                "home_stats": home_stats,
                "away_form": away_form,
                "away_stats": away_stats,
                "h2h": h2h_str,
                "home_inj": extract_injuries(injuries, home_id),
                "away_inj": extract_injuries(injuries, away_id),
                "odds": parse_odds(f_odds)
            }
            
            ai_result = analyze_match_with_gemini(match_data)
            if ai_result:
                results.append((match_data, ai_result))
                metrics["total_picks"] += len(ai_result.get("picks", []))
                for p in ai_result.get("picks", []):
                    metrics["total_ev"] += p.get("ev", 0)
                    if p.get("level") == "green":
                        metrics["high_conf"] += 1
            
            progress_bar.progress((idx + 1) / len(analyzable_fixtures))
            
        status_text.empty()
        progress_bar.empty()
        
        # Display Summary
        avg_ev = metrics["total_ev"] / metrics["total_picks"] if metrics["total_picks"] > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"<div class='summary-metric'><h3>🎯 {metrics['total_analyzed']}</h3><p>Meciuri Analizate</p></div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='summary-metric'><h3>🟢 {metrics['high_conf']}</h3><p>Încredere MARE</p></div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div class='summary-metric'><h3>⚽ {metrics['total_picks']}</h3><p>Total Picks</p></div>", unsafe_allow_html=True)
        with col4:
            st.markdown(f"<div class='summary-metric'><h3>📈 {round(avg_ev, 2)}%</h3><p>Avg EV</p></div>", unsafe_allow_html=True)
            
        st.write("---")
        
        # Display Matches
        for match, analysis in results:
            picks = analysis.get("picks", [])
            risk = analysis.get("risk", "Niciun risc major specificat.")
            
            html_card = f"""
            <div class="match-card">
                <h4>{match['time']} | {match['home_team']} vs {match['away_team']}</h4>
                <p style="color: #AAA;">{match['country']} - {match['league']}</p>
            """
            
            for p in picks:
                level = p.get('level', 'yellow')
                lvl_icon = "🟢" if level == "green" else "🟡" if level == "yellow" else "🔴"
                rank = p.get('rank', '-')
                
                badge = "<span class='badge-play'>🎯 JOACĂ</span>" if rank == 1 else ""
                
                html_card += f"""
                <div class="pick-box {level}">
                    <strong>Pick #{rank} {badge}</strong><br>
                    <span style="font-size:18px;">{lvl_icon} {p.get('market', '-')}</span> @ <strong>{p.get('odds', '-')}</strong> ({p.get('bookmaker', '-')})<br>
                    <span style="font-size:14px; color:#CCC;">Prob: {p.get('prob', '-')}%, EV: {p.get('ev', '-')}%, Stake: {p.get('stake', '-')}u</span><br>
                    <p style="font-size:13px; margin-top:5px;"><i>{p.get('reason', '-')}</i></p>
                </div>
                """
                
            html_card += f"<div class='risk-note'>⚠️ Risc Principal: {risk}</div>"
            html_card += "</div>"
            
            st.markdown(html_card, unsafe_allow_html=True)
            
    st.markdown("<br><hr><center><small>Nord Allaska Supreme © 2026 | Date furnizate de API-Football | AI-Powered by Gemini 3.6 Flash</small></center>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
