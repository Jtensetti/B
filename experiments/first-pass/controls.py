"""Check the feedback and independent scorer on known good, joint-broken and unseen edits."""
import json
import tempfile
from pathlib import Path

from b_lang.compiler import compile_b
from b_lang.joint import check_joint

from feedback import feedback
from oracle import score
from properties import RULES, check_native


def same_evidence(source, task):
    compiled = compile_b(source)
    ns = {}
    exec(compiled.code, ns)
    for rule in RULES[task]:
        native = check_joint(compiled.ir, rule.request())
        python = check_native(rule, ns)
        for k in ("status", "checked_pairs", "witness", "failed_comparison"):
            assert native.get(k) == python.get(k), (rule.name, k, native, python)


def main():
    folder = Path(__file__).resolve().parent
    for task in ("pagination", "presses"):
        src = (folder/task/'program.bee').read_text().splitlines()
        if task=="pagination":
            # Count the correction to a three-unit average for completed pairs.
            body = "if compact == 0 then row * 4 else 1 + 3 * row - row % 2 + (if row >= 2 then 1 else 0) + (if row >= 5 then 2 else 0)"
            src[0] = src[0].split(" = ")[0] + " = " + body
            src[1] = src[1].split(" = ")[0] + " = start(row, compact) + (if compact == 1 and row % 2 == 0 then 2 else 4)"
            public_bug = "if compact == 1 and row == 5 then 1 else 0"
            private_bug = "if compact == 1 and row == 8 then 1 else 0"
        else:
            src[:0] = [
                "fn available(t: Int, r: Int) -> Int pure = if r == 1 and t >= 4 then t - 1 else t",
                "fn request(t: Int, q: Int, r: Int) -> Int pure = if r == 1 and available(t,r) >= 3 and q > 0 then q + 1 else q",
                "fn ceiling(t: Int, r: Int) -> Int pure = if r == 1 and available(t,r) >= 2 then available(t,r) - 1 else available(t,r)",
            ]
            src[3] = src[3].split(" = ")[0] + " = if request(total,quota,rush) < ceiling(total,rush) then request(total,quota,rush) else ceiling(total,rush)"
            src[4] = src[4].split(" = ")[0] + " = available(total,rush) - fast(total,quota,rush)"
            public_bug = "if rush == 1 and total == 6 then 1 else 0"
            private_bug = "if rush == 1 and total == 7 then 1 else 0"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"program.bee"
            for kind, bug in (("correct",None),("covered defect",public_bug),("unseen defect",private_bug)):
                lines = src.copy()
                if bug is not None:
                    index = 0 if task=="pagination" else 4
                    prefix, current = lines[index].split(' = ', 1)
                    lines[index] = f"{prefix} = ({current}) + ({bug})"
                source = "\n".join(lines)+"\n"
                path.write_text(source)
                same_evidence(source,task)
                public = feedback(source,task,"B")
                row = {"task":task,"control":kind,"examples_pass":all(g["ok"] for g in public["public"]),
                       "violated":[g["property"] for g in public["joint_properties"] if g["status"]!="passed"],
                       "acceptance":score(path,task)}
                print(json.dumps(row))


if __name__ == "__main__":
    main()
