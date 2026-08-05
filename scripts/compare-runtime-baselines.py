#!/usr/bin/env python3
"""Deterministic, offline comparison of two validated V02B baselines."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import pathlib
import tempfile
import runtime_diff_core as _core
import runtime_diff_validation as _validation

_schema_spec=importlib.util.spec_from_file_location("runtime_schema",pathlib.Path(__file__).with_name("runtime-baseline-schema.py"))
_schema=importlib.util.module_from_spec(_schema_spec)
_schema_spec.loader.exec_module(_schema)
SchemaError=_schema.SchemaError
load=_schema.load
SCHEMA_V1=_core.SCHEMA_V1
SCHEMA_V2=_core.SCHEMA_V2
DOMAINS=_core.DOMAINS
report=_core.report
markdown=_core.markdown
summarize_v2=_core.summarize_v2
validate_report=_validation.validate_report

def die(_message,code=1):
    raise SystemExit(code)

def atomic(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(prefix=".v03-",dir=path.parent,text=True)
    try:
        with os.fdopen(descriptor,"w",encoding="utf-8",newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary,0o600)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def allowed(repo,path):
    resolved=path.resolve(strict=False)
    if not any(str(resolved).startswith(str(repo/name)+os.sep) for name in ("evidence","exports")):
        die("output outside evidence/exports")
    if resolved.exists():
        die("refusing overwrite")
    if any(item.is_symlink() for item in (resolved,*resolved.parents)):
        die("symlink output")
    return resolved

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--before",required=True)
    parser.add_argument("--after",required=True)
    parser.add_argument("--json-out",required=True)
    parser.add_argument("--markdown-out",required=True)
    arguments=parser.parse_args()
    if len({arguments.before,arguments.after,arguments.json_out,arguments.markdown_out})<2:
        die("invalid paths",2)
    repo=pathlib.Path(__file__).resolve().parent.parent
    try:
        before=load(arguments.before)
        after=load(arguments.after)
    except SchemaError:
        die("invalid baseline input")
    json_out=allowed(repo,pathlib.Path(arguments.json_out))
    markdown_out=allowed(repo,pathlib.Path(arguments.markdown_out))
    result=report(arguments.before,arguments.after,before,after)
    validate_report(result)
    atomic(json_out,json.dumps(result,sort_keys=True,indent=2)+"\n")
    atomic(markdown_out,markdown(result))

if __name__=="__main__":
    main()
