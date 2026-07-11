#!/usr/bin/env python3
import csv,json
from pathlib import Path
from collections import defaultdict
from schema import write_json
THRESHOLD=20
LANES=['DATA_ANALYTICS','DATA_SCIENCE','BUSINESS_INTELLIGENCE','BUSINESS_ANALYTICS','ADJACENT_ANALYTICS']
def main():
    counts=defaultdict(lambda:{'applications':0,'outcomes':0,'interviews':0})
    if Path('data/outcomes.csv').exists():
        for r in csv.DictReader(open('data/outcomes.csv')):
            lane=r.get('role_family') or 'DATA_ANALYTICS'; counts[lane]['applications']+=1
            if r.get('interviewed') not in [None,'']: counts[lane]['outcomes']+=1; counts[lane]['interviews']+=1 if r.get('interviewed') in ['1','yes','Yes','TRUE','True'] else 0
    lanes=[]
    for lane in LANES:
        c=counts[lane]; ready=c['outcomes']>=THRESHOLD
        lanes.append({'role_family':lane,**c,'calibration_status':'CALIBRATED' if ready else 'PRIOR_ONLY','calibrated_probability':None,'outcomes_needed_for_calibration':max(0,THRESHOLD-c['outcomes'])})
    write_json('data/lane_calibration.json', {'threshold':THRESHOLD,'message':'Expected-interview estimates are not available yet. Log 20 outcomes in a role lane to enable calibration.','lanes':lanes})
if __name__=='__main__': main()
