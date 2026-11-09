import sys, json, base64, urllib.request, datetime, pathlib, webbrowser
ROOT=pathlib.Path(__file__).resolve().parent
now=datetime.datetime.now(datetime.timezone.utc); years=[now.year,now.year+1]; events=[]; ok=[]
for y in years:
    try:
        req=urllib.request.Request('https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates='+str(y)+'&limit=1000',headers={'User-Agent':'Mozilla/5.0 Sideline-Lab/1.0','Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=20) as f:data=json.load(f)
        if not isinstance(data.get('events'),list):raise ValueError('Missing event list')
        ok.append(y)
        for e in data['events']:
            cs=e.get('competitions') or []
            if not cs:continue
            c=cs[0]; st=(c.get('status') or e.get('status') or {}).get('type',{})
            if st.get('completed') or st.get('name')!='STATUS_SCHEDULED':continue
            try:dt=datetime.datetime.fromisoformat(e['date'].replace('Z','+00:00'))
            except (KeyError,ValueError):continue
            if dt<now:continue
            comps=[]
            for z in c.get('competitors',[]):
                t=z.get('team') or {}
                if not t.get('id'):continue
                comps.append({'homeAway':z.get('homeAway'),'team':{'id':str(t['id']),'displayName':t.get('displayName',''),'abbreviation':t.get('abbreviation','')}})
            if len(comps)!=2:continue
            events.append({'id':str(e['id']),'date':e['date'],'season':{'type':e.get('season',{}).get('type',2)},'competitions':[{'status':{'type':{'completed':False,'name':'STATUS_SCHEDULED'}},'competitors':comps}]})
        print('Checked',y)
    except Exception as exc:print('Could not refresh',y,str(exc))
if ok:
    payload={'checkedAt':now.isoformat(),'years':years,'okYears':ok,'events':events}
    encoded=base64.b64encode(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()).decode('ascii')
    tmp=ROOT/'schedule.js.tmp';tmp.write_text("window.SIDELINE_SCHEDULE_B64='"+encoded+"';\n",encoding='utf-8');tmp.replace(ROOT/'schedule.js')
    print('Scheduled matches:',len(events))
else:print('Using the previous saved schedule, if available.')
if '--no-open' not in sys.argv:webbrowser.open((ROOT/'index.html').as_uri())
