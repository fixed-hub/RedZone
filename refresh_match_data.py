import base64,concurrent.futures,datetime,json,pathlib,re,sys,urllib.parse,urllib.request
ROOT=pathlib.Path(__file__).resolve().parent;PATH=ROOT/'match-data.js';now=datetime.datetime.now(datetime.timezone.utc)
API='https://site.api.espn.com/apis/site/v2/sports/'; PWHL='https://lscluster.hockeytech.com/feed/index.php'; KEY='446521baf8c38984'
LEAGUES={'wnba':('basketball','wnba'),'nwsl':('soccer','usa.nwsl'),'wsl':('soccer','eng.w.1')}
def get(url,params=None):
 if params:url+='?'+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 RedZone/1.0','Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=18) as f:return json.load(f)
def loadjs(path):
 try:return json.loads(base64.b64decode(path.read_text('utf8').split("'",2)[1]).decode('utf8'))
 except Exception:return {}
def fresh(stamp,hours):
 try:return datetime.timedelta(0)<=now-datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))<datetime.timedelta(hours=hours)
 except Exception:return False
old=loadjs(PATH);sports=loadjs(ROOT/'sports-data.js');schedule=loadjs(ROOT/'schedule.js')
# Existing ESPN player ids are read from the page; no scraping or identity guesses.
html=(ROOT/'index.html').read_text('utf8');pos=html.index('const DATA=')+len('const DATA=');wnba,_=json.JSONDecoder().raw_decode(html[pos:])
players={'wnba':wnba['players']}
for l,v in sports.get('leagues',{}).items():players[l]=[dict(p,teamId=t) for t,r in v.get('rosters',{}).items() for p in r]

def injuries(l):
 sport,slug=LEAGUES[l];j=get(API+sport+'/'+slug+'/injuries')
 if j.get('status')!='success' or not isinstance(j.get('injuries'),list):raise ValueError('No injury feed')
 rows=[]
 for team in j['injuries']:
  for x in team.get('injuries',[]):
   a=x.get('athlete') or {};links=a.get('links') or [];href=next((z.get('href','') for z in links if '/player/' in z.get('href','') and '/id/' in z.get('href','')),'');m=re.search(r'/id/(\d+)',href);pid=str(a.get('id') or (m.group(1) if m else ''));details=x.get('details') or {}
   if not pid:continue
   rows.append({'teamId':str(team.get('id','')),'id':pid,'name':a.get('displayName',''),'status':x.get('status',''),'reason':details.get('type',''),'date':x.get('date',''),'comment':x.get('shortComment',''),'url':href})
 return {'checkedAt':now.isoformat(),'source':'ESPN','rows':rows}
def wnba_roster(team):
 j=get(API+'basketball/wnba/teams/'+str(team['id'])+'/roster');ro=j.get('athletes')
 if not isinstance(ro,list) or not ro:raise ValueError('WNBA team roster unavailable')
 out=[]
 for a in ro:
  if not a.get('id') or not a.get('displayName'):continue
  links=a.get('links') or [];href=next((x.get('href','') for x in links if '/player/_/id/' in x.get('href','')),'')
  out.append({'id':str(a['id']),'name':a['displayName'],'teamId':str(team['id']),'position':(a.get('position') or {}).get('abbreviation',''),'photo':(a.get('headshot') or {}).get('href',''),'url':href})
 if not out:raise ValueError('WNBA team roster empty')
 return out
def wnba_nearby():
 a=(now-datetime.timedelta(days=2)).strftime('%Y%m%d');b=(now+datetime.timedelta(days=7)).strftime('%Y%m%d');j=get(API+'basketball/wnba/scoreboard',{'dates':a+'-'+b,'limit':1000});return [{'id':str(e['id']),'date':e['date']} for e in j.get('events',[]) if e.get('id') and e.get('date')]
def wnba_lineup(e):
 j=get(API+'basketball/wnba/summary',{'event':e['id']});out={}
 for team in (j.get('boxscore') or {}).get('players',[]):
  tid=str((team.get('team') or {}).get('id',''));entries=[]
  for block in team.get('statistics',[]):
   for r in block.get('athletes',[]):
    a=r.get('athlete') or {};pid=str(a.get('id',''));name=a.get('displayName','')
    if pid and name:entries.append({'id':pid,'name':name,'teamId':tid,'position':(a.get('position') or {}).get('abbreviation',''),'photo':(a.get('headshot') or {}).get('href',''),'starter':r.get('starter') is True})
  if tid and len(entries)>=5 and sum(x['starter'] for x in entries)>=5:out[tid]=entries
 return out
def soccer_lineup(l,e):
 sport,slug=LEAGUES[l];j=get(API+sport+'/'+slug+'/summary',{'event':e['id']});out={}
 for team in j.get('rosters',[]):
  tid=str((team.get('team') or {}).get('id',''));r=team.get('roster') or []
  if not tid or not isinstance(r,list) or sum(z.get('starter') is True for z in r)<11:continue
  entries=[]
  for z in r:
   a=z.get('athlete') or {};id=str(a.get('id',''));name=a.get('displayName','')
   if not id or not name:continue
   entries.append({'id':id,'name':name,'position':(z.get('position') or {}).get('abbreviation',''),'starter':z.get('starter') is True,'photo':(a.get('headshot') or {}).get('href',''),'url':''})
  if entries:out[tid]=entries
 return out
def hockey_lineup(e):
 j=get(PWHL,{'feed':'gc','tab':'gamesummary','game_id':e['id'],'key':KEY,'client_code':'pwhl'});x=(j.get('GC') or {}).get('Gamesummary') or {};out={}
 for side,label in [('home','home_team_lineup'),('visitor','visitor_team_lineup')]:
  tid=str((x.get(side) or {}).get('id',''));ro=x.get(label) or {};entries=[]
  if not isinstance(ro,dict):continue
  for section in ro.values():
   if not isinstance(section,list):continue
   for p in section:
    pid=str(p.get('player_id',''));name=(p.get('first_name','')+' '+p.get('last_name','')).strip()
    if pid and name:entries.append({'id':pid,'name':name,'position':p.get('position_str',''),'starter':str(p.get('start','0'))=='1','photo':'','url':''})
  if tid and len(entries)>=10:out[tid]=entries
 return out

def espn_logs(l,p):
 sport,slug=LEAGUES[l];params={'season':now.year}
 if l!='wnba':params['league']=slug;params['team']=p.get('teamId','')
 j=get(f'https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{slug}/athletes/{p["id"]}/gamelog',params)
 names=j.get('names') or [];events=j.get('events') or {};records=[]
 for group in j.get('seasonTypes',[]):
  for cat in group.get('categories',[]):
   for row in cat.get('events',[]):
    event=events.get(str(row.get('eventId')),{}) or {};date=event.get('gameDate');raw=row.get('stats') or []
    if not date or len(raw)!=len(names):continue
    values=dict(zip(names,raw)); rec={'date':date}
    def num(v):
     try:return float(v)
     except (TypeError,ValueError):return None
    if l=='wnba':
     rec['metric']='Points';rec['value']=num(values.get('points'));minute=num(values.get('minutes'))
     if minute is None or minute<=0:continue
    elif p.get('position','').upper() in ('G','GK'):
     saves=num(values.get('saves'));ga=num(values.get('goalsConceded'))
     if saves is None or ga is None or saves+ga<=0:continue
     rec.update({'metric':'Save %','saves':saves,'shots':saves+ga})
    elif p.get('position','').upper() in ('F','FW','M','MF'):
     rec['metric']='Shots';rec['value']=num(values.get('totalShots'))
    else:continue # attacking numbers are not a general performance measure for defenders
    if rec['metric']!='Save %' and rec.get('value') is None:continue
    records.append(rec)
 return sorted({r['date']:r for r in records}.values(),key=lambda x:x['date'])[-30:]
def hockey_logs(p,season):
 j=get(PWHL,{'feed':'modulekit','view':'player','category':'gamebygame','season_id':season,'player_id':p['id'],'key':KEY,'client_code':'pwhl'});records=[]
 for x in ((j.get('SiteKit') or {}).get('Player') or {}).get('games',[]):
  date=x.get('date_played');
  if not date:continue
  try:
   if str(x.get('goalie'))=='1':
    saves=float(x['saves']);shots=float(x['shots_against']);
    if shots<=0:continue
    records.append({'date':date+'T12:00:00Z','metric':'Save %','saves':saves,'shots':shots})
   else:records.append({'date':date+'T12:00:00Z','metric':'Points','value':float(x['points'])})
  except (KeyError,ValueError,TypeError):continue
 return sorted(records,key=lambda x:x['date'])[-30:]
result={'injuries':old.get('injuries',{}),'lineups':old.get('lineups',{}),'logs':old.get('logs',{}),'formsCheckedAt':old.get('formsCheckedAt'),'teamRosters':old.get('teamRosters',{})};status=[]
# Injury reports and match lineups change faster than season logs.
if '--force' in sys.argv or not fresh(old.get('checkedAt',''),.25):
 jobs={}
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
  for l in LEAGUES:jobs[pool.submit(injuries,l)]=('injuries',l,'')
  result['teamRosters'].setdefault('wnba',{})
  for team in wnba['teams']:jobs[pool.submit(wnba_roster,team)]=('roster','wnba',str(team['id']))
  for l,v in sports.get('leagues',{}).items():
   result['lineups'].setdefault(l,{})
   for e in v.get('events',[]):
    try:date=datetime.datetime.fromisoformat(e['date'].replace('Z','+00:00'))
    except Exception:continue
    if not now-datetime.timedelta(days=2)<=date<=now+datetime.timedelta(days=7):continue
    jobs[pool.submit(hockey_lineup if l=='pwhl' else soccer_lineup,e) if l=='pwhl' else pool.submit(soccer_lineup,l,e)]=('lineup',l,e['id'])
  result['lineups'].setdefault('wnba',{})
  try:
   for e in wnba_nearby():jobs[pool.submit(wnba_lineup,e)]=('lineup','wnba',e['id'])
  except Exception as e:status.append('WNBA schedule: '+type(e).__name__)
  for f in concurrent.futures.as_completed(jobs):
   typ,l,id=jobs[f]
   try:
    x=f.result()
    if typ=='injuries':result['injuries'][l]=x
    elif typ=='roster':result['teamRosters']['wnba'][id]={'checkedAt':now.isoformat(),'players':x}
    else:result['lineups'][l][id]={'checkedAt':now.isoformat(),'teams':x}
   except Exception as e:status.append(f'{typ} {l}: {type(e).__name__}')
 result['checkedAt']=now.isoformat()
else:result['checkedAt']=old.get('checkedAt')
if '--force' in sys.argv or not fresh(old.get('formsCheckedAt',''),6):
 current=result.get('teamRosters',{}).get('wnba',{})
 if current:players['wnba']=[p for team in current.values() for p in team['players']]
 try:
  seasons=get(PWHL,{'feed':'modulekit','view':'seasons','key':KEY,'client_code':'pwhl'})['SiteKit']['Seasons'];today=now.date().isoformat();rs=[x for x in seasons if 'Regular Season' in x.get('season_name','') and x.get('start_date','')<=today];season=max(rs,key=lambda x:x['start_date'])['season_id']
 except Exception:season=None
 jobs={};newlogs={l:{} for l in players}
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
  for l,ps in players.items():
   for p in {p['id']:p for p in ps}.values():
    if l=='pwhl':
     if not season:continue
     f=pool.submit(hockey_logs,p,season)
    else:f=pool.submit(espn_logs,l,p)
    jobs[f]=(l,p['id'])
  failed=0
  for f in concurrent.futures.as_completed(jobs):
   l,id=jobs[f]
   try:
    x=f.result()
    if x:newlogs[l][id]=x
   except Exception:
    failed+=1
    prev=(old.get('logs',{}).get(l,{}) or {}).get(id)
    if prev:newlogs[l][id]=prev
 if not season:newlogs['pwhl']=(old.get('logs') or {}).get('pwhl',{})  # keep saved PWHL logs when the season list fails to load
 result['logs']=newlogs;result['formsCheckedAt']=now.isoformat();result['logErrors']=failed
 print('Form logs', {l:len(x) for l,x in newlogs.items()},'errors',failed,flush=True)
result['errors']=status
encoded=base64.b64encode(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()).decode('ascii');tmp=PATH.with_suffix('.tmp');tmp.write_text("window.REDZONE_MATCH_B64='"+encoded+"';\n",encoding='utf8');tmp.replace(PATH)
print('Match data refreshed:',len(result['injuries']),'injury feeds; lineups',{l:sum(bool(x.get('teams')) for x in m.values()) for l,m in result['lineups'].items()},'errors',len(status))
