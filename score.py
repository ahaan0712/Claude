#!/usr/bin/env python3
import json
from pathlib import Path
from schema import write_json
def main():
    matches=json.load(open('data/live_matches.json')) if Path('data/live_matches.json').exists() else []
    review=json.load(open('data/review_queue.json')) if Path('data/review_queue.json').exists() else []
    excluded=json.load(open('data/excluded_postings.json')) if Path('data/excluded_postings.json').exists() else []
    write_json('data/matches.json', {'schema_version':'campaign27.canonical.v1','matches':matches,'review_queue':review,'excluded_postings':excluded,'note':'Trackers are supplemental; no ranks, scores, or probabilities are published.'})
if __name__=='__main__': main()
