#!/usr/bin/env python3
"""Paper-only ETF breakout bot. No network calls, credentials, or live orders."""
import argparse, csv, json, math, os
from datetime import datetime, timezone
from pathlib import Path

UNIVERSE = ['SPY','QQQ','IWM','XLF','XLV','XLY','XLP','RSP','SMH','XLE','XLK','XLI','XLB','XLU','XLC','DIA','EEM','EFA','TLT','GLD','SLV','IBB','XBI','KRE','IYR','VNQ','GDX','ARKK','VTI','SOXX']
CAPITAL=500.0; ACCOUNT_CASH=625.0; RESERVE=125.0; MAX_EXPOSURE=400.0; MAX_POSITIONS=2
RISK=2.50; WEEKLY_LOSS=10.0; MAX_DRAWDOWN=30.0

def load_bars(folder, symbol):
    path=Path(folder)/(symbol+'.csv')
    if not path.exists(): return []
    with path.open(newline='') as f:
        rows=list(csv.DictReader(f))
    result=[]
    for x in rows:
        try:
            result.append(dict(date=x['date'],open=float(x['open']),high=float(x['high']),low=float(x['low']),close=float(x['close']),volume=float(x['volume'])))
        except (KeyError,ValueError): continue
    return sorted(result,key=lambda x:x['date'])

def avg(a,key,n): return sum(x[key] for x in a[-n:])/n

def rsi14(bars):
    changes=[bars[i]['close']-bars[i-1]['close'] for i in range(len(bars)-14,len(bars))]
    gain=sum(max(v,0) for v in changes)/14; loss=sum(max(-v,0) for v in changes)/14
    return 100 if loss==0 else 100-100/(1+gain/loss)

def evaluate(bars,spy):
    if len(bars)<56 or len(spy)<56 or bars[-1]['date']!=spy[-1]['date']:return None
    close=bars[-1]['close']; ma20=avg(bars,'close',20); ma50=avg(bars,'close',50)
    spy50=avg(spy,'close',50); spy50prev=avg(spy[-55:-5],'close',50)
    market=spy[-1]['close']>spy50 and spy50>spy50prev
    high20=max(x['high'] for x in bars[-21:-1]); volavg=avg(bars[-21:-1],'volume',20)
    relvol=bars[-1]['volume']/volavg if volavg else 0
    strength=close/bars[-21]['close']-spy[-1]['close']/spy[-21]['close']
    rsi=rsi14(bars)
    qualified=(market and close>high20 and close>ma20>ma50 and relvol>=1.5 and 50<=rsi<=75 and strength>0)
    stop=round(min(x['low'] for x in bars[-10:])*0.997,2)
    return dict(date=bars[-1]['date'],close=close,ma20=ma20,ma50=ma50,market_pass=market,high20=high20,relative_volume=round(relvol,3),rsi=round(rsi,2),relative_strength=round(strength,5),stop=stop,qualified=qualified)

def run(folder,state_path):
    if os.getenv('LIVE_TRADING') or os.getenv('ROBINHOOD_TOKEN'):
        raise SystemExit('Refusing live-trading settings: this program is PAPER ONLY')
    state_file=Path(state_path)
    state=json.loads(state_file.read_text()) if state_file.exists() else {'cash':ACCOUNT_CASH,'positions':{},'orders':[],'realized_pnl':0.0,'weekly_realized_pnl':0.0,'equity_peak':ACCOUNT_CASH,'week':None,'last_processed_date':None}
    spy=load_bars(folder,'SPY')
    if not spy: raise SystemExit('Missing SPY.csv: supply historical OHLCV CSVs; see README')
    today=spy[-1]['date']; week=datetime.fromisoformat(today).strftime('%G-W%V')
    if state.get('week')!=week:state['week']=week;state['weekly_realized_pnl']=0.0
    if state.get('last_processed_date')==today:
        print(json.dumps({'status':'already_processed','date':today},indent=2));return
    bars={s:load_bars(folder,s) for s in UNIVERSE}
    prices={s:b[-1]['close'] for s,b in bars.items() if b and b[-1]['date']==today}
    # Mark to market and simulate protective exits at next session's open or intraday levels.
    # Conservative when both stop and target are hit: stop is assumed first.
    for s,p in list(state['positions'].items()):
        b=bars.get(s,[])
        if not b or b[-1]['date']!=today:continue
        candle=b[-1]
        if candle['date']<=p['entry_date']:continue
        exit_price=None;reason=None
        if candle['open']<=p['stop']:exit_price=candle['open'];reason='gap_below_stop'
        elif candle['low']<=p['stop']:exit_price=p['stop'];reason='stop'
        elif candle['open']>=p['target']:exit_price=candle['open'];reason='gap_above_target'
        elif candle['high']>=p['target']:exit_price=p['target'];reason='target'
        if exit_price is not None:
            proceeds=round(p['qty']*exit_price,2);cost=round(p['qty']*p['entry'],2);pnl=round(proceeds-cost,2)
            state['cash']=round(state['cash']+proceeds,2);state['realized_pnl']=round(state['realized_pnl']+pnl,2)
            state['weekly_realized_pnl']=round(state['weekly_realized_pnl']+pnl,2)
            state['orders'].append(dict(date=today,symbol=s,action='PAPER_SELL',qty=p['qty'],price=exit_price,pnl=pnl,reason=reason))
            del state['positions'][s]
    equity=state['cash']+sum(p['qty']*prices.get(s,p['entry']) for s,p in state['positions'].items())
    state['equity_peak']=max(state.get('equity_peak',ACCOUNT_CASH),equity)
    drawdown=state['equity_peak']-equity
    halted=state['weekly_realized_pnl']<=-WEEKLY_LOSS or drawdown>=MAX_DRAWDOWN
    # Signals are observed at close. Orders are QUEUED for manual review rather than
    # filled using that same close; this avoids look-ahead execution assumptions.
    candidates=[]
    if not halted:
        for s,b in bars.items():
            if s=='SPY' or s in state['positions'] or not b:continue
            sig=evaluate(b,spy)
            if sig and sig['qualified']:
                entry=round(sig['close'],2);stop=sig['stop'];per_share=entry-stop
                if per_share<=0:continue
                exposure=sum(p['qty']*prices.get(t,p['entry']) for t,p in state['positions'].items())
                room=min(MAX_EXPOSURE-exposure,state['cash']-RESERVE)
                qty=max(0,min(math.floor(RISK/per_share),math.floor(room/entry)))
                if qty:
                    candidates.append(dict(symbol=s,qty=qty,indicative_entry=entry,stop=stop,target=round(entry+2*per_share,2),estimated_risk=round(qty*per_share,2),score=round(sig['relative_volume']+sig['relative_strength'],4),signal_date=today,execution='REPRICE_AND_REVALIDATE_NEXT_SESSION'))
    candidates.sort(key=lambda x:x['score'],reverse=True)
    available_slots=max(0,MAX_POSITIONS-len(state['positions']))
    # Never execute orders here: candidate is a next-session watchlist, not a fill.
    state['pending_candidates']=candidates[:available_slots]
    state['last_processed_date']=today
    state_file.parent.mkdir(parents=True,exist_ok=True)
    state_file.write_text(json.dumps(state,indent=2))
    print(json.dumps({'mode':'PAPER_ONLY','date':today,'account_cash':round(state['cash'],2),'equity':round(equity,2),'weekly_realized_pnl':state['weekly_realized_pnl'],'drawdown':round(drawdown,2),'halted':halted,'positions':state['positions'],'next_session_candidates':state['pending_candidates'],'note':'No live orders. Next-session candidates require fresh prices, market validation, and separate execution simulation.'},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',default='data');parser.add_argument('--state',default='state/paper.json');args=parser.parse_args();run(args.data,args.state)
