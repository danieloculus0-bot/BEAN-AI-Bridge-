"""Reproduce BEAN's 2026-10-22 pair-ledger research. Synthetic, no external input.

Uses only Python stdlib. Saves every original value and full chain in SQLite
and a gzip event log; compares fully costed reversible representations.
"""
from __future__ import annotations
import argparse
import bz2
import gzip
import hashlib
import json
import lzma
import random
import sqlite3
import struct
from pathlib import Path

SEED = 220261022
N = 3000
CASES = {'high_reuse': 4, 'moderate_reuse': 24, 'low_reuse': 80}
ALPHABETS = ('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz', '0123456789', '!#$%&()*+,-./:;<=>?@[]^_\\|~')
SCHEMA = 'bean.pair-ledger.exp.v1'
EXPECTED = {
 'events': 9000,
 'events_gzip_sha256': '29f97009d9e235628f063701942266c662b2b827ede0cfc4973677693c1a85c2',
 'comparison_gzip_sha256': '66098d3a984211e96d136aa9fc646e1309d3ad0d0b81cda5ab69025375b6e383',
 'ledger_tip': '75e66debfaf1bed0b83f337a7babb830daffa3ce3ddd86fda98bf8b6d62357f0',
 'bytes': {
   'high_reuse': [15140, 8609, 7131, 10499],
   'moderate_reuse': [57709, 25112, 17675, 45284],
   'low_reuse': [112537, 37730, 25758, 63733],
 }
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(b):
    return hashlib.sha256(b).hexdigest()


def gzip9(b):
    return gzip.compress(b, compresslevel=9, mtime=0)


def records(nv):
    rng = random.Random(SEED + nv * 37)
    vocab = [[f'inspection.slot{s}.attribute{v:03d}.' +
              ''.join(rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(7)) +
              '.observation' for v in range(nv)] for s in range(8)]
    out = []
    for i in range(N):
        parent = rng.randrange(max(2, nv // 3))
        row = []
        for s in range(8):
            j = ((parent*7 + s*11 + rng.randrange(max(1, nv//3))) % nv
                 if s in (0, 1, 2) else rng.randrange(nv))
            row.append(vocab[s][j])
        out.append(row)
    return out, vocab


def encode(rows, vocab):
    codes = [[''.join(t) for t in __import__('itertools').product(ALPHABETS[s%4], repeat=2)][:len(vocab[s])] for s in range(8)]
    dictionaries = [dict(zip(codes[s], vocab[s])) for s in range(8)]
    inverse = [{v:k for k,v in d.items()} for d in dictionaries]
    encoded = [''.join(inverse[s][value] for s,value in enumerate(row)) for row in rows]
    assert all(len(row)==16 for row in encoded)
    return encoded, dictionaries


def decode(encoded, dictionaries):
    return [[dictionaries[s][line[2*s:2*s+2]] for s in range(8)] for line in encoded]


def pair_blob(encoded, dictionaries):
    header = canonical({'schema':SCHEMA, 'columns':8, 'codes':dictionaries})
    return b'BEAN2P1' + struct.pack('>I', len(header)) + header + ''.join(encoded).encode('ascii')


def onebyte_blob(rows, vocab):
    inverse = [{v:i for i,v in enumerate(values)} for values in vocab]
    body = bytes(inverse[s][v] for row in rows for s,v in enumerate(row))
    head = canonical({'schema':'bean.1byte.control.v1','dictionary':vocab,'n':len(rows)})
    blob = b'B1B' + struct.pack('>I',len(head)) + head + body
    recovered = [[vocab[s][blob[7+len(head)+i*8+s]] for s in range(8)] for i in range(len(rows))]
    assert recovered == rows
    return blob


def hierarchy_blob(encoded, dictionaries):
    nodes = [(0, b'\0\0\0\0')]
    lookup = {}
    leaves = []
    for row in encoded:
        parent=0
        for offset in (0,4,8,12):
            key=(parent,row[offset:offset+4].encode('ascii'))
            if key not in lookup:
                nodes.append(key)
                lookup[key] = len(nodes)-1
            parent=lookup[key]
        leaves.append(parent)
    assert len(nodes)<65536
    head=canonical({'schema':'bean.pair.hierarchy.v1','codes':dictionaries,'count':len(encoded),'nodes':len(nodes)-1})
    blob=b'B2H'+struct.pack('>I',len(head))+head+ b''.join(struct.pack('>H4s',p,c) for p,c in nodes[1:])+b''.join(struct.pack('>H',v) for v in leaves)
    body=blob[7+len(head):]
    reconstructed=[(0,b'\0'*4)] + [struct.unpack('>H4s',body[i*6:(i+1)*6]) for i in range(len(nodes)-1)]
    split=(len(nodes)-1)*6
    roundtrip=[]
    for i in range(len(encoded)):
        node=struct.unpack('>H',body[split+i*2:split+i*2+2])[0]
        segments=[]
        while node:
            parent,chunk=reconstructed[node]
            segments.append(chunk)
            node=parent
        assert len(segments)==4
        roundtrip.append(b''.join(reversed(segments)).decode('ascii'))
    assert roundtrip == encoded
    return blob


def execute(output: Path, verify=True):
    output.mkdir(parents=True, exist_ok=True)
    dbpath=output/'events.sqlite'
    if dbpath.exists(): dbpath.unlink()
    db=sqlite3.connect(dbpath)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE events(seq INTEGER PRIMARY KEY,run_id TEXT,condition TEXT,source_json TEXT,code TEXT,decoded_sha TEXT,payload_sha TEXT,previous_hash TEXT,chain_hash TEXT,UNIQUE(run_id,seq))''')
    seq=0;prev='GENESIS'
    comparison=[];comp_prev='GENESIS';summaries={}
    for condition,nv in CASES.items():
        rows,vocab=records(nv)
        encoded,dictionaries=encode(rows,vocab)
        assert decode(encoded,dictionaries)==rows
        original=canonical(rows)
        pairs=pair_blob(encoded,dictionaries)
        pack=onebyte_blob(rows,vocab)
        tree=hierarchy_blob(encoded,dictionaries)
        compressed={
          'json_gzip':gzip9(original),
          'pair_gzip':gzip9(pairs),
          'onebyte_gzip':gzip9(pack),
          'hierarchy_gzip':gzip9(tree),
          'json_bz2':bz2.compress(original,compresslevel=9),
          'json_lzma':lzma.compress(original,preset=6),
        }
        assert gzip.decompress(compressed['pair_gzip'])==pairs
        assert gzip.decompress(compressed['json_gzip'])==original
        assert bz2.decompress(compressed['json_bz2'])==original
        assert lzma.decompress(compressed['json_lzma'])==original
        for name in ('json_gzip','pair_gzip','onebyte_gzip','hierarchy_gzip'):
            (output/f'{condition}_{name}.bin.gz').write_bytes(compressed[name])
        sizes=[len(compressed[k]) for k in ('json_gzip','pair_gzip','onebyte_gzip','hierarchy_gzip')]
        summaries[condition]={'sizes':dict(zip(('json_gzip','pair_gzip','onebyte_gzip','hierarchy_gzip'),sizes)),
            'gain_over_json_gzip_percent':round((sizes[0]-sizes[1])*100/sizes[0],3),
            'pair_vs_onebyte_percent':round((sizes[2]-sizes[1])*100/sizes[2],3),
            'full_values':len(rows)*8}
        for i,(row,code) in enumerate(zip(rows,encoded)):
            seq+=1
            run_id=f'{condition}-{i:04d}'
            decoded_sha=digest(canonical(row))
            event={'seq':seq,'run_id':run_id,'condition':condition,'values':row,'pair_code':code,
                   'decoded_sha256':decoded_sha,'evidence_kind':'synthetic','schema':SCHEMA,'passed':True}
            fingerprint=digest(canonical(event))
            tip=digest(canonical([prev,fingerprint]))
            db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',
                       (seq,run_id,condition,canonical(row).decode(),code,decoded_sha,fingerprint,prev,tip))
            prev=tip
        db.commit()
        for n in (5,20,100,N):
            row={'id':f'{condition}-{n}','condition':condition,'rows':n,
                 'baseline_gzip_bytes':len(gzip9(canonical(rows[:n]))),
                 'pair_gzip_bytes':len(gzip9(pair_blob(encoded[:n],dictionaries)))}
            row['gain_percent']=round((row['baseline_gzip_bytes']-row['pair_gzip_bytes'])*100/row['baseline_gzip_bytes'],3)
            payload=digest(canonical(row))
            tip=digest(canonical([comp_prev,payload]))
            row.update({'payload_sha256':payload,'previous_hash':comp_prev,'chain_hash':tip})
            comparison.append(row);comp_prev=tip
    db.close()
    # Independently reopen SQLite and reconstruct every event/hash, including original data.
    db=sqlite3.connect(dbpath)
    results=db.execute('SELECT * FROM events ORDER BY seq').fetchall()
    assert len(results)==9000
    previous='GENESIS';lines=[]
    for i,run_id,condition,source_json,code,decoded_sha,payload_sha,old,tip in results:
        values=json.loads(source_json)
        event={'seq':i,'run_id':run_id,'condition':condition,'values':values,'pair_code':code,
               'decoded_sha256':decoded_sha,'evidence_kind':'synthetic','schema':SCHEMA,'passed':True}
        assert old==previous and digest(canonical(event))==payload_sha
        assert digest(canonical([previous,payload_sha]))==tip and digest(canonical(values))==decoded_sha
        lines.append(canonical({**event,'payload_sha256':payload_sha,'previous_hash':old,'chain_hash':tip})+b'\n')
        previous=tip
    assert previous==prev
    try:
        db.execute('INSERT INTO events(seq,run_id) VALUES (?,?)',(1,'duplicate'))
    except sqlite3.IntegrityError:
        db.rollback()
    else:
        raise AssertionError('duplicate event accepted')
    assert digest(canonical([results[0][7],'0'*64]))!=results[0][8]
    db.close()
    full_log=gzip9(b''.join(lines))
    (output/'events_full.jsonl.gz').write_bytes(full_log)
    comparison_log=gzip9(b''.join(canonical(row)+b'\n' for row in comparison))
    (output/'comparison_events.jsonl.gz').write_bytes(comparison_log)
    result={'schema':'bean.bridge.pair_replay.v1','synthetic':True,'seed':SEED,
            'events':len(results),'values':len(results)*8,'comparison_events':len(comparison),
            'ledger_tip':prev,'comparison_tip':comp_prev,
            'events_gzip_sha256':digest(full_log),
            'comparison_gzip_sha256':digest(comparison_log),
            'conditions':summaries,'roundtrip_and_sqlite_restart':True,
            'runtime_changes':False,'q_learning_updates':0}
    if verify:
        assert result['events']==EXPECTED['events']
        assert hashlib.sha256(gzip.decompress((__import__('pathlib').Path(__import__('sys').argv[__import__('sys').argv.index('--out')+1])/'events_full.jsonl.gz').read_bytes())).hexdigest() == '2c26d2c2dc9ee483d4e01c38234d72de10da2e089d8de23fd2811657827e7ce7'
        assert result['ledger_tip']==EXPECTED['ledger_tip']
        assert hashlib.sha256(gzip.decompress((__import__('pathlib').Path(__import__('sys').argv[__import__('sys').argv.index('--out')+1])/'comparison_events.jsonl.gz').read_bytes())).hexdigest() == '5c89927515deac5e4cdd7486cd8e7274469e8f75f78e52a575f71530df1bd5ff'
        for key,row in result['conditions'].items():
            assert list(row['sizes'].values())==EXPECTED['bytes'][key],(key,row['sizes'])
    (output/'scoreboard.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=Path('two_char_output'))
    p.add_argument('--no-pin',action='store_true',help='check replay without enforcing recorded historical size/digests')
    args=p.parse_args()
    print(json.dumps(execute(args.out,verify=not args.no_pin),indent=2))

if __name__=='__main__':
    main()
