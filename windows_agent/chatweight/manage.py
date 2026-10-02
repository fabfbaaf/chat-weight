from __future__ import annotations
import argparse
import time
from pathlib import Path
from .db import ChatWeightDb
from .models import RelationshipType
from .pipeline import RealtimeAnalysisPipeline


def main(argv=None):
    p=argparse.ArgumentParser(description='ChatWeight local management')
    p.add_argument('--db',default='chatweight.db')
    p.add_argument('--schema',default=str(Path(__file__).resolve().parents[2]/'sql'/'schema.sql'))
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('people')
    s=sub.add_parser('set-type'); s.add_argument('person_id'); s.add_argument('type',choices=[x.value for x in RelationshipType])
    r=sub.add_parser('pending'); r.add_argument('--limit',type=int,default=30)
    c=sub.add_parser('confirm'); c.add_argument('candidate_id')
    x=sub.add_parser('reject'); x.add_argument('candidate_id')
    args=p.parse_args(argv)
    db=ChatWeightDb(args.db,args.schema); pipe=RealtimeAnalysisPipeline(db)
    try:
        if args.cmd=='people':
            for row in db.conn.execute('SELECT id,display_name FROM persons ORDER BY updated_at DESC'):
                prof=db.get_relationship_profile(row['id'],int(time.time()*1000))
                print(f"{row['id']}\t{row['display_name']}\t{prof.relationship_type.value}\tstage={int(prof.expression_stage)}")
        elif args.cmd=='set-type':
            db.set_relationship_type(args.person_id,RelationshipType(args.type),int(time.time()*1000)); print('OK')
        elif args.cmd=='pending':
            for row in db.pending_candidates(args.limit):
                print(f"{row['id']}\t{row['event_type']}\t{row['confidence']:.2f}\t{row['evidence_text'] or ''}")
        elif args.cmd=='confirm': print('OK' if pipe.confirm_candidate(args.candidate_id) else 'NOT_FOUND_OR_REJECTED')
        elif args.cmd=='reject': print('OK' if pipe.reject_candidate(args.candidate_id) else 'NOT_FOUND')
    finally: db.close()
    return 0

if __name__=='__main__': raise SystemExit(main())
