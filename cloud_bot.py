"""Daily, paper-only ETF breakout worker. No broker credentials or live order path."""
import json, os, time, math, tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from strategy_original import UNIVERSE, evaluate, ACCOUNT_CASH, RESERVE, MAX_EXPOSURE, MAX_POSITIONS, RISK, WEEKLY_LOSS, MAX_DRAWDOWN

STATE=Path(os.getenv('STATE_PATH','/data/paper.json'))
ET=ZoneInfo('America/New_York')

def bars_download():
    import yfinance as yf
    end=datetime.now(timezone.utc).date()+timedelta(days=1)
    start=end-timedelta(days=160)
    data={}
    for symbol in UNIVERSE:
        df=yf.download(symbol,start=str(start),end=str(end),interval='1d',auto_adjust=False,progress=False,threads=False)
        if df.empty: continue
        # Some yfinance versions return MultiIndex columns.
        if getattr(df.columns,'nlevels',1)>1: df.columns=df.columns.get_level_values(0)
        rows=[]
        for idx,r in df.iterrows():
            vals={k:float(r[k]) for k in ['Open','High','Low','Close','Volume']}
            if all(math.isfinite(v) for v in vals.values()) and vals['Close']>0 and vals['Volume']>0:
                rows.append({'date':str(idx.date()),'open':vals['Open'],'high':vals['High'],'low':vals['Low'],'close':vals['Close'],'volume':vals['Volume']})
        data[symbol]=rows
    return data

def save(state):
    STATE.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=STATE.parent,delete=False) as f:
        json.dump(state,f,indent=2);f.flush();os.fsync(f.fileno());tmp=f.name
    os.replace(tmp,STATE)

def initial():
    return {'cash':ACCOUNT_CASH,'positions':{},'pending':[],'trades':[],'equity_peak':ACCOUNT_CASH,'weekly_realized_pnl':0,'week':None,'last_processed':None,'halted':False}

def process_day(state,day,history):
    if state['last_processed'] and day<=state['last_processed']:return False
    bysym={s:next((r for r in reversed(rows) if r['date']==day),None) for s,rows in history.items()}
    spy=history.get('SPY',[]);spy=[r for r in spy if r['date']<=day]
    if not spy or spy[-1]['date']!=day:raise ValueError('Missing SPY bar: fail closed')
    week=datetime.fromisoformat(day).strftime('%G-W%V')
    if state['week']!=week:state['week']=week;state['weekly_realized_pnl']=0
    # Fill previous close's signals at NEXT session open; never use future close to decide entry.
    queued=state['pending'];state['pending']=[]
    for q in queued:
        s=q['symbol'];bar=bysym.get(s)
        if not bar or len(state['positions'])>=MAX_POSITIONS or s in state['positions'] or state['halted']:continue
        entry=round(bar['open'],2);stop=q['stop'];per_share=entry-stop
        if per_share<=0 or entry>q['signal_close']*1.01:continue # reject adverse gap >1%
        exposure=sum(p['qty']*bysym[t]['open'] for t,p in state['positions'].items() if bysym.get(t))
        room=min(MAX_EXPOSURE-exposure,state['cash']-RESERVE)
        qty=min(math.floor(RISK/per_share),math.floor(room/entry))
        if qty<=0:continue
        target=round(entry+2*per_share,2)
        state['cash']=round(state['cash']-qty*entry,2)
        state['positions'][s]={'qty':qty,'entry':entry,'stop':stop,'target':target,'entry_date':day}
        state['trades'].append({'date':day,'action':'BUY_PAPER','symbol':s,'qty':qty,'price':entry})
    # Same-day stop/target checks. Stop wins ambiguous intraday touches.
    for s,p in list(state['positions'].items()):
        b=bysym.get(s)
        if not b:continue
        price=reason=None
        if b['open']<=p['stop']:price=b['open'];reason='gap_stop'
        elif b['low']<=p['stop']:price=p['stop'];reason='stop'
        elif b['open']>=p['target']:price=b['open'];reason='gap_target'
        elif b['high']>=p['target']:price=p['target'];reason='target'
        if price is not None:
            pnl=round(p['qty']*(price-p['entry']),2)
            state['cash']=round(state['cash']+p['qty']*price,2)
            state['weekly_realized_pnl']=round(state['weekly_realized_pnl']+pnl,2)
            state['trades'].append({'date':day,'action':'SELL_PAPER','symbol':s,'qty':p['qty'],'price':price,'pnl':pnl,'reason':reason})
            del state['positions'][s]
    equity=state['cash']+sum(p['qty']*bysym[s]['close'] for s,p in state['positions'].items() if bysym.get(s))
    state['equity_peak']=max(state['equity_peak'],equity)
    drawdown=state['equity_peak']-equity
    state['halted']=state['halted'] or state['weekly_realized_pnl']<=-WEEKLY_LOSS or drawdown>=MAX_DRAWDOWN
    # End-of-day screening. Require every held symbol to have a current bar.
    if any(bysym.get(s) is None for s in state['positions']):state['halted']=True
    if not state['halted']:
        picks=[]
        for s,rows in history.items():
            if s=='SPY' or s in state['positions'] or bysym.get(s) is None:continue
            past=[r for r in rows if r['date']<=day]
            sig=evaluate(past,spy)
            if sig and sig['qualified']:
                picks.append({'symbol':s,'stop':sig['stop'],'signal_close':sig['close'],'score':sig['relative_volume']+sig['relative_strength'],'signal_date':day})
        state['pending']=sorted(picks,key=lambda p:p['score'],reverse=True)[:max(0,MAX_POSITIONS-len(state['positions']))]
    state['last_processed']=day
    print(json.dumps({'date':day,'mode':'PAPER_ONLY','cash':state['cash'],'equity':round(equity,2),'drawdown':round(drawdown,2),'halted':state['halted'],'positions':state['positions'],'queued':state['pending']}),flush=True)
    return True

def run_once():
    if any(os.getenv(k) for k in ('LIVE_TRADING','ROBINHOOD_TOKEN','ROBINHOOD_API_KEY')):raise RuntimeError('Live credentials or flags prohibited')
    if os.getenv('KILL_SWITCH','false').lower()=='true':print('KILL_SWITCH active: no processing');return
    now=datetime.now(ET)
    if now.weekday()>=5 or now.hour<17:print('Waiting for completed US trading session');return
    history=bars_download()
    if 'SPY' not in history or len(history['SPY'])<56:raise RuntimeError('Insufficient SPY history; no trading')
    state=json.loads(STATE.read_text()) if STATE.exists() else initial()
    # No historical paper fills on initial deployment: only the latest completed bar.
    latest=history['SPY'][-1]['date']
    if latest!=now.date().isoformat():print('No completed current-day SPY bar; no action');return
    if process_day(state,latest,history):save(state)

if __name__=='__main__':
    if os.getenv('RUN_ONCE','false').lower()=='true':run_once()
    else:
        while True:
            try:run_once()
            except Exception as e:print('FAIL_CLOSED:',repr(e),flush=True)
            time.sleep(3600)
