import requests
TIMEOUT=8
BASE="https://site.api.espn.com/apis/site/v2/sports"
PATHS={
 "football":[("soccer/eng.1","Английская Премьер-лига"),("soccer/uefa.champions","Лига чемпионов")],
 "basketball":[("basketball/nba","NBA")],
 "tennis":[("tennis/atp","ATP Tennis")]
}
def get_events(sport):
    if sport=="dota2":
        try:
            r=requests.get("https://api.opendota.com/api/status",timeout=TIMEOUT)
            r.raise_for_status()
            return [],"OpenDota доступен, но этот endpoint не даёт надёжного расписания будущих профессиональных матчей."
        except Exception as e: return [],f"OpenDota временно недоступен: {type(e).__name__}"
    if sport=="cs2": return [],"Проверенный бесплатный источник будущих матчей CS2 пока не подключён."
    events=[]; errors=[]
    for path,label in PATHS.get(sport,[]):
        try:
            r=requests.get(f"{BASE}/{path}/scoreboard",timeout=TIMEOUT,headers={"User-Agent":"SportPredictorMVP/1.0"})
            r.raise_for_status()
            for ev in r.json().get("events",[]):
                comps=ev.get("competitions",[])
                competitors=comps[0].get("competitors",[]) if comps else []
                if len(competitors)<2: continue
                home=next((x for x in competitors if x.get("homeAway")=="home"),competitors[0])
                away=next((x for x in competitors if x.get("homeAway")=="away"),competitors[1])
                events.append({"home":home.get("team",{}).get("displayName","Unknown"),
                "away":away.get("team",{}).get("displayName","Unknown"),"start":ev.get("date",""),
                "source":f"ESPN · {label}","odds_home":None,"odds_away":None})
        except Exception as e: errors.append(f"{label}: {type(e).__name__}")
    return events, ("Часть источников недоступна: "+"; ".join(errors)) if errors else "Источник: ESPN scoreboard. Расписание может быть неполным; проверь дату и статус матча."
def source_status():
    out={}
    for name,url in [
        ("ESPN NBA","https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"),
        ("OpenDota","https://api.opendota.com/api/status")]:
        try:
            r=requests.get(url,timeout=TIMEOUT); out[name]="OK" if r.ok else f"HTTP {r.status_code}"
        except Exception as e: out[name]=f"ошибка ({type(e).__name__})"
    out["CS2 расписание"]="не подключено"
    out["BetBoom"]="не подключён: разрешённый официальный способ не подтверждён"
    return out
