#!/usr/bin/env python3
"""Independent set/join oracle for the recorded registered-operation author task.
Reads JSON-RPC evidence only; never calls DDlog or imports backend implementation.
The supplied program is checked against the reviewed routing contract, so this
is a task-specific oracle, not a general Datalog interpreter.
"""
import argparse
import json
from pathlib import Path
import re

ROUTE_RULE = 'route(E,R,P,O,C) :- agent_result(E,R,C), project(E,P), owner(P,C,O), urgency(C,S), S =< 2.'

def rows(text):
    result=set()
    pattern=r'\.f\d+ = ("(?:[^"\\]|\\.)*"|-?\d+)'
    for line in text.splitlines():
        assert line.startswith('R_route{') and line.endswith('}'), line
        values=tuple(json.loads(value) for value in re.findall(pattern,line))
        assert len(values)==5,line
        result.add(values)
    return result

def verify(folder):
    folder=Path(folder)
    program=json.loads((folder/'program.json').read_text())
    assert program['rules']==ROUTE_RULE, 'Oracle is scoped to the independently reviewed routing rule'
    registry=json.loads((folder/'operations.json').read_text())
    operation=program['operation']; version=registry[operation]['version']
    requests=[json.loads(line) for line in (folder/'requests.jsonl').read_text().splitlines() if line.strip()]
    responses=[json.loads(line) for line in (folder/'responses.jsonl').read_text().splitlines() if line.strip()]
    assert len(requests)==len(responses), 'Missing responses'
    assert len({r['id'] for r in requests})==len(requests), 'Repeated RPC identity'
    by_id={r['id']:r for r in responses}
    assert len(by_id)==len(responses), 'Repeated response identity'
    facts={'project':set(),'owner':set(),'urgency':set()}
    current={}; admitted=set(); completed={}; intents={}
    checks=0; stale=0; duplicate_claims=0; errors=0
    snapshots=[]
    for request in requests:
        result=by_id[request['id']]['result']
        if request['method']!='tools/call': continue
        name=request['params']['name']; args=request['params'].get('arguments',{})
        failed=result.get('isError',False)
        if failed:
            errors+=1
            if name=='claim_agent_request':
                identity=args['request_id']
                assert identity in admitted or identity not in intents or current.get(intents[identity][0])!=identity
                duplicate_claims+=identity in admitted
            elif name=='complete_agent_request':
                identity=args['request_id']
                assert identity not in admitted or (identity in completed and completed[identity]!=args['output'])
            elif name=='submit_agent_input':
                old=intents[current[args['entity']]]
                assert args['revision']<old[1] or (args['revision']==old[1] and args['payload']!=old[2])
            else:
                raise AssertionError(f'Unexpected tool error at {request["id"]}: {name}: {result}')
            continue
        data=json.loads(result['content'][0]['text'])
        if name=='apply_changes':
            for change in args['changes']:
                target=facts[change['predicate']]; row=tuple(change['values'])
                if change['op']=='insert':target.add(row)
                elif change['op']=='delete':target.discard(row)
                else:raise AssertionError('Invalid mutation operation')
        elif name=='submit_agent_input':
            e,r,p=args['entity'],args['revision'],args['payload']
            expected=json.dumps([operation,version,e,r,p],ensure_ascii=False,separators=(',',':'))
            assert data['request_id']==expected, 'Identity differs from exact operation/input tuple'
            if e in current:
                previous=intents[current[e]]
                assert r>=previous[1] and (r!=previous[1] or p==previous[2])
            intents[expected]=(e,r,p);current[e]=expected;checks+=1
        elif name=='claim_agent_request':
            identity=args['request_id'];e,r,p=intents[identity]
            assert current[e]==identity and identity not in admitted and identity not in completed
            assert data['payload']==p and data['revision']==r and data['entity']==e
            admitted.add(identity);checks+=1
        elif name=='complete_agent_request':
            identity=args['request_id'];e,r,p=intents[identity]
            assert identity in admitted
            fresh=current[e]==identity
            assert data['fresh']==fresh
            assert data['duplicate']==(identity in completed)
            if identity in completed:assert completed[identity]==args['output']
            completed[identity]=args['output'];stale+=not fresh;checks+=1
        elif name=='lemmalog_query' and args['predicate']=='route':
            expected=set()
            for e,identity in current.items():
                if identity not in completed:continue
                classification=completed[identity];revision=intents[identity][1]
                for entity,project in facts['project']:
                    if entity!=e:continue
                    for owner_project,category,owner in facts['owner']:
                        if owner_project!=project or category!=classification:continue
                        if any(c==classification and s<=2 for c,s in facts['urgency']):
                            expected.add((e,revision,project,owner,classification))
            actual=rows(data['rows'])
            assert actual==expected, f'Routing mismatch at RPC {request["id"]}: {actual} vs {expected}'
            snapshots.append({'rpc':request['id'],'rows':sorted(actual)});checks+=1
        elif name=='lemmalog_why':
            assert args['rule']==0, 'Oracle covers the authored routing rule only'
            expected=set()
            for e,identity in current.items():
                if identity not in completed:continue
                category=completed[identity];revision=intents[identity][1]
                for entity,project in facts['project']:
                    if entity!=e:continue
                    for owner_project,owner_category,owner in facts['owner']:
                        if owner_project!=project or owner_category!=category:continue
                        for urgency_category,severity in facts['urgency']:
                            if urgency_category==category and severity<=2:
                                expected.add((category,e,owner,project,revision,severity))
            actual=set()
            for line in data['bindings'].splitlines():
                assert line.startswith('Evidence0{') and line.endswith('}'), line
                bindings=dict(re.findall(r'\.v_([CEOPRS]) = ("(?:[^"\\]|\\.)*"|-?\d+)',line))
                assert set(bindings)==set('CEOPRS'), line
                actual.add(tuple(json.loads(bindings[key]) for key in 'CEOPRS'))
            assert actual==expected, f'Witness mismatch at RPC {request["id"]}'
            checks+=1
        elif name=='agent_request_status':
            actual={item['request_id']:item for item in data['requests']}
            assert set(actual)==set(intents)
            for identity,(e,r,p) in intents.items():
                item=actual[identity]
                assert item['fresh']==(current[e]==identity)
                assert item['status']==('completed' if identity in completed else 'claimed' if identity in admitted else 'pending')
            checks+=1
    assert stale>=1 and duplicate_claims>=1 and len(current)>=2 and len(snapshots)>=3
    return {'passed':True,'rpc_exchanges':len(requests),'independent_checks':checks,'stale_completions':stale,'duplicate_claim_rejections':duplicate_claims,'expected_errors':errors,'entities':len(current),'route_snapshots':snapshots,'scope':'Agent-authored routing/lifecycle correctness; does not score model classification quality or prove durable execution'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');args=parser.parse_args()
    print(json.dumps(verify(args.folder),indent=2))
