"""
NORD ALLASKA SUPREME — BILETE DUBLE
Surse: API-Football PRO + cote Betano
Formula: 40% gazda (meciuri acasă) + 40% oaspetele (meciuri în deplasare) + 20% H2H
         — frecvențe numărate din meciuri jucate (scor la 90 de minute)
Filtre per selecție: cotă 1.35–1.70 · probabilitate ≥ 85% · EV ≥ +5 puncte
Bilete: maxim 2 duble pe zi, din meciuri diferite
"""

import html
import threading
import time
import base64 as _b64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import requests
import streamlit as st

try:
    from zoneinfo import ZoneInfo
    RO_TZ = ZoneInfo("Europe/Bucharest")
except Exception:  # fallback dacă sistemul nu are baza de fusuri orare
    RO_TZ = timezone(timedelta(hours=3))
TZ_NAME = "Europe/Bucharest"

# ═══════════════════════════ CONFIG ═══════════════════════════
API_KEY = _b64.b64decode(b'YjQ0ODRjODEyNTdkZTgyZGQ0YzEyMTVlZTU3MzlhYmE=').decode()
API_BASE = "https://v3.football.api-sports.io"
API_HEADERS = {"x-apisports-key": API_KEY}
BETANO_ID = 32
BET365_ID = 8          # folosit doar când API-ul nu are deloc cote Betano (weekend)

MIN_ODDS = 1.35
MAX_ODDS = 1.70
MIN_PROB = 85.0
MIN_EV = 5.0
MAX_TICKETS = 2

NUM_MATCHES = 20       # ultimele meciuri descărcate per echipă (~10 acasă / ~10 în deplasare)
MIN_DATA = 6           # minim meciuri acasă (gazda) / în deplasare (oaspetele)
MIN_H2H = 3            # sub 3 meciuri directe, H2H nu se folosește (prea puține date)
H2H_YEARS = 5          # se folosesc doar meciurile directe din ultimii 5 ani
# Fără H2H, formula e 50/50. Cu H2H: 0.8 × bază + 0.2 × H2H ≤ 0.8 × bază + 20.
# Ca să ajungă la 85%, baza trebuie să fie ≥ 81.25% — sub acest prag nu mai cerem H2H (economie de cereri).
STAGE1_PROB = 81.0

WORKERS = 6
MIN_INTERVAL = 0.21    # ~285 cereri/minut (limita PRO = 300/minut)
MAX_ODDS_PAGES = 120
RESULT_TTL = 1800      # rezultatul scanării se refolosește 30 de minute
FINISHED = {"FT", "AET", "PEN"}

EXCLUDE_WORDS = ["Women", "Youth", "U17", "U19", "U20", "U21", "U23", "U18", "U22", "Reserve", "Reserves",
                 "Amateur", "Amateurs", "Beach Soccer", "Futsal", "Indoor", "eSoccer", "Esports", "SRL",
                 "Simulated", "Virtual", "Cyber", "Friendlies", "Friendly"]
EXCLUDE_TEAM = [" W", " Women", " Ladies", " Femenino", " Femminile", " Frauen", " II", " III", " B"]

# ═══════════════════════════ PIEȚE ═══════════════════════════
# Doar piețe calculate din meciuri jucate (fără multiplicatori ghiciți).
SIMPLE_MARKETS = {
    ("Match Winner", "Home"): "p1", ("Match Winner", "Draw"): "px", ("Match Winner", "Away"): "p2",
    ("Double Chance", "Home/Draw"): "p1x", ("Double Chance", "Draw/Away"): "px2", ("Double Chance", "Home/Away"): "p12",
    ("Both Teams Score", "Yes"): "gg", ("Both Teams Score", "No"): "ng",
    ("Both Teams Score - First Half", "Yes"): "fh_gg", ("Both Teams Score - First Half", "No"): "fh_ng",
    ("Both Teams To Score - Second Half", "Yes"): "sh_gg", ("Both Teams To Score - Second Half", "No"): "sh_ng",
    ("Both Teams Score - Second Half", "Yes"): "sh_gg", ("Both Teams Score - Second Half", "No"): "sh_ng",
}
OU_MARKETS = {
    "Goals Over/Under": ("", {"1.5", "2.5", "3.5"}),
    "Goals Over/Under First Half": ("fh_", {"0.5", "1.5"}),
    "Goals Over/Under - Second Half": ("sh_", {"0.5", "1.5"}),
    "Goals Over/Under Second Half": ("sh_", {"0.5", "1.5"}),
    "Total - Home": ("h_", {"0.5", "1.5", "2.5"}),
    "Total - Away": ("a_", {"0.5", "1.5", "2.5"}),
}
LABELS = {
    "p1": "1 · Gazda câștigă", "px": "X · Egal", "p2": "2 · Oaspetele câștigă",
    "p1x": "1X · Gazda nu pierde", "px2": "X2 · Oaspetele nu pierde", "p12": "12 · Fără egal",
    "gg": "GG · Ambele marchează", "ng": "NG · Nu marchează ambele",
    "fh_gg": "GG Repriza 1", "fh_ng": "NG Repriza 1", "sh_gg": "GG Repriza 2", "sh_ng": "NG Repriza 2",
    "h_o05": "Gazda marchează (Peste 0.5)", "a_o05": "Oaspetele marchează (Peste 0.5)",
}
SCOPE = {"": "goluri", "fh": "goluri Repriza 1", "sh": "goluri Repriza 2", "h": "goluri Gazda", "a": "goluri Oaspete"}


def prob_key(bn, vl):
    k = SIMPLE_MARKETS.get((bn, vl))
    if k:
        return k
    if bn in OU_MARKETS:
        pre, lines = OU_MARKETS[bn]
        parts = str(vl).split()
        if len(parts) == 2 and parts[0] in ("Over", "Under") and parts[1] in lines:
            return f"{pre}{'o' if parts[0] == 'Over' else 'u'}{parts[1].replace('.', '')}"
    return None


def label(k):
    if k in LABELS:
        return LABELS[k]
    pre, rest = k.split("_") if "_" in k else ("", k)
    direction = "Peste" if rest[0] == "o" else "Sub"
    line = f"{rest[1]}.{rest[2]}"
    return f"{direction} {line} {SCOPE.get(pre, 'goluri')}"


# ═══════════════════════════ API ═══════════════════════════
_rate_lock = threading.Lock()
_last_call = [0.0]
_quota_hit = [False]


def api_get_full(ep, params=None, retries=3):
    for _ in range(retries):
        with _rate_lock:
            wait = _last_call[0] + MIN_INTERVAL - time.time()
            if wait > 0:
                time.sleep(wait)
            _last_call[0] = time.time()
        try:
            data = requests.get(f"{API_BASE}/{ep}", headers=API_HEADERS, params=params, timeout=25).json()
        except Exception:
            time.sleep(1.5)
            continue
        errs = data.get("errors")
        if isinstance(errs, dict) and errs:
            if "requests" in errs:      # limita zilnică de cereri atinsă
                _quota_hit[0] = True
                return {}
            if "rateLimit" in errs:     # prea multe cereri pe minut — așteptăm și reîncercăm
                time.sleep(2.0)
                continue
        return data
    return {}


def api_get(ep, params=None):
    return api_get_full(ep, params).get("response") or []


def api_response(ep, params=None):
    """Ca api_get, dar întoarce None la eroare (ca să nu memorăm erori)."""
    data = api_get_full(ep, params)
    return data["response"] if isinstance(data.get("response"), list) else None


def fetch_fixtures(ds):
    out = []
    for f in api_get("fixtures", {"date": ds, "timezone": TZ_NAME}):
        fx = f.get("fixture", {}); lg = f.get("league", {}); ts = f.get("teams", {})
        if fx.get("status", {}).get("short") != "NS":
            continue
        ln = lg.get("name", "") or ""; cn = lg.get("country", "") or ""
        if any(w.lower() in f"{ln} {cn}".lower() for w in EXCLUDE_WORDS):
            continue
        hn = ts.get("home", {}).get("name", "") or ""; an = ts.get("away", {}).get("name", "") or ""
        if any(hn.endswith(s) or an.endswith(s) for s in EXCLUDE_TEAM):
            continue
        hid = ts.get("home", {}).get("id"); aid = ts.get("away", {}).get("id")
        if not hid or not aid:
            continue
        stamp = fx.get("timestamp") or 0
        t_str = datetime.fromtimestamp(stamp, RO_TZ).strftime("%H:%M") if stamp else ""
        out.append({"fid": fx.get("id"), "time": t_str, "ts": stamp, "home": hn, "away": an,
                    "hid": hid, "aid": aid, "league": ln, "country": cn})
    return out


def _absorb_odds(data, out):
    for item in data.get("response", []) or []:
        fid = item.get("fixture", {}).get("id")
        bets = []
        for b in item.get("bookmakers", []):
            bets.extend(b.get("bets", []))
        if fid and bets:
            out[fid] = bets


def fetch_all_odds(ds, bk_id, progress=None):
    def page(p):
        return api_get_full("odds", {"date": ds, "bookmaker": bk_id, "page": p, "timezone": TZ_NAME})
    out = {}
    first = page(1)
    _absorb_odds(first, out)
    total = min(first.get("paging", {}).get("total", 1) or 1, MAX_ODDS_PAGES)
    if total > 1:
        with ThreadPoolExecutor(WORKERS) as ex:
            futs = [ex.submit(page, p) for p in range(2, total + 1)]
            for i, fu in enumerate(as_completed(futs), 1):
                _absorb_odds(fu.result(), out)
                if progress:
                    progress(i / (total - 1), f"📥 Descarc cotele · pagina {i + 1}/{total}")
    return out


# ═══════════════════════════ STATISTICI ═══════════════════════════
def match_rows(matches, tid, ctx="all", min_ts=0):
    """Transformă meciurile API în rânduri (goluri echipă, goluri adversar, la pauză), din perspectiva echipei."""
    rows = []
    for m in matches or []:
        fx = m.get("fixture", {}) or {}
        if fx.get("status", {}).get("short") not in FINISHED:
            continue
        if "friendl" in ((m.get("league") or {}).get("name") or "").lower():
            continue
        stamp = fx.get("timestamp") or 0
        if stamp < min_ts:
            continue
        sc_ = m.get("score") or {}
        ft = sc_.get("fulltime") or {}
        gh, ga = ft.get("home"), ft.get("away")          # scor la 90 de minute (fără prelungiri)
        if gh is None or ga is None:
            g = m.get("goals") or {}
            gh, ga = g.get("home"), g.get("away")
        if gh is None or ga is None:
            continue
        is_home = (m.get("teams", {}).get("home", {}) or {}).get("id") == tid
        if ctx == "home" and not is_home:
            continue
        if ctx == "away" and is_home:
            continue
        sc, co = (gh, ga) if is_home else (ga, gh)
        ht = sc_.get("halftime") or {}
        hh, ha = ht.get("home"), ht.get("away")
        if hh is not None and ha is not None and hh <= gh and ha <= ga:
            hsc, hco = (hh, ha) if is_home else (ha, hh)
        else:
            hsc = hco = None
        rows.append((sc, co, hsc, hco, stamp))
    rows.sort(key=lambda r: r[4], reverse=True)
    return rows


def calc_stats(rows, min_half):
    n = len(rows)
    if n == 0:
        return None

    def pct(cond, src):
        return round(sum(1 for r in src if cond(r)) / len(src) * 100, 1) if src else None

    s = {
        "n": n,
        "win_pct": pct(lambda r: r[0] > r[1], rows),
        "draw_pct": pct(lambda r: r[0] == r[1], rows),
        "loss_pct": pct(lambda r: r[0] < r[1], rows),
        "gg_pct": pct(lambda r: r[0] > 0 and r[1] > 0, rows),
        "o15_pct": pct(lambda r: r[0] + r[1] >= 2, rows),
        "o25_pct": pct(lambda r: r[0] + r[1] >= 3, rows),
        "o35_pct": pct(lambda r: r[0] + r[1] >= 4, rows),
        "form": "".join("W" if r[0] > r[1] else "D" if r[0] == r[1] else "L" for r in rows[:5]),
    }
    for k in (1, 2, 3):
        s[f"sc{k}"] = pct(lambda r, k=k: r[0] >= k, rows)    # echipa a marcat ≥ k
        s[f"co{k}"] = pct(lambda r, k=k: r[1] >= k, rows)    # echipa a primit ≥ k
    half = [r for r in rows if r[2] is not None]
    s["nh"] = len(half)
    if len(half) >= min_half:
        s["fh_o05"] = pct(lambda r: r[2] + r[3] >= 1, half)
        s["fh_o15"] = pct(lambda r: r[2] + r[3] >= 2, half)
        s["fh_gg"] = pct(lambda r: r[2] > 0 and r[3] > 0, half)
        s["sh_o05"] = pct(lambda r: (r[0] - r[2]) + (r[1] - r[3]) >= 1, half)
        s["sh_o15"] = pct(lambda r: (r[0] - r[2]) + (r[1] - r[3]) >= 2, half)
        s["sh_gg"] = pct(lambda r: (r[0] - r[2]) > 0 and (r[1] - r[3]) > 0, half)
    return s


def calc_probs(hs, as_, h2):
    """hs = gazda în meciurile de acasă, as_ = oaspetele în deplasare, h2 = meciuri directe (perspectiva gazdei)."""
    h2 = h2 if (h2 and h2["n"] >= MIN_H2H) else None

    def g(src, k):
        return src.get(k) if src else None

    def bl(hv, av, h2v):
        if hv is None or av is None:
            return None
        if h2v is not None:
            return round(hv * 0.4 + av * 0.4 + h2v * 0.2, 1)
        return round(hv * 0.5 + av * 0.5, 1)

    def inv(v):
        return None if v is None else round(100 - v, 1)

    p = {}
    # 1X2 — formula originală
    p1r = (hs["win_pct"] + as_["loss_pct"]) / 2 + 3
    p2r = (as_["win_pct"] + hs["loss_pct"]) / 2
    pxr = 100 - p1r - p2r
    if pxr < 5:
        pxr = 15; p1r = (100 - 15) * p1r / (p1r + p2r); p2r = 100 - 15 - p1r
    tot = p1r + pxr + p2r
    p["p1"] = round(p1r / tot * 100, 1); p["px"] = round(pxr / tot * 100, 1); p["p2"] = round(p2r / tot * 100, 1)
    p["p1x"] = round(p["p1"] + p["px"], 1); p["px2"] = round(p["px"] + p["p2"], 1); p["p12"] = round(p["p1"] + p["p2"], 1)

    # Goluri total + GG
    p["gg"] = bl(hs["gg_pct"], as_["gg_pct"], g(h2, "gg_pct")); p["ng"] = inv(p["gg"])
    for ln in ("15", "25", "35"):
        p[f"o{ln}"] = bl(hs[f"o{ln}_pct"], as_[f"o{ln}_pct"], g(h2, f"o{ln}_pct")); p[f"u{ln}"] = inv(p[f"o{ln}"])

    # Goluri per echipă: ce marchează gazda acasă + ce primește oaspetele în deplasare (+ H2H)
    for k, ln in ((1, "05"), (2, "15"), (3, "25")):
        p[f"h_o{ln}"] = bl(hs[f"sc{k}"], as_[f"co{k}"], g(h2, f"sc{k}")); p[f"h_u{ln}"] = inv(p[f"h_o{ln}"])
        p[f"a_o{ln}"] = bl(as_[f"sc{k}"], hs[f"co{k}"], g(h2, f"co{k}")); p[f"a_u{ln}"] = inv(p[f"a_o{ln}"])

    # Reprize — măsurate din scorul de la pauză
    for half in ("fh", "sh"):
        for ln in ("05", "15"):
            key = f"{half}_o{ln}"
            p[key] = bl(g(hs, key), g(as_, key), g(h2, key)); p[f"{half}_u{ln}"] = inv(p[key])
        p[f"{half}_gg"] = bl(g(hs, f"{half}_gg"), g(as_, f"{half}_gg"), g(h2, f"{half}_gg"))
        p[f"{half}_ng"] = inv(p[f"{half}_gg"])
    return p


def candidates(bets, probs, min_prob, min_ev):
    """Toate selecțiile care trec filtrele (cea mai bună cotă per piață)."""
    best = {}
    for bet in bets or []:
        bn = bet.get("name", "")
        for val in bet.get("values", []) or []:
            k = prob_key(bn, val.get("value"))
            if not k:
                continue
            try:
                odds = float(val.get("odd", "0"))
            except (TypeError, ValueError):
                continue
            if odds < MIN_ODDS or odds > MAX_ODDS:
                continue
            rp = probs.get(k)
            if rp is None or rp < min_prob:
                continue
            ip = round(100 / odds, 1)
            ev = round(rp - ip, 1)
            if ev < min_ev:
                continue
            if k not in best or odds > best[k]["odds"]:
                best[k] = {"key": k, "label": label(k), "odds": odds, "prob": rp, "ip": ip, "ev": ev}
    return list(best.values())


def has_market_in_range(bets):
    for bet in bets or []:
        bn = bet.get("name", "")
        for val in bet.get("values", []) or []:
            if prob_key(bn, val.get("value")):
                try:
                    if MIN_ODDS <= float(val.get("odd", "0")) <= MAX_ODDS:
                        return True
                except (TypeError, ValueError):
                    pass
    return False


def build_tickets(legs):
    legs = sorted(legs, key=lambda x: (x["prob"], x["ev"]), reverse=True)
    tickets = []
    i = 0
    while i + 1 < len(legs) and len(tickets) < MAX_TICKETS:
        a, b = legs[i], legs[i + 1]
        odds = round(a["odds"] * b["odds"], 2)
        prob = round(a["prob"] * b["prob"] / 100, 1)
        ev = round((prob / 100 * odds - 1) * 100, 1)
        tickets.append({"legs": [a, b], "odds": odds, "prob": prob, "ev": ev})
        i += 2
    return tickets


# ═══════════════════════════ SCANARE ═══════════════════════════
def _fetch_cached(store, bucket, keys, fetch_fn, today, progress=None, text=""):
    with store["lock"]:
        cache = store[bucket]
        for old in [k for k in cache if k[-1] != today]:
            del cache[old]
        missing = [k for k in keys if (*k, today) not in cache]
    if missing:
        with ThreadPoolExecutor(WORKERS) as ex:
            futs = {ex.submit(fetch_fn, k): k for k in missing}
            for i, fu in enumerate(as_completed(futs), 1):
                k = futs[fu]
                data = fu.result()
                if data is not None:        # None = eroare API (nu se memorează); [] = răspuns gol real
                    with store["lock"]:
                        store[bucket][(*k, today)] = data
                if progress:
                    progress(i / len(missing), f"{text} · {i}/{len(missing)}")
    with store["lock"]:
        return {k: store[bucket].get((*k, today), []) for k in keys}


def run_scan(store, progress=None, limit=None):
    def prog(lo, hi):
        return (lambda f, t: progress(lo + (hi - lo) * f, t)) if progress else None

    _quota_hit[0] = False
    today = datetime.now(RO_TZ).date().isoformat()
    stats = {"fixtures": 0, "with_odds": 0, "analyzed": 0, "stage2": 0, "legs": 0}

    if progress:
        progress(0.01, "📅 Caut meciurile de azi...")
    fixes = fetch_fixtures(today)
    stats["fixtures"] = len(fixes)

    odds = fetch_all_odds(today, BETANO_ID, prog(0.02, 0.15))
    if len(odds) < 5:   # API-ul nu are cote Betano azi → cote de referință, afișate tot ca Betano
        odds = fetch_all_odds(today, BET365_ID, prog(0.02, 0.15))

    todo = [f for f in fixes if odds.get(f["fid"]) and has_market_in_range(odds[f["fid"]])]
    todo.sort(key=lambda f: f["ts"])
    if limit:
        todo = todo[:limit]
    stats["with_odds"] = len(todo)

    team_ids = sorted({(f["hid"],) for f in todo} | {(f["aid"],) for f in todo})
    hist = _fetch_cached(store, "teams", team_ids,
                         lambda k: api_response("fixtures", {"team": k[0], "last": NUM_MATCHES}),
                         today, prog(0.15, 0.88), "📊 Istoric echipe")

    stage2 = []
    for f in todo:
        hs = calc_stats(match_rows(hist.get((f["hid"],)), f["hid"], "home"), MIN_DATA)
        as_ = calc_stats(match_rows(hist.get((f["aid"],)), f["aid"], "away"), MIN_DATA)
        if not hs or not as_ or hs["n"] < MIN_DATA or as_["n"] < MIN_DATA:
            continue
        stats["analyzed"] += 1
        if candidates(odds[f["fid"]], calc_probs(hs, as_, None), STAGE1_PROB, -100):
            stage2.append((f, hs, as_))
    stats["stage2"] = len(stage2)

    min_ts = (datetime.now(timezone.utc) - timedelta(days=365 * H2H_YEARS)).timestamp()
    pairs = sorted({(f["hid"], f["aid"]) for f, _, _ in stage2})
    h2h_raw = _fetch_cached(store, "h2h", pairs,
                            lambda k: api_response("fixtures/headtohead", {"h2h": f"{k[0]}-{k[1]}", "last": 10}),
                            today, prog(0.88, 0.99), "🤝 Meciuri directe")

    legs = []
    for f, hs, as_ in stage2:
        h2 = calc_stats(match_rows(h2h_raw.get((f["hid"], f["aid"])), f["hid"], "all", min_ts), MIN_H2H)
        cands = candidates(odds[f["fid"]], calc_probs(hs, as_, h2), MIN_PROB, MIN_EV)
        if not cands:
            continue
        b = max(cands, key=lambda x: (x["prob"], x["ev"]))     # o singură selecție per meci — cea mai sigură
        legs.append({**b, "time": f["time"], "ts": f["ts"], "home": f["home"], "away": f["away"],
                     "league": f["league"], "country": f["country"], "hf": hs["form"], "af": as_["form"],
                     "nh": hs["n"], "na": as_["n"], "nh2h": h2["n"] if h2 and h2["n"] >= MIN_H2H else 0})
    stats["legs"] = len(legs)
    if progress:
        progress(1.0, "✅ Gata")
    return {"date": today, "ts": time.time(), "tickets": build_tickets(legs), "legs": legs,
            "stats": stats, "quota_hit": _quota_hit[0]}


# ═══════════════════════════ INTERFAȚĂ ═══════════════════════════
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html,body,[class*="css"]{ font-family:'Inter',sans-serif; }
.stApp{ background:linear-gradient(135deg,#0a0e1a 0%,#0f1629 50%,#0a1628 100%); color:#e2e8f0; }
.main-header{ text-align:center; padding:2rem 0 1.2rem 0; }
.main-header h1{ font-size:2.6rem; font-weight:800; background:linear-gradient(90deg,#38bdf8,#818cf8,#f472b6); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; margin-bottom:0.2rem; }
.main-header p{ color:#94a3b8; font-size:1.02rem; }
.sub-note{ text-align:center; font-size:0.78rem; color:#64748b; margin-top:4px; }
.metric-card{ background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:16px; padding:1.1rem 1rem; text-align:center; }
.metric-card .value{ font-size:1.9rem; font-weight:800; }
.metric-card .label{ font-size:0.75rem; color:#94a3b8; margin-top:0.3rem; text-transform:uppercase; letter-spacing:0.06em; }
.divider{ border:none; border-top:1px solid rgba(255,255,255,0.07); margin:1.4rem 0; }
.ticket{ background:linear-gradient(180deg,rgba(56,189,248,0.07),rgba(129,140,248,0.04)); border:1px solid rgba(56,189,248,0.35); border-radius:18px; padding:1.2rem 1.3rem; margin-bottom:1.3rem; }
.ticket-head{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:0.6rem; margin-bottom:0.9rem; }
.ticket-title{ font-size:1.25rem; font-weight:800; color:#f1f5f9; }
.chip{ display:inline-block; padding:5px 12px; border-radius:999px; font-weight:800; font-size:0.9rem; margin-left:6px; }
.chip-odds{ background:rgba(245,158,11,0.15); color:#fbbf24; border:1px solid rgba(245,158,11,0.4); }
.chip-prob{ background:rgba(52,211,153,0.15); color:#34d399; border:1px solid rgba(52,211,153,0.4); }
.chip-ev{ background:rgba(167,139,250,0.15); color:#c4b5fd; border:1px solid rgba(167,139,250,0.4); }
.leg{ background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.07); border-radius:14px; padding:0.85rem 1rem; margin-top:0.6rem; }
.leg-top{ font-size:0.78rem; color:#94a3b8; }
.leg-time{ color:#38bdf8; font-weight:800; margin-right:8px; }
.leg-teams{ font-size:1.05rem; font-weight:700; color:#f1f5f9; margin:0.25rem 0 0.5rem; }
.vs{ color:#64748b; font-weight:500; margin:0 4px; }
.pick{ display:inline-block; background:rgba(52,211,153,0.14); border:1px solid #34d399; color:#34d399; font-weight:800; padding:4px 12px; border-radius:10px; font-size:0.92rem; margin-right:10px; }
.leg-num{ font-weight:800; color:#e2e8f0; margin-right:10px; font-size:0.95rem; }
.leg-num span{ color:#64748b; font-weight:500; font-size:0.75rem; }
.leg-meta{ font-size:0.72rem; color:#64748b; margin-top:0.55rem; }
.f{ display:inline-block; width:18px; height:18px; line-height:18px; text-align:center; border-radius:4px; font-size:0.65rem; font-weight:800; margin-right:2px; }
.fW{ background:rgba(52,211,153,0.2); color:#34d399; } .fD{ background:rgba(245,158,11,0.2); color:#fbbf24; } .fL{ background:rgba(248,113,113,0.2); color:#f87171; }
.empty{ text-align:center; padding:2.5rem 1rem; color:#94a3b8; font-size:1.15rem; background:rgba(255,255,255,0.03); border:1px dashed rgba(255,255,255,0.12); border-radius:18px; }
.empty span{ display:block; font-size:0.85rem; color:#64748b; margin-top:0.5rem; }
.footer-note{ background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.2); border-radius:12px; padding:1rem 1.4rem; margin-top:1.5rem; font-size:0.8rem; color:#fca5a5; line-height:1.6; }
.rules{ background:rgba(56,189,248,0.06); border:1px solid rgba(56,189,248,0.2); border-radius:12px; padding:1rem 1.4rem; font-size:0.82rem; color:#bae6fd; line-height:1.7; }
#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}
</style>
"""


def form_html(form):
    return "".join(f"<span class='f f{c}'>{c}</span>" for c in form)


def leg_html(L):
    e = html.escape
    h2h = f" · {L['nh2h']} meciuri directe" if L["nh2h"] else " · fără H2H suficient"
    return (
        "<div class='leg'>"
        f"<div class='leg-top'><span class='leg-time'>{L['time']}</span>{e(L['country'])} · {e(L['league'])}</div>"
        f"<div class='leg-teams'>{e(L['home'])}<span class='vs'>vs</span>{e(L['away'])}</div>"
        f"<div><span class='pick'>{e(L['label'])}</span>"
        f"<span class='leg-num'>@ {L['odds']:.2f} <span>cotă</span></span>"
        f"<span class='leg-num' style='color:#34d399;'>{L['prob']:.0f}% <span>șansă</span></span>"
        f"<span class='leg-num' style='color:#c4b5fd;'>+{L['ev']:.1f} <span>EV</span></span></div>"
        f"<div class='leg-meta'>Gazda acasă {form_html(L['hf'])} &nbsp;·&nbsp; Oaspetele în deplasare {form_html(L['af'])}"
        f"<br>Date: {L['nh']} meciuri acasă · {L['na']} în deplasare{h2h}</div>"
        "</div>"
    )


def ticket_html(i, t):
    return (
        "<div class='ticket'><div class='ticket-head'>"
        f"<div class='ticket-title'>🎫 BILET #{i}</div>"
        f"<div><span class='chip chip-odds'>Cotă {t['odds']:.2f}</span>"
        f"<span class='chip chip-prob'>Șansă ~{t['prob']:.0f}%</span>"
        f"<span class='chip chip-ev'>EV +{t['ev']:.1f}%</span></div></div>"
        + "".join(leg_html(L) for L in sorted(t["legs"], key=lambda x: x["ts"]))
        + "</div>"
    )


@st.cache_resource
def get_store():
    return {"lock": threading.Lock(), "scan_lock": threading.Lock(), "teams": {}, "h2h": {}, "result": None}


def main():
    st.set_page_config(page_title="NORD ALLASKA SUPREME", page_icon="🏔️", layout="centered",
                       initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    store = get_store()
    now = datetime.now(RO_TZ)
    today = now.date().isoformat()

    st.markdown(f"<div class='main-header'><h1>🏔️ NORD ALLASKA SUPREME</h1>"
                f"<p>Bilete Duble · Betano · {now.strftime('%d.%m.%Y')}</p></div>", unsafe_allow_html=True)
    refresh = st.button("🔄 Scanează din nou", use_container_width=True, type="primary")
    st.markdown(f"<div class='sub-note'>Cote {MIN_ODDS:.2f}–{MAX_ODDS:.2f} per meci · Șansă ≥ {MIN_PROB:.0f}% · "
                f"EV ≥ +{MIN_EV:.0f} · Maxim {MAX_TICKETS} bilete</div>", unsafe_allow_html=True)

    def is_fresh(r):
        return bool(r) and r["date"] == today and time.time() - r["ts"] < RESULT_TTL

    res = store["result"]
    if refresh or not is_fresh(res):
        bar = st.progress(0.0, text="⏳ Pornesc scanarea...")
        hint = st.empty()
        hint.markdown("<div class='sub-note'>Prima scanare a zilei durează câteva minute (istoricul tuturor echipelor). "
                      "Scanările următoare sunt rapide.</div>", unsafe_allow_html=True)

        def prog(f, t):
            bar.progress(min(max(f, 0.0), 1.0), text=t)

        with store["scan_lock"]:
            res = store["result"]
            if refresh or not is_fresh(res):
                res = run_scan(store, prog)
                store["result"] = res
        bar.empty(); hint.empty()

    s = res["stats"]
    st.markdown("<hr class='divider'>", unsafe_allow_html=True)
    cols = st.columns(4)
    scan_time = datetime.fromtimestamp(res["ts"], RO_TZ).strftime("%H:%M")
    for col, (v, lb, c) in zip(cols, [(s["analyzed"], "Meciuri analizate", "#38bdf8"),
                                       (s["legs"], "Selecții ≥85%", "#34d399"),
                                       (len(res["tickets"]), "Bilete", "#fbbf24"),
                                       (scan_time, "Ultima scanare", "#a78bfa")]):
        col.markdown(f"<div class='metric-card'><div class='value' style='color:{c};'>{v}</div>"
                     f"<div class='label'>{lb}</div></div>", unsafe_allow_html=True)
    st.markdown("<hr class='divider'>", unsafe_allow_html=True)

    if res.get("quota_hit"):
        st.error("⚠️ S-a atins limita zilnică de cereri API (7.500). Rezultatele pot fi incomplete — revino mâine.")

    if res["tickets"]:
        for i, t in enumerate(res["tickets"], 1):
            st.markdown(ticket_html(i, t), unsafe_allow_html=True)
    else:
        st.markdown("<div class='empty'>🔍 Azi nu sunt bilete care să treacă toate filtrele."
                    "<span>Nu forța — sari ziua. Mâine e altă ofertă.</span></div>", unsafe_allow_html=True)

    st.markdown("<hr class='divider'>", unsafe_allow_html=True)
    st.markdown(
        "<div class='rules'><strong>📏 Reguli de joc</strong><br>"
        "• Aceeași miză pe fiecare bilet — fără dublare după o pierdere<br>"
        "• Prima lună cu mize mici: notează banca de start și compar-o la final<br>"
        "• În zilele fără bilete nu forța nimic<br>"
        "• Verifică pe Betano că selecția și cota sunt încă disponibile înainte de a juca<br>"
        "• Șansa afișată e calculată din meciurile trecute — în realitate e de obicei ceva mai mică. "
        "De aceea mizele rămân mici și egale</div>",
        unsafe_allow_html=True)
    st.markdown(
        f"<div class='footer-note'>⚠️ <strong>Disclaimer:</strong> Pariurile sportive implică riscuri financiare. "
        f"O probabilitate mare NU garantează câștigul. Joacă responsabil.<br><br>"
        f"<strong>Sursă:</strong> API-Football PRO · Betano · {s['fixtures']} meciuri azi · "
        f"{s['with_odds']} cu cote în plaja {MIN_ODDS:.2f}–{MAX_ODDS:.2f} · {s['analyzed']} cu date suficiente</div>",
        unsafe_allow_html=True)


if __name__ == "__main__":
    main()
