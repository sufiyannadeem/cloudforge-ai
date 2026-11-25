#!/usr/bin/env python3
"""Read-only GitHub Actions evidence binding; never dispatches a workflow."""
import argparse
import json
import os
import re
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def require(run_id,attempt,workflow,job):
    if not re.fullmatch('[1-9][0-9]*',str(run_id)) or not re.fullmatch('[1-9][0-9]*',str(attempt)):
        raise ValueError('Exact positive run ID/attempt required')
    repo=os.environ['GITHUB_REPOSITORY'];sha=os.environ['GITHUB_SHA']
    if not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) or not re.fullmatch('[a-f0-9]{40}',sha):
        raise ValueError('Invalid source identity')
    def get(path):
        request=urllib.request.Request('https://api.github.com/repos/'+repo+path,headers={
            'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json',
            'X-GitHub-Api-Version':'2022-11-28','User-Agent':'CloudForge-same-sha-verification'})
        with urllib.request.build_opener(NoRedirect).open(request,timeout=15) as response:raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('Evidence response budget exceeded')
        return json.loads(raw)
    run=get('/actions/runs/'+str(run_id))
    if (run.get('head_sha')!=sha or run.get('head_repository',{}).get('full_name')!=repo
        or run.get('event')!='workflow_dispatch' or run.get('path')!=workflow
        or run.get('conclusion')!='success' or run.get('status')!='completed'
        or run.get('run_attempt')!=int(attempt)):
        raise ValueError('Successful same-repository/same-SHA exact workflow run required')
    jobs=get('/actions/runs/'+str(run_id)+'/attempts/'+str(attempt)+'/jobs?per_page=100')
    selected=[value for value in jobs['jobs'] if value['name']==job]
    if len(selected)!=1 or selected[0].get('conclusion')!='success':raise ValueError('Required exact gate did not succeed')
    print('Bound successful',job,'run',run_id,'attempt',attempt,'to source',sha)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-id',required=True);parser.add_argument('--attempt',required=True)
    parser.add_argument('--kind',choices=['integration','preparation'],required=True);args=parser.parse_args()
    if os.getenv('GITHUB_ACTIONS')!='true':parser.exit(2,'GitHub Actions evidence binding only\n')
    require(args.run_id,args.attempt,
        '.github/workflows/consolidated-release-verification.yml' if args.kind=='integration' else '.github/workflows/semantic-release-verification.yml',
        'integration-verification' if args.kind=='integration' else 'semantic-preparation')
