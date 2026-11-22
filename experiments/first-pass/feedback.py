"""Matched public feedback. The acceptance oracle lives outside this path."""
import json
import sys
from pathlib import Path

from b_lang.compiler import compile_b
from b_lang.joint import check_joint

from properties import RULES, check_native

EXAMPLES = {
    "pagination":[("start",(0,1),1),("stop",(0,1),3),("start",(3,0),12),("page_tag",(1,),9)],
    "presses":[("fast",(6,2,0),2),("fast",(6,1,1),2),("slow",(4,4,1),1),("batch_tag",(1,),8)],
}


def python_diagnostic(rule, row):
    result = {"property":rule.name, "assertion":rule.ensures, "status":row["status"],
              "checked_pairs":row["checked_pairs"]}
    if row["status"] == "violated":
        calls = []
        for part in ("left", "right"):
            call = row["witness"][part]
            args = ", ".join(f"{n}={v}" for n,v in call["inputs"].items())
            calls.append(f"{call['function']}({args}) returned {call['result']}")
        comparison = row["failed_comparison"]
        lhs, op, rhs = comparison["left_value"], comparison["operator"], comparison["right_value"]
        result["failure"] = ". ".join(calls + [f"Assertion failed: {lhs} {op} {rhs}"])
    elif "reason" in row:
        result["reason"] = row["reason"]
    return result


def feedback(source, task, provider):
    try:
        compiled = compile_b(source)
        ns = {}
        exec(compiled.code,ns)
        public = []
        for name, args, expected in EXAMPLES[task]:
            try:
                actual = ns[name](*args)
            except Exception as exc:
                actual = type(exc).__name__
            public.append({"name":name,"args":args,"expected":expected,"observed":actual,
                           "ok":type(actual) is int and actual==expected})
        checks = []
        for rule in RULES[task]:
            row = check_joint(compiled.ir,rule.request()) if provider=="B" else check_native(rule,ns)
            checks.append({"property":rule.name, **row} if provider=="B" else python_diagnostic(rule,row))
        return {"compiled":True,"static_diagnostics":[vars(d) for d in compiled.diagnostics],
                "public":public,"joint_properties":checks}
    except Exception as exc:
        return {"compiled":False,"error":str(exc)}


if __name__=="__main__":
    print(json.dumps(feedback(Path(sys.argv[1]).read_text(),sys.argv[2],sys.argv[3]),sort_keys=True))
