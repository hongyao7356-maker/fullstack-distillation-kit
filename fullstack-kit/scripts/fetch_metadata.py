#!/usr/bin/env python3
"""Optional metadata-only GitHub API fetch; never clones or executes remote code."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def github_path(url:str)->str|None:
    p=urlparse(url)
    if p.scheme!="https" or p.netloc!="github.com": return None
    pieces=[x for x in p.path.strip("/").split("/") if x]
    if len(pieces)!=2: return None
    if any(x in {"..","."} for x in pieces): return None
    return "/".join(pieces)


def fetch_repo(repo:str,token:str|None=None)->dict:
    headers={"User-Agent":"fullstack-distillation-metadata-only/1.0","Accept":"application/vnd.github+json"}
    if token: headers["Authorization"]="Bearer "+token
    url="https://api.github.com/repos/"+repo
    req=Request(url,headers=headers)
    with urlopen(req,timeout=12) as resp:
        obj=json.load(resp)
    return {"full_name":obj.get("full_name"),"html_url":obj.get("html_url"),"default_branch":obj.get("default_branch"),
            "pushed_at":obj.get("pushed_at"),"archived":obj.get("archived"),"license":(obj.get("license") or {}).get("spdx_id"),
            "size_kb":obj.get("size"),"open_issues_count":obj.get("open_issues_count"),
            "latest_branch_sha":fetch_branch_sha(repo,obj.get("default_branch"),headers)}


def fetch_branch_sha(repo,branch,headers):
    if not branch: return None
    from urllib.parse import quote
    req=Request("https://api.github.com/repos/"+repo+"/commits/"+quote(branch,safe=""),headers=headers)
    with urlopen(req,timeout=12) as resp: return json.load(resp).get("sha")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--project",default=".")
    a=p.parse_args()
    project=Path(a.project).resolve()
    kit=Path(__file__).resolve().parents[1]
    registry=json.loads((kit/"sources"/"source_registry.json").read_text(encoding="utf-8"))
    records=[]
    for source in registry["sources"]:
        repo=github_path(source["url"])
        if not repo: continue
        try:
            metadata=fetch_repo(repo,os.getenv("GITHUB_TOKEN"))
            records.append({"source_id":source["id"],"status":"fetched","data":metadata})
            print("FETCHED",repo,metadata.get("latest_branch_sha"))
        except (HTTPError,URLError,TimeoutError,ValueError) as exc:
            records.append({"source_id":source["id"],"status":"unavailable","error":f"{type(exc).__name__}: {getattr(exc,'code','network failure')}"})
            print("SKIP",repo,type(exc).__name__)
    output=project/".fullstack"/"sources"/"metadata.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    # Use fresh snapshot, but don't clobber an existing one: create time-stamped evidence instead.
    if output.exists():
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output=output.with_name("metadata-"+stamp+".json")
        if output.exists():
            print("Snapshot collision, refusing overwrite")
            raise SystemExit(2)
    output.write_text(json.dumps({"retrieved_at":datetime.now(timezone.utc).isoformat(),"repos":records},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("SAVED",output)


if __name__=="__main__": main()
