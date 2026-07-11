#!/usr/bin/env python3
import subprocess, sys
steps=['import_target_universe.py','watchlist.py','discover.py','ingest.py','enrich.py','dol_lookup.py','build_network_aggregates.py','calibrate.py','portfolio.py','score.py','build_reports.py','build_site.py']
for s in steps:
    print('==',s)
    subprocess.check_call([sys.executable,s])
