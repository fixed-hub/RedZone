import base64, concurrent.futures, datetime, json, pathlib, sys, urllib.request, urllib.parse, urllib.error
ROOT=pathlib.Path(__file__).resolve().parent
LEAGUES={'nwsl':('soccer','usa.nwsl'), 'wsl':('soccer','eng.w.1')}
ALL=('nwsl','wsl','pwhl')
now=datetime.datetime.now(datetime.timezone.utc); path=ROOT/'sports-data.js'
def read_previous():
    try: return json.loads(base64.b64decode(path.read_text('utf-8').split("'",2)[1]).decode('utf-8'))
    except Exception: return {}
old=read_previous()
if '--force' not in sys.argv and all(k in old.get('leagues',{}) for k in ALL):
    try:
        dt=datetime.datetime.fromisoformat(old['checkedAt'].replace('Z','+00:00'))
        if datetime.timedelta(0)<=now-dt<datetime.timedelta(hours=6): print('Women sports cache is less than 6 hours old.');sys.exit(0)
    except Exception: pass
def get(url,params=None):
    if params: url+='?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 RedZone/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=22) as f: return json.load(f)
def base(l):
    sport,slug=LEAGUES[l];return f'https://site.api.espn.com/apis/site/v2/sports/{sport}/{slug}'
def soccer_teams(l):
    j=get(base(l)+'/teams',{'limit':100});raw=j['sports'][0]['leagues'][0]['teams']
    out=[]
    for x in raw:
        t=x['team'];out.append({'id':str(t['id']),'name':t.get('displayName') or t.get('name'),'abbr':t.get('abbreviation',''),'logo':(t.get('logos') or [{}])[0].get('href','')})
    if not out: raise ValueError('empty team list')
    return out
def soccer_roster(l,t):
    j=get(base(l)+'/teams/'+urllib.parse.quote(t['id'])+'/roster');raw=j.get('athletes');
    if not isinstance(raw,list):raise ValueError('missing roster')
    players=[]
    for a in raw:
        for p in a.get('items',[a]):
            if not p.get('id') or not p.get('displayName'):continue
            links=p.get('links') or [];link=next((x.get('href','') for x in links if 'player' in x.get('href','')), '')
            players.append({'id':str(p['id']),'name':p['displayName'],'position':(p.get('position') or {}).get('abbreviation',''),'photo':(p.get('headshot') or {}).get('href',''),'url':link})
    return players
def soccer_year(l,year):
    j=get(base(l)+'/scoreboard',{'dates':year,'limit':1000})
    if not isinstance(j.get('events'),list):raise ValueError('missing events')
    out=[]
    for e in j['events']:
        cs=e.get('competitions') or []
        if not cs:continue
        c=cs[0];comps=c.get('competitors') or [];home=next((x for x in comps if x.get('homeAway')=='home'),None);away=next((x for x in comps if x.get('homeAway')=='away'),None)
        if not home or not away or not home.get('team') or not away.get('team'):continue
        try:dt=datetime.datetime.fromisoformat(e['date'].replace('Z','+00:00'))
        except Exception:continue
        if dt<now-datetime.timedelta(days=365) or dt>now+datetime.timedelta(days=90):continue
        st=(c.get('status') or e.get('status') or {}).get('type',{});links=e.get('links') or []
        url=next((x.get('href','') for x in links if x.get('href','').startswith('https://www.espn.com/')),'')
        out.append({'id':str(e['id']),'date':e['date'],'home':str(home['team']['id']),'away':str(away['team']['id']),'homeName':home['team'].get('displayName',''),'awayName':away['team'].get('displayName',''),'homeScore':home.get('score'),'awayScore':away.get('score'),'status':st.get('name',''),'completed':bool(st.get('completed')),'detail':st.get('shortDetail',''),'url':url})
    return out
PURL='https://lscluster.hockeytech.com/feed/index.php'
def pwhl(view,**p):return get(PURL,{'feed':'modulekit','view':view,'key':'446521baf8c38984','client_code':'pwhl',**p})['SiteKit']
def hockey_info():
    seasons=pwhl('seasons')['Seasons'];today=now.date().isoformat()
    active=[s for s in seasons if s.get('start_date','')<=today<=s.get('end_date','')]
    rosterseason=active[0] if active else next((s for s in seasons if s.get('start_date','')<=today),seasons[0])
    regs=[s for s in seasons if 'Regular Season' in s.get('season_name','') and s.get('end_date','')>=today]
    schedseason=min(regs,key=lambda s:s['start_date']) if regs else rosterseason
    raw=pwhl('teamsbyseason',season_id=schedseason['season_id'])['Teamsbyseason']
    teams=[{'id':str(t['id']),'name':t['name'],'abbr':t.get('code',''),'logo':t.get('team_logo_url','')} for t in raw if t.get('id') and t.get('name')]
    if not teams:raise ValueError('empty PWHL teams')
    start=(now-datetime.timedelta(days=2)).date().isoformat();end=(now+datetime.timedelta(days=90)).date().isoformat()
    relevant=[x for x in seasons if x.get('start_date','9999')<=end and x.get('end_date','0000')>=start]
    if not relevant: relevant=[schedseason]
    previous=[s for s in seasons if 'Regular Season' in s.get('season_name','') and s.get('start_date','')<=today]
    statseason=max(previous,key=lambda s:s['start_date']) if previous else rosterseason
    if statseason not in relevant:relevant.append(statseason)
    return rosterseason,relevant,teams,statseason
def hockey_roster(team,season):
    rows=pwhl('roster',team_id=team['id'],season_id=season['season_id']).get('Roster',[])
    if not isinstance(rows,list):raise ValueError('missing roster')
    return [{'id':str(p.get('player_id') or p['id']),'name':p['name'],'position':p.get('position',''),'photo':p.get('player_image',''),'url':''} for p in rows if isinstance(p,dict) and p.get('name') and (p.get('player_id') or p.get('id'))]
def hockey_schedule(season):
    rows=pwhl('schedule',season_id=season['season_id']).get('Schedule')
    if not isinstance(rows,list):raise ValueError('missing schedule')
    out=[]
    for x in rows:
        if str(x.get('time_tbd','0'))=='1' or str(x.get('date_tbd','0'))=='1':continue
        date=x.get('GameDateISO8601')
        try:dt=datetime.datetime.fromisoformat(date.replace('Z','+00:00'))
        except Exception:continue
        if dt<now-datetime.timedelta(days=365) or dt>now+datetime.timedelta(days=90):continue
        final=str(x.get('final'))=='1';started=str(x.get('started'))=='1'; status='STATUS_FINAL' if final else 'STATUS_IN_PROGRESS' if started else 'STATUS_SCHEDULED'
        out.append({'id':str(x['id']),'date':date,'home':str(x['home_team']),'away':str(x['visiting_team']),'homeName':x.get('home_team_name',''),'awayName':x.get('visiting_team_name',''),'homeScore':x.get('home_goal_count') if final or started else None,'awayScore':x.get('visiting_goal_count') if final or started else None,'status':status,'completed':final,'detail':x.get('game_status',''),'url':''})
    return out
def soccer_stats(l,p):
    slug=LEAGUES[l][1]
    j=get(f'https://site.web.api.espn.com/apis/common/v3/sports/soccer/{slug}/athletes/{p}/overview')
    st=j.get('statistics') or {}; names=st.get('names') or []; splits=[x for x in st.get('splits',[]) if x.get('leagueSlug')==slug and len(x.get('stats',[]))==len(names)]
    if not splits:return None
    x=splits[0]; vals=dict(zip(names,x['stats']))
    labels=[('starts','Starts'),('totalGoals','Goals'),('goalAssists','Assists'),('totalShots','Shots'),('shotsOnTarget','On target'),('cleanSheet','Clean sheets'),('saves','Saves'),('goalsConceded','Goals against')]
    return {'season':x.get('displayName',''), 'teamId':str(x.get('teamId','')), 'items':[[label,str(vals[key])] for key,label in labels if key in vals]}
def hockey_stats(team,season,typ):
    rows=pwhl('statviewtype',type=typ,league_id=1,team_id=team['id'],season_id=season['season_id']).get('Statviewtype')
    if not isinstance(rows,list):raise ValueError('missing stats')
    labels=([('games_played','Games'),('saves','Saves'),('save_percentage','Save %'),('goals_against_average','GAA'),('shutouts','Shutouts')] if typ=='goalies' else [('games_played','Games'),('goals','Goals'),('assists','Assists'),('points','Points'),('shots','Shots'),('plus_minus','+/−')])
    return {str(x['player_id']):{'season':season['season_name'],'teamId':team['id'],'items':[[label,str(x[key])] for key,label in labels if x.get(key) not in (None,'')]} for x in rows if x.get('player_id')}
leagues={};failed=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    fs={pool.submit(soccer_teams,l):l for l in LEAGUES}
    for f,l in fs.items():
        try:leagues[l]={'teams':f.result(),'rosters':{},'events':[],'failedDays':0,'failedRosters':0,'source':'ESPN'}
        except Exception as e:failed.append(l+': teams '+str(e))
    try:
        rs,seasons,teams,statseason=hockey_info();leagues['pwhl']={'teams':teams,'rosters':{},'events':[],'failedDays':0,'failedRosters':0,'source':'PWHL / HockeyTech','rosterSeason':rs['season_name'],'scheduleSeason':', '.join(x['season_name'] for x in seasons),'statsSeason':statseason['season_name']}
    except Exception as e:failed.append('pwhl: teams '+str(e))
    jobs={}
    for l,v in leagues.items():
        for t in v['teams']:
            f=pool.submit(hockey_roster,t,rs) if l=='pwhl' else pool.submit(soccer_roster,l,t)
            jobs[f]=('roster',l,t['id'])
        if l=='pwhl':
            for season in seasons:jobs[pool.submit(hockey_schedule,season)]=('schedule',l,season['season_id'])
            for t in v['teams']:
                for typ in ('skaters','goalies'):jobs[pool.submit(hockey_stats,t,statseason,typ)]=('hstats',l,t['id'])
        else:
            for year in (now.year-1,now.year,now.year+1):jobs[pool.submit(soccer_year,l,year)]=('schedule',l,str(year))
    for f in concurrent.futures.as_completed(jobs):
        typ,l,key=jobs[f];v=leagues[l]
        try:
            result=f.result()
            if typ=='roster':
                v['rosters'][key]=result
                if not result:v['failedRosters']+=1
            elif typ=='hstats':v.setdefault('stats',{}).update(result)
            else:v['events'].extend(result)
        except Exception as e:
            if typ=='roster':v['failedRosters']+=1
            elif typ=='hstats':v['failedStats']=v.get('failedStats',0)+1
            else:v['failedDays']+=1;failed.append(l+': schedule '+str(e))
# HockeyTech redirects missing portraits to a generic silhouette; keep initials instead.
def photo_exists(url):
    try:
        req=urllib.request.Request(url,method='HEAD',headers={'User-Agent':'Mozilla/5.0 RedZone/1.0'})
        with urllib.request.urlopen(req,timeout=12) as response:
            return 'nophoto' not in response.url.lower() and response.headers.get('Content-Type','').startswith('image/')
    except urllib.error.HTTPError as e:
        return False if e.code in (404,410) else None
    except Exception:return None
if 'pwhl' in leagues:
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as photo_pool:
        jobs={photo_pool.submit(photo_exists,p['photo']):p for roster in leagues['pwhl']['rosters'].values() for p in roster if p.get('photo')}
        for f in concurrent.futures.as_completed(jobs):
            if f.result() is False:jobs[f]['photo']=''

# Fetch ESPN player overviews independently; failures remain explicit, never zero-filled.
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    jobs={}
    for l in LEAGUES:
        if l not in leagues:continue
        ids={p['id'] for roster in leagues[l]['rosters'].values() for p in roster}
        for pid in ids:jobs[pool.submit(soccer_stats,l,pid)]=(l,pid)
        leagues[l]['stats']={}
    for f in concurrent.futures.as_completed(jobs):
        l,pid=jobs[f]
        try:
            x=f.result()
            if x:leagues[l]['stats'][pid]=x
        except Exception:leagues[l]['failedStats']=leagues[l].get('failedStats',0)+1
for l,v in leagues.items():
    previous=old.get('leagues',{}).get(l,{})
    if v.get('failedStats') and previous.get('stats'):
        for pid,stat in previous['stats'].items():v.setdefault('stats',{}).setdefault(pid,stat)
    for x in v['stats'].values():
        if x.get('teamId'):
            t=next((t for t in v['teams'] if t['id']==x['teamId']),None)
            if t:x['teamName']=t['name']
    v['history']=[x for x in v['events'] if x.get('completed') and x.get('homeScore') is not None and x.get('awayScore') is not None and now-datetime.timedelta(days=365)<=datetime.datetime.fromisoformat(x['date'].replace('Z','+00:00'))<now]
    v['events']=[x for x in v['events'] if datetime.datetime.fromisoformat(x['date'].replace('Z','+00:00'))>=now-datetime.timedelta(days=2)]
    print(l,'stats',len(v.get('stats',{})),'history',len(v['history']),'stats errors',v.get('failedStats',0))
    v['events']=sorted({x['id']:x for x in v['events']}.values(),key=lambda x:x['date'])
    print(l,'teams',len(v['teams']),'players',sum(map(len,v['rosters'].values())),'games',len(v['events']),'failures',v['failedDays'],v['failedRosters'])
for l in ALL:
    if l not in leagues and l in old.get('leagues',{}):leagues[l]=old['leagues'][l];leagues[l]['oldSnapshot']=old.get('checkedAt')
if not leagues:print('No league data refreshed; saved copy remains.');sys.exit(1)
payload={'checkedAt':now.isoformat(),'leagues':leagues,'window':'past 2 / next 90 days','errors':failed}
raw=base64.b64encode(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()).decode('ascii')
tmp=ROOT/'sports-data.js.tmp';tmp.write_text("window.SIDELINE_SPORTS_B64='"+raw+"';\n",encoding='utf8');tmp.replace(path)
