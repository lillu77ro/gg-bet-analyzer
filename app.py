"""
NORD ALLASKA SUPREME — BILETE DUBLE v2
Surse: API-Football PRO + cote Betano
Formula: 40% gazda (meciuri acasă) + 40% oaspetele (meciuri în deplasare) + 20% H2H
         — frecvențe numărate din meciuri jucate (scor la 90 de minute și la pauză)
Reguli automate per selecție:
  • cotă 1.35–1.70 · șansă ≥ 85% · EV ≥ +5
  • ambele echipe confirmă: gazda ≥ 80% ȘI oaspetele ≥ 80%
  • forma recentă confirmă: minim 4 din ultimele 5 meciuri, la fiecare echipă
  • corecție pentru puține date (7 din 7 nu mai înseamnă 100%)
  • H2H, dacă există, nu contrazice (≥ 60%)
  • doar ligi serioase (primele divizii + cupele europene)
Bilete: maxim 4 duble pe zi, FIXE până la miezul nopții
"""

import html
import json
import tempfile
import threading
import time
import base64 as _b64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

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
MAX_TICKETS = 4

SIDE_MIN = 80.0        # fiecare echipă trebuie să confirme separat
H2H_AGREE = 60.0       # H2H (dacă există) nu are voie să contrazică
RECENT_N = 5           # ultimele 5 meciuri ale fiecărei echipe...
RECENT_MIN = 4         # ...trebuie să confirme în minim 4
SHRINK_M = 4           # corecție pentru puține date: 4 meciuri „medii” adăugate la fiecare calcul

NUM_MATCHES = 20       # ultimele meciuri descărcate per echipă (~10 acasă / ~10 în deplasare)
MIN_DATA = 6           # minim meciuri acasă (gazda) / în deplasare (oaspetele)
MIN_H2H = 3            # sub 3 meciuri directe, H2H nu se folosește
H2H_YEARS = 5          # doar meciurile directe din ultimii 5 ani
# Fără H2H formula e 50/50. Cu H2H: 0.8 × bază + 0.2 × H2H ≤ 0.8 × bază + 20.
# Ca să ajungă la 85%, baza trebuie să fie ≥ 81.25% — sub acest prag nu mai cerem H2H (economie de cereri).
STAGE1_PROB = 81.0

WORKERS = 6
MIN_INTERVAL = 0.21    # ~285 cereri/minut (limita PRO = 300/minut)
MAX_ODDS_PAGES = 120
RESULT_TTL = 1800      # dacă azi nu au ieșit bilete, se rescanează automat după 30 de minute
STATUS_TTL = 60        # scorurile live se actualizează cel mult o dată pe minut
FINISHED = {"FT", "AET", "PEN"}
LIVE = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}
VOID = {"PST", "CANC", "ABD", "AWD", "WO", "SUSP"}

# Ligi serioase: primele 2 divizii în țările mari, prima divizie în rest, plus cupele europene.
LEAGUE_IDS = {
    2, 3, 848,                                   # Champions League, Europa League, Conference League
    39, 40, 140, 141, 78, 79, 135, 136, 61, 62,  # Anglia, Spania, Germania, Italia, Franța (1+2)
    88, 89, 94, 95, 144, 145, 203, 204,          # Olanda, Portugalia, Belgia, Turcia (1+2)
    179, 180, 218, 219, 207, 208,                # Scoția, Austria, Elveția (1+2)
    119, 120, 103, 104, 113, 114,                # Danemarca, Norvegia, Suedia (1+2)
    106, 107, 345, 346, 283, 284,                # Polonia, Cehia, România (1+2)
    71, 72, 98, 99,                              # Brazilia, Japonia (1+2)
    197, 210, 286, 333, 235, 271, 332, 373, 172, 318, 383,   # Grecia, Croația, Serbia, Ucraina, Rusia, Ungaria,
                                                             # Slovacia, Slovenia, Bulgaria, Cipru, Israel
    128, 253, 262, 292, 188, 307, 169,           # Argentina, SUA, Mexic, Coreea, Australia, Arabia Saudită, China
    357, 244, 164,                               # Irlanda, Finlanda, Islanda
    265, 239, 268, 270, 242, 281, 250, 252,      # Chile, Columbia, Uruguay, Ecuador, Peru, Paraguay
}
EXCLUDE_TEAM = [" W", " Women", " Ladies", " Femenino", " Femminile", " Frauen", " II", " III", " B"]

# ═══════════════════════════ PIEȚE ═══════════════════════════
# Fiecare piață = (etichetă, are nevoie de scorul la pauză, condiție pe meci).
# Condiția primește (H, A, h, a): goluri gazdă/oaspete la 90' și la pauză.
MARKETS = {
    "p1": ("1 · Gazda câștigă", False, lambda H, A, h, a: H > A),
    "px": ("X · Egal", False, lambda H, A, h, a: H == A),
    "p2": ("2 · Oaspetele câștigă", False, lambda H, A, h, a: A > H),
    "p1x": ("1X · Gazda nu pierde", False, lambda H, A, h, a: H >= A),
    "px2": ("X2 · Oaspetele nu pierde", False, lambda H, A, h, a: A >= H),
    "p12": ("12 · Fără egal", False, lambda H, A, h, a: H != A),
    "gg": ("GG · Ambele marchează", False, lambda H, A, h, a: H > 0 and A > 0),
    "ng": ("NG · Nu marchează ambele", False, lambda H, A, h, a: not (H > 0 and A > 0)),
    "fh_gg": ("GG Repriza 1", True, lambda H, A, h, a: h > 0 and a > 0),
    "fh_ng": ("NG Repriza 1", True, lambda H, A, h, a: not (h > 0 and a > 0)),
    "sh_gg": ("GG Repriza 2", True, lambda H, A, h, a: H - h > 0 and A - a > 0),
    "sh_ng": ("NG Repriza 2", True, lambda H, A, h, a: not (H - h > 0 and A - a > 0)),
    "hb_y": ("Gol în ambele reprize", True, lambda H, A, h, a: h + a >= 1 and (H - h) + (A - a) >= 1),
    "hb_n": ("Fără gol într-una din reprize", True, lambda H, A, h, a: not (h + a >= 1 and (H - h) + (A - a) >= 1)),
    "weh_h": ("Gazda câștigă cel puțin o repriză", True, lambda H, A, h, a: h > a or (H - h) > (A - a)),
    "weh_a": ("Oaspetele câștigă cel puțin o repriză", True, lambda H, A, h, a: a > h or (A - a) > (H - h)),
    "fh_1x": ("1X Repriza 1", True, lambda H, A, h, a: h >= a),
    "fh_x2": ("X2 Repriza 1", True, lambda H, A, h, a: a >= h),
    "fh_12": ("12 Repriza 1", True, lambda H, A, h, a: h != a),
    "sh_1x": ("1X Repriza 2", True, lambda H, A, h, a: (H - h) >= (A - a)),
    "sh_x2": ("X2 Repriza 2", True, lambda H, A, h, a: (A - a) >= (H - h)),
    "sh_12": ("12 Repriza 2", True, lambda H, A, h, a: (H - h) != (A - a)),
}
# Familii Peste/Sub: prefix → (descriere, nevoie pauză, câte goluri, linii)
OU_FAMILIES = {
    "": ("goluri", False, lambda H, A, h, a: H + A, ("1.5", "2.5", "3.5")),
    "fh_": ("goluri Repriza 1", True, lambda H, A, h, a: h + a, ("0.5", "1.5")),
    "sh_": ("goluri Repriza 2", True, lambda H, A, h, a: (H - h) + (A - a), ("0.5", "1.5")),
    "h_": ("goluri Gazda", False, lambda H, A, h, a: H, ("0.5", "1.5", "2.5")),
    "a_": ("goluri Oaspete", False, lambda H, A, h, a: A, ("0.5", "1.5", "2.5")),
    "hfh_": ("goluri Gazda Repriza 1", True, lambda H, A, h, a: h, ("0.5", "1.5")),
    "afh_": ("goluri Oaspete Repriza 1", True, lambda H, A, h, a: a, ("0.5", "1.5")),
    "hsh_": ("goluri Gazda Repriza 2", True, lambda H, A, h, a: H - h, ("0.5", "1.5")),
    "ash_": ("goluri Oaspete Repriza 2", True, lambda H, A, h, a: A - a, ("0.5", "1.5")),
}
for _pre, (_desc, _half, _cnt, _lines) in OU_FAMILIES.items():
    for _ln in _lines:
        _t = int(float(_ln) + 0.5)
        _d = _ln.replace(".", "")
        MARKETS[f"{_pre}o{_d}"] = (f"Peste {_ln} {_desc}", _half, lambda H, A, h, a, c=_cnt, t=_t: c(H, A, h, a) >= t)
        MARKETS[f"{_pre}u{_d}"] = (f"Sub {_ln} {_desc}", _half, lambda H, A, h, a, c=_cnt, t=_t: c(H, A, h, a) < t)
_NICE = {
    "h_o05": "Gazda marchează", "a_o05": "Oaspetele marchează",
    "h_u05": "Gazda nu marchează", "a_u05": "Oaspetele nu marchează",
    "hfh_o05": "Gazda marchează în Repriza 1", "hfh_u05": "Gazda nu marchează în Repriza 1",
    "afh_o05": "Oaspetele marchează în Repriza 1", "afh_u05": "Oaspetele nu marchează în Repriza 1",
    "hsh_o05": "Gazda marchează în Repriza 2", "hsh_u05": "Gazda nu marchează în Repriza 2",
    "ash_o05": "Oaspetele marchează în Repriza 2", "ash_u05": "Oaspetele nu marchează în Repriza 2",
}
for _k, _lbl in _NICE.items():
    MARKETS[_k] = (_lbl,) + MARKETS[_k][1:]

# Numele piețelor exact cum vin din API (Betano / Bet365)
NAMED_MARKETS = {
    ("Match Winner", "Home"): "p1", ("Match Winner", "Draw"): "px", ("Match Winner", "Away"): "p2",
    ("Double Chance", "Home/Draw"): "p1x", ("Double Chance", "Draw/Away"): "px2", ("Double Chance", "Home/Away"): "p12",
    ("Double Chance - First Half", "Home/Draw"): "fh_1x", ("Double Chance - First Half", "Draw/Away"): "fh_x2",
    ("Double Chance - First Half", "Home/Away"): "fh_12",
    ("Double Chance - Second Half", "Home/Draw"): "sh_1x", ("Double Chance - Second Half", "Draw/Away"): "sh_x2",
    ("Double Chance - Second Half", "Home/Away"): "sh_12",
    ("Both Teams Score", "Yes"): "gg", ("Both Teams Score", "No"): "ng",
    ("Both Teams Score - First Half", "Yes"): "fh_gg", ("Both Teams Score - First Half", "No"): "fh_ng",
    ("Both Teams To Score - Second Half", "Yes"): "sh_gg", ("Both Teams To Score - Second Half", "No"): "sh_ng",
    ("Both Teams Score - Second Half", "Yes"): "sh_gg", ("Both Teams Score - Second Half", "No"): "sh_ng",
    ("To Score in Both Halves", "Yes"): "hb_y", ("To Score in Both Halves", "No"): "hb_n",
    ("To Score In Both Halves", "Yes"): "hb_y", ("To Score In Both Halves", "No"): "hb_n",
    ("To Win Either Half", "Home"): "weh_h", ("To Win Either Half", "Away"): "weh_a",
}
OU_API = {
    "Goals Over/Under": "", "Goals Over/Under First Half": "fh_",
    "Goals Over/Under - Second Half": "sh_", "Goals Over/Under Second Half": "sh_",
    "Total - Home": "h_", "Total - Away": "a_",
    "Home Team Total Goals(1st Half)": "hfh_", "Away Team Total Goals(1st Half)": "afh_",
    "Home Team Total Goals(2nd Half)": "hsh_", "Away Team Total Goals(2nd Half)": "ash_",
}


def prob_key(bn, vl):
    k = NAMED_MARKETS.get((bn, str(vl)))
    if k:
        return k
    if bn in OU_API:
        parts = str(vl).split()
        if len(parts) == 2 and parts[0] in ("Over", "Under"):
            k = f"{OU_API[bn]}{'o' if parts[0] == 'Over' else 'u'}{parts[1].replace('.', '')}"
            return k if k in MARKETS else None
    return None


def label(k):
    return MARKETS[k][0]


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
        if lg.get("id") not in LEAGUE_IDS:
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
                    "hid": hid, "aid": aid, "league": lg.get("name", "") or "", "country": lg.get("country", "") or ""})
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


# ═══════════════════════════ CALCULE ═══════════════════════════
def match_rows(matches, tid, min_ts=0):
    """Rânduri din perspectiva echipei: (goluri echipă, goluri adversar, la pauză echipă, la pauză adversar,
    timestamp, a jucat acasă, id meci). Doar meciuri terminate, fără amicale, scor la 90 de minute."""
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
        gh, ga = ft.get("home"), ft.get("away")
        if gh is None or ga is None:
            g = m.get("goals") or {}
            gh, ga = g.get("home"), g.get("away")
        if gh is None or ga is None:
            continue
        is_home = (m.get("teams", {}).get("home", {}) or {}).get("id") == tid
        sc, co = (gh, ga) if is_home else (ga, gh)
        ht = sc_.get("halftime") or {}
        hh, ha = ht.get("home"), ht.get("away")
        if hh is not None and ha is not None and hh <= gh and ha <= ga:
            hsc, hco = (hh, ha) if is_home else (ha, hh)
        else:
            hsc = hco = None
        rows.append((sc, co, hsc, hco, stamp, is_home, fx.get("id")))
    rows.sort(key=lambda r: r[4], reverse=True)
    return rows


def as_home(r):
    """Meciul văzut cu echipa noastră pe poziția gazdei."""
    return r[0], r[1], r[2], r[3]


def as_away(r):
    """Meciul văzut cu echipa noastră pe poziția oaspetelui."""
    return r[1], r[0], r[3], r[2]


def as_fixture(r):
    """Meciul așa cum s-a jucat (gazda reală, oaspetele real)."""
    return as_home(r) if r[5] else as_away(r)


def hits(key, tuples, limit=None):
    """(de câte ori a ieșit, din câte meciuri cu date)."""
    _, half, pred = MARKETS[key]
    x = n = 0
    for H, A, h, a in tuples:
        if half and h is None:
            continue
        n += 1
        x += 1 if pred(H, A, h, a) else 0
        if limit and n >= limit:
            break
    return x, n


def shrink(x, n, prior):
    """Corecție pentru puține date: adaugă SHRINK_M meciuri „medii” (rata generală a pieței)."""
    return round((x + SHRINK_M * prior) / (n + SHRINK_M) * 100, 1)


def compute_priors(all_rows):
    """Rata generală a fiecărei piețe, din toate meciurile descărcate azi (fiecare meci o singură dată)."""
    seen = {}
    for r in all_rows:
        if r[6] not in seen:
            seen[r[6]] = as_fixture(r)
    tuples = list(seen.values())
    priors = {}
    for k in MARKETS:
        x, n = hits(k, tuples)
        priors[k] = x / n if n else 0.5
    return priors


def evaluate(key, home_rows, away_rows, h2h_rows, priors):
    """Calculul complet pentru o piață. home_rows/away_rows = toate meciurile recente ale echipelor."""
    prior = priors.get(key, 0.5)
    hx, hn = hits(key, [as_home(r) for r in home_rows if r[5]])          # gazda, meciuri acasă
    ax, an = hits(key, [as_away(r) for r in away_rows if not r[5]])      # oaspetele, meciuri în deplasare
    if hn < MIN_DATA or an < MIN_DATA:
        return None
    ph, pa = shrink(hx, hn, prior), shrink(ax, an, prior)
    p2 = None; n2 = 0
    if h2h_rows:
        x2, n2 = hits(key, [as_home(r) for r in h2h_rows])
        if n2 >= MIN_H2H:
            p2 = shrink(x2, n2, prior)
        else:
            n2 = 0
    prob = round(0.4 * ph + 0.4 * pa + 0.2 * p2, 1) if p2 is not None else round(0.5 * (ph + pa), 1)
    rh, rhn = hits(key, [as_home(r) for r in home_rows], RECENT_N)       # forma recentă gazdă (orice teren)
    ra, ran = hits(key, [as_away(r) for r in away_rows], RECENT_N)       # forma recentă oaspete (orice teren)
    return {"prob": prob, "ph": ph, "pa": pa, "p2": p2, "n2": n2, "hn": hn, "an": an,
            "rh": rh, "ra": ra, "recent_ok": rhn == RECENT_N and ran == RECENT_N and rh >= RECENT_MIN and ra >= RECENT_MIN}


def passes_rules(e, min_prob):
    return (e is not None and e["recent_ok"] and e["ph"] >= SIDE_MIN and e["pa"] >= SIDE_MIN
            and (e["p2"] is None or e["p2"] >= H2H_AGREE) and e["prob"] >= min_prob)


def odds_in_range(bets):
    """Cea mai bună cotă în plaja 1.35–1.70, pentru fiecare piață suportată."""
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
            if MIN_ODDS <= odds <= MAX_ODDS and odds > best.get(k, 0):
                best[k] = odds
    return best


def candidates(odds_map, home_rows, away_rows, h2h_rows, priors, final=True):
    out = []
    for k, odds in odds_map.items():
        e = evaluate(k, home_rows, away_rows, h2h_rows, priors)
        if not passes_rules(e, MIN_PROB if final else STAGE1_PROB):
            continue
        ip = round(100 / odds, 1)
        ev = round(e["prob"] - ip, 1)
        if final and ev < MIN_EV:
            continue
        out.append({"key": k, "label": label(k), "odds": odds, "ip": ip, "ev": ev, **e})
    return out


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
        progress(0.01, "📅 Caut meciurile de azi din ligile serioase...")
    fixes = fetch_fixtures(today)
    stats["fixtures"] = len(fixes)

    odds = fetch_all_odds(today, BETANO_ID, prog(0.02, 0.20))
    if len(odds) < 5:   # API-ul nu are cote Betano azi → cote de referință, afișate tot ca Betano
        odds = fetch_all_odds(today, BET365_ID, prog(0.02, 0.20))

    todo = []
    for f in sorted(fixes, key=lambda x: x["ts"]):
        om = odds_in_range(odds.get(f["fid"]))
        if om:
            todo.append((f, om))
    if limit:
        todo = todo[:limit]
    stats["with_odds"] = len(todo)

    team_ids = sorted({(f["hid"],) for f, _ in todo} | {(f["aid"],) for f, _ in todo})
    hist = _fetch_cached(store, "teams", team_ids,
                         lambda k: api_response("fixtures", {"team": k[0], "last": NUM_MATCHES}),
                         today, prog(0.20, 0.88), "📊 Istoric echipe")
    rows = {k[0]: match_rows(v, k[0]) for k, v in hist.items()}
    priors = compute_priors([r for rr in rows.values() for r in rr])

    stage2 = []
    for f, om in todo:
        hr, ar = rows.get(f["hid"], []), rows.get(f["aid"], [])
        if sum(1 for r in hr if r[5]) < MIN_DATA or sum(1 for r in ar if not r[5]) < MIN_DATA:
            continue
        stats["analyzed"] += 1
        if candidates(om, hr, ar, None, priors, final=False):
            stage2.append((f, om, hr, ar))
    stats["stage2"] = len(stage2)

    min_ts = (datetime.now(timezone.utc) - timedelta(days=365 * H2H_YEARS)).timestamp()
    pairs = sorted({(f["hid"], f["aid"]) for f, _, _, _ in stage2})
    h2h_raw = _fetch_cached(store, "h2h", pairs,
                            lambda k: api_response("fixtures/headtohead", {"h2h": f"{k[0]}-{k[1]}", "last": 10}),
                            today, prog(0.88, 0.99), "🤝 Meciuri directe")

    legs = []
    for f, om, hr, ar in stage2:
        h2r = match_rows(h2h_raw.get((f["hid"], f["aid"])), f["hid"], min_ts)
        cands = candidates(om, hr, ar, h2r, priors, final=True)
        if not cands:
            continue
        b = max(cands, key=lambda x: (x["prob"], x["ev"]))     # o singură selecție per meci — cea mai sigură
        legs.append({**b, "fid": f["fid"], "time": f["time"], "ts": f["ts"], "home": f["home"], "away": f["away"],
                     "league": f["league"], "country": f["country"],
                     "hf": "".join("W" if r[0] > r[1] else "D" if r[0] == r[1] else "L" for r in hr[:5]),
                     "af": "".join("W" if r[0] > r[1] else "D" if r[0] == r[1] else "L" for r in ar[:5])})
    stats["legs"] = len(legs)
    if progress:
        progress(1.0, "✅ Gata")
    return {"date": today, "ts": time.time(), "tickets": build_tickets(legs), "legs": legs,
            "stats": stats, "quota_hit": _quota_hit[0]}


# ═══════════════════════════ BILETE FIXE + SCORURI ═══════════════════════════
SAVE_PATHS = [Path(__file__).with_name(".bilete_ziua.json"),
              Path(tempfile.gettempdir()) / "nord_allaska_bilete_ziua.json"]


def save_frozen(fr):
    for p in SAVE_PATHS:
        try:
            p.write_text(json.dumps(fr, ensure_ascii=False))
            return
        except Exception:
            continue


def load_frozen():
    for p in SAVE_PATHS:
        try:
            return json.loads(p.read_text())
        except Exception:
            continue
    return None


def fetch_statuses(fids):
    out = {}
    for i in range(0, len(fids), 20):
        for m in api_get("fixtures", {"ids": "-".join(str(x) for x in fids[i:i + 20]), "timezone": TZ_NAME}):
            fx = m.get("fixture", {}); sc_ = m.get("score") or {}; g = m.get("goals") or {}
            ft = sc_.get("fulltime") or {}; ht = sc_.get("halftime") or {}
            out[fx.get("id")] = {"status": fx.get("status", {}).get("short"), "elapsed": fx.get("status", {}).get("elapsed"),
                                 "gh": g.get("home"), "ga": g.get("away"), "fth": ft.get("home"), "fta": ft.get("away"),
                                 "hth": ht.get("home"), "hta": ht.get("away")}
    return out


def settle(key, s):
    """win / lose / live / pending / void / unknown — pentru o selecție, din statusul meciului."""
    if not s:
        return "pending"
    if s["status"] in FINISHED:
        H = s["fth"] if s["fth"] is not None else s["gh"]
        A = s["fta"] if s["fta"] is not None else s["ga"]
        h, a = s["hth"], s["hta"]
        _, half, pred = MARKETS[key]
        if H is None or A is None or (half and (h is None or a is None)):
            return "unknown"
        return "win" if pred(H, A, h, a) else "lose"
    if s["status"] in VOID:
        return "void"
    if s["status"] in LIVE:
        return "live"
    return "pending"


def ticket_state(states):
    if "lose" in states:
        return "lose"
    if all(x == "win" for x in states):
        return "win"
    if any(x in ("live", "win") for x in states):
        return "live"
    return "pending"


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
.ticket.win{ border-color:rgba(52,211,153,0.7); background:linear-gradient(180deg,rgba(52,211,153,0.12),rgba(52,211,153,0.03)); }
.ticket.lose{ border-color:rgba(248,113,113,0.6); background:linear-gradient(180deg,rgba(248,113,113,0.10),rgba(248,113,113,0.02)); }
.ticket-head{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:0.6rem; margin-bottom:0.9rem; }
.ticket-title{ font-size:1.25rem; font-weight:800; color:#f1f5f9; }
.chip{ display:inline-block; padding:5px 12px; border-radius:999px; font-weight:800; font-size:0.9rem; margin-left:6px; }
.chip-odds{ background:rgba(245,158,11,0.15); color:#fbbf24; border:1px solid rgba(245,158,11,0.4); }
.chip-prob{ background:rgba(52,211,153,0.15); color:#34d399; border:1px solid rgba(52,211,153,0.4); }
.chip-ev{ background:rgba(167,139,250,0.15); color:#c4b5fd; border:1px solid rgba(167,139,250,0.4); }
.state{ display:inline-block; padding:4px 12px; border-radius:999px; font-weight:800; font-size:0.85rem; }
.st-win{ background:rgba(52,211,153,0.18); color:#34d399; } .st-lose{ background:rgba(248,113,113,0.18); color:#f87171; }
.st-live{ background:rgba(239,68,68,0.15); color:#fca5a5; } .st-pending{ background:rgba(148,163,184,0.12); color:#94a3b8; }
.st-void{ background:rgba(245,158,11,0.15); color:#fbbf24; } .st-unknown{ background:rgba(148,163,184,0.12); color:#cbd5e1; }
.leg{ background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.07); border-radius:14px; padding:0.85rem 1rem; margin-top:0.6rem; }
.leg-top{ display:flex; justify-content:space-between; gap:0.5rem; font-size:0.78rem; color:#94a3b8; }
.leg-time{ color:#38bdf8; font-weight:800; margin-right:8px; }
.leg-teams{ font-size:1.05rem; font-weight:700; color:#f1f5f9; margin:0.25rem 0 0.5rem; }
.vs{ color:#64748b; font-weight:500; margin:0 4px; }
.pick{ display:inline-block; background:rgba(52,211,153,0.14); border:1px solid #34d399; color:#34d399; font-weight:800; padding:4px 12px; border-radius:10px; font-size:0.92rem; margin-right:10px; }
.leg-num{ font-weight:800; color:#e2e8f0; margin-right:10px; font-size:0.95rem; }
.leg-num span{ color:#64748b; font-weight:500; font-size:0.75rem; }
.leg-meta{ font-size:0.72rem; color:#64748b; margin-top:0.55rem; line-height:1.6; }
.f{ display:inline-block; width:18px; height:18px; line-height:18px; text-align:center; border-radius:4px; font-size:0.65rem; font-weight:800; margin-right:2px; }
.fW{ background:rgba(52,211,153,0.2); color:#34d399; } .fD{ background:rgba(245,158,11,0.2); color:#fbbf24; } .fL{ background:rgba(248,113,113,0.2); color:#f87171; }
.empty{ text-align:center; padding:2.5rem 1rem; color:#94a3b8; font-size:1.15rem; background:rgba(255,255,255,0.03); border:1px dashed rgba(255,255,255,0.12); border-radius:18px; }
.empty span{ display:block; font-size:0.85rem; color:#64748b; margin-top:0.5rem; }
.lock-note{ text-align:center; font-size:0.85rem; color:#a5b4fc; background:rgba(129,140,248,0.08); border:1px solid rgba(129,140,248,0.25); border-radius:12px; padding:0.6rem 1rem; margin-bottom:1rem; }
.footer-note{ background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.2); border-radius:12px; padding:1rem 1.4rem; margin-top:1.5rem; font-size:0.8rem; color:#fca5a5; line-height:1.6; }
.rules{ background:rgba(56,189,248,0.06); border:1px solid rgba(56,189,248,0.2); border-radius:12px; padding:1rem 1.4rem; font-size:0.82rem; color:#bae6fd; line-height:1.7; }
#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}
</style>
"""


def form_html(form):
    return "".join(f"<span class='f f{c}'>{c}</span>" for c in form)


def leg_state_html(L, s, state):
    if state == "pending":
        return f"<span class='state st-pending'>⏳ {L['time']}</span>"
    if state == "void":
        return "<span class='state st-void'>⚠️ Amânat / anulat</span>"
    score = f"{s['gh']}-{s['ga']}" if s and s.get("gh") is not None else ""
    if state == "live":
        minute = f" {s['elapsed']}'" if s and s.get("elapsed") else ""
        return f"<span class='state st-live'>🔴 LIVE {score}{minute}</span>"
    if state == "win":
        return f"<span class='state st-win'>✅ {score}</span>"
    if state == "lose":
        return f"<span class='state st-lose'>❌ {score}</span>"
    return f"<span class='state st-unknown'>❔ {score}</span>"


def leg_html(L, s, state):
    e = html.escape
    h2h = f" · H2H {L['p2']:.0f}% ({L['n2']} meciuri)" if L.get("p2") is not None else " · fără H2H suficient"
    return (
        "<div class='leg'>"
        f"<div class='leg-top'><div><span class='leg-time'>{L['time']}</span>{e(L['country'])} · {e(L['league'])}</div>"
        f"<div>{leg_state_html(L, s, state)}</div></div>"
        f"<div class='leg-teams'>{e(L['home'])}<span class='vs'>vs</span>{e(L['away'])}</div>"
        f"<div><span class='pick'>{e(L['label'])}</span>"
        f"<span class='leg-num'>@ {L['odds']:.2f} <span>cotă</span></span>"
        f"<span class='leg-num' style='color:#34d399;'>{L['prob']:.0f}% <span>șansă</span></span>"
        f"<span class='leg-num' style='color:#c4b5fd;'>+{L['ev']:.1f} <span>EV</span></span></div>"
        f"<div class='leg-meta'>Gazda acasă {L['ph']:.0f}% ({L['hn']} meciuri) · Oaspetele în deplasare {L['pa']:.0f}% "
        f"({L['an']} meciuri){h2h}<br>"
        f"Ultimele 5: gazda {L['rh']}/5 · oaspetele {L['ra']}/5 &nbsp;·&nbsp; "
        f"Formă gazdă {form_html(L['hf'])} · oaspete {form_html(L['af'])}</div>"
        "</div>"
    )


TICKET_STATE_TXT = {"win": "<span class='state st-win'>✅ CÂȘTIGAT</span>",
                    "lose": "<span class='state st-lose'>❌ PIERDUT</span>",
                    "live": "<span class='state st-live'>🔴 ÎN JOC</span>",
                    "pending": "<span class='state st-pending'>⏳ În așteptare</span>"}


def ticket_html(i, t, statuses):
    legs = sorted(t["legs"], key=lambda x: x["ts"])
    states = [settle(L["key"], statuses.get(L["fid"])) for L in legs]
    tstate = ticket_state(states)
    cls = tstate if tstate in ("win", "lose") else ""
    return tstate, (
        f"<div class='ticket {cls}'><div class='ticket-head'>"
        f"<div class='ticket-title'>🎫 BILET #{i} &nbsp;{TICKET_STATE_TXT[tstate]}</div>"
        f"<div><span class='chip chip-odds'>Cotă {t['odds']:.2f}</span>"
        f"<span class='chip chip-prob'>Șansă ~{t['prob']:.0f}%</span>"
        f"<span class='chip chip-ev'>EV +{t['ev']:.1f}%</span></div></div>"
        + "".join(leg_html(L, statuses.get(L["fid"]), s) for L, s in zip(legs, states))
        + "</div>"
    )


@st.cache_resource
def get_store():
    return {"lock": threading.Lock(), "scan_lock": threading.Lock(), "teams": {}, "h2h": {},
            "result": None, "frozen": load_frozen(), "status": {"ts": 0, "data": {}}}


def get_statuses(store, frozen, force):
    cache = store["status"]
    if force or time.time() - cache["ts"] > STATUS_TTL or cache.get("date") != frozen["date"]:
        fids = [L["fid"] for t in frozen["tickets"] for L in t["legs"]]
        data = fetch_statuses(fids)
        if data:
            store["status"] = {"ts": time.time(), "data": data, "date": frozen["date"]}
    return store["status"]["data"]


def render_footer(extra=""):
    st.markdown("<hr class='divider'>", unsafe_allow_html=True)
    st.markdown(
        "<div class='rules'><strong>📏 Reguli de joc</strong><br>"
        "• Biletele se fac o singură dată pe zi și rămân fixe până la miezul nopții<br>"
        "• Aceeași miză pe fiecare bilet — fără dublare după o pierdere<br>"
        "• În zilele fără bilete nu forța nimic<br>"
        "• Verifică pe Betano că selecția și cota sunt încă disponibile înainte de a juca<br>"
        "• Șansa afișată e calculată din meciurile trecute — în realitate e de obicei ceva mai mică. "
        "De aceea mizele rămân mici și egale</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='footer-note'>⚠️ <strong>Disclaimer:</strong> Pariurile sportive implică riscuri financiare. "
        f"O probabilitate mare NU garantează câștigul. Joacă responsabil.<br><br>{extra}</div>",
        unsafe_allow_html=True)


def main():
    st.set_page_config(page_title="NORD ALLASKA SUPREME", page_icon="🏔️", layout="centered",
                       initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    store = get_store()
    now = datetime.now(RO_TZ)
    today = now.date().isoformat()
    st.markdown(f"<div class='main-header'><h1>🏔️ NORD ALLASKA SUPREME</h1>"
                f"<p>Bilete Duble · Betano · {now.strftime('%d.%m.%Y')}</p></div>", unsafe_allow_html=True)

    frozen = store["frozen"]
    is_frozen = bool(frozen) and frozen.get("date") == today

    if not is_frozen:
        refresh = st.button("🔄 Scanează", use_container_width=True, type="primary")
        st.markdown(f"<div class='sub-note'>Cote {MIN_ODDS:.2f}–{MAX_ODDS:.2f} · Șansă ≥ {MIN_PROB:.0f}% · "
                    f"EV ≥ +{MIN_EV:.0f} · Maxim {MAX_TICKETS} bilete · Ligi serioase</div>", unsafe_allow_html=True)
        res = store["result"]
        fresh = bool(res) and res["date"] == today and time.time() - res["ts"] < RESULT_TTL
        if refresh or not fresh:
            bar = st.progress(0.0, text="⏳ Pornesc scanarea...")
            hint = st.empty()
            hint.markdown("<div class='sub-note'>Prima scanare a zilei durează câteva minute. "
                          "Biletele găsite rămân apoi fixe toată ziua.</div>", unsafe_allow_html=True)

            def prog(f, t):
                bar.progress(min(max(f, 0.0), 1.0), text=t)

            with store["scan_lock"]:
                fr = store["frozen"]
                if fr and fr.get("date") == today:          # altă sesiune a făcut deja biletele
                    is_frozen = True
                else:
                    res = store["result"]
                    if refresh or not (res and res["date"] == today and time.time() - res["ts"] < RESULT_TTL):
                        res = run_scan(store, prog)
                        store["result"] = res
                    if res["tickets"]:
                        store["frozen"] = {"date": today, "ts": res["ts"], "tickets": res["tickets"], "stats": res["stats"]}
                        save_frozen(store["frozen"])
                        is_frozen = True
            bar.empty(); hint.empty()
            if is_frozen:
                st.rerun()

        if not is_frozen:
            s = res["stats"]
            if res.get("quota_hit"):
                st.error("⚠️ S-a atins limita zilnică de cereri API (7.500). Rezultatele pot fi incomplete — revino mâine.")
            st.markdown("<hr class='divider'>", unsafe_allow_html=True)
            st.markdown("<div class='empty'>🔍 Azi (încă) nu sunt bilete care să treacă toate regulile."
                        "<span>Aplicația reverifică automat la 30 de minute când o deschizi. Nu forța — "
                        "dacă nu apare nimic, sari ziua.</span></div>", unsafe_allow_html=True)
            render_footer(f"<strong>Ultima scanare:</strong> {datetime.fromtimestamp(res['ts'], RO_TZ).strftime('%H:%M')} · "
                          f"{s['fixtures']} meciuri azi în ligile serioase · {s['with_odds']} cu cote în plajă · "
                          f"{s['analyzed']} cu date suficiente · {s['legs']} selecții")
            return

    # ─── Biletele zilei (fixe) ───
    frozen = store["frozen"]
    refresh = st.button("🔄 Actualizează scorurile", use_container_width=True, type="primary")
    statuses = get_statuses(store, frozen, refresh)
    gen = datetime.fromtimestamp(frozen["ts"], RO_TZ).strftime("%H:%M")
    st.markdown(f"<div class='lock-note'>🔒 Biletele zilei au fost generate la {gen} și rămân fixe până la miezul nopții.</div>",
                unsafe_allow_html=True)

    rendered = [ticket_html(i, t, statuses) for i, t in enumerate(frozen["tickets"], 1)]
    states = [r[0] for r in rendered]
    cols = st.columns(4)
    for col, (v, lb, c) in zip(cols, [(len(states), "Bilete azi", "#38bdf8"),
                                       (states.count("win"), "Câștigate", "#34d399"),
                                       (states.count("lose"), "Pierdute", "#f87171"),
                                       (states.count("live") + states.count("pending"), "În joc / așteptare", "#fbbf24")]):
        col.markdown(f"<div class='metric-card'><div class='value' style='color:{c};'>{v}</div>"
                     f"<div class='label'>{lb}</div></div>", unsafe_allow_html=True)
    st.markdown("<hr class='divider'>", unsafe_allow_html=True)
    for _, h in rendered:
        st.markdown(h, unsafe_allow_html=True)
    s = frozen.get("stats", {})
    render_footer(f"<strong>Sursă:</strong> API-Football PRO · Betano · {s.get('fixtures', 0)} meciuri în ligile serioase · "
                  f"{s.get('analyzed', 0)} analizate · {s.get('legs', 0)} selecții au trecut toate regulile")


if __name__ == "__main__":
    main()
