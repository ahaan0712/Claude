#!/usr/bin/env python3
from schema import write_json
import json
from pathlib import Path
def main():
    cal=json.load(open('data/lane_calibration.json')) if Path('data/lane_calibration.json').exists() else {}
    write_json('data/portfolio.json', {'schema_version':'campaign27.canonical.v1','message':'Expected-interview estimates are not available yet. Log 20 outcomes in a role lane to enable calibration.','calibration':cal,'calibrated_curve':[]})
if __name__=='__main__': main()
