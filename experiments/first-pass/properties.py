"""Public cross-call properties, written separately for B and for typed Python."""
from collections.abc import Callable
from dataclasses import dataclass
from itertools import product
import operator

Point = tuple[int, ...]
Guard = Callable[[Point, Point], bool]
Terms = Callable[[Point, Point, int, int], tuple[int, int]]
Functions = dict[str, Callable[..., int]]
OPS: dict[str, Callable[[int, int], bool]] = {"==": operator.eq, ">=": operator.ge}


@dataclass(frozen=True)
class Rule:
    name: str
    left: str
    right: str
    axes: dict[str, list[int]]
    where: str
    ensures: str
    relevant: Guard
    terms: Terms
    op: str = "=="

    def request(self) -> dict[str, object]:
        return {"left": {"function": self.left, "axes": self.axes},
                "right": {"function": self.right, "axes": self.axes},
                "where": self.where, "ensures": self.ensures}


PAGE = {"row": [0,1,2,4,5], "compact": [0,1]}
PRESS = {"total": [0,2,4,6], "quota": [0,1,2,4], "rush": [0,1]}
SAME_PAGE = "left_row == right_row and left_compact == right_compact"
NEXT = "right_row == left_row + 1 and left_compact == right_compact"
SAME_BATCH = "left_total == right_total and left_quota == right_quota and left_rush == right_rush"
RULES = {
    "pagination": [
        Rule("legacy width", "start","stop", PAGE, SAME_PAGE+" and left_compact == 0", "right_result - left_result == 4",
             lambda a,b:a==b and a[1]==0, lambda a,b,x,y:(y-x,4)),
        Rule("compact short rows", "start","stop", PAGE, SAME_PAGE+" and left_compact == 1 and (left_row == 0 or left_row == 2 or left_row == 4)", "right_result - left_result == 2",
             lambda a,b:a==b and a[1]==1 and a[0]%2==0, lambda a,b,x,y:(y-x,2)),
        Rule("compact long rows", "start","stop", PAGE, SAME_PAGE+" and left_compact == 1 and (left_row == 1 or left_row == 5)", "right_result - left_result == 4",
             lambda a,b:a==b and a[1]==1 and a[0]%2==1, lambda a,b,x,y:(y-x,4)),
        Rule("compact unsplit boundary", "stop","start", PAGE, NEXT+" and left_compact == 1 and left_row != 1 and left_row != 4", "right_result == left_result",
             lambda a,b:b==(a[0]+1,1) and a[1]==1 and a[0] not in (1,4),lambda a,b,x,y:(y,x)),
        Rule("first compact gutter", "stop","start", PAGE, NEXT+" and left_compact == 1 and left_row == 1", "right_result - left_result == 1",
             lambda a,b:a==(1,1) and b==(2,1),lambda a,b,x,y:(y-x,1)),
        Rule("second compact gutter", "stop","start", PAGE, NEXT+" and left_compact == 1 and left_row == 4", "right_result - left_result == 2",
             lambda a,b:a==(4,1) and b==(5,1),lambda a,b,x,y:(y-x,2)),
    ],
    "presses": [
        Rule("ordinary conservation", "fast","slow",PRESS,SAME_BATCH+" and left_rush == 0","left_result + right_result == left_total",
             lambda a,b:a==b and a[2]==0,lambda a,b,x,y:(x+y,a[0])),
        Rule("small rush conservation", "fast","slow",PRESS,SAME_BATCH+" and left_rush == 1 and left_total < 4","left_result + right_result == left_total",
             lambda a,b:a==b and a[2]==1 and a[0]<4,lambda a,b,x,y:(x+y,a[0])),
        Rule("reserved proof copy", "fast","slow",PRESS,SAME_BATCH+" and left_rush == 1 and left_total >= 4","left_result + right_result == left_total - 1",
             lambda a,b:a==b and a[2]==1 and a[0]>=4,lambda a,b,x,y:(x+y,a[0]-1)),
        Rule("minimum slow allocation", "fast","slow",PRESS,SAME_BATCH+" and left_rush == 1 and left_total >= 2","right_result >= 1",
             lambda a,b:a==b and a[2]==1 and a[0]>=2,lambda a,b,x,y:(y,1),">="),
        Rule("zero fast request", "fast","slow",PRESS,SAME_BATCH+" and left_quota == 0","left_result == 0",
             lambda a,b:a==b and a[1]==0,lambda a,b,x,y:(x,0)),
    ],
}


def check_native(rule: Rule, functions: Functions) -> dict[str, object]:
    points = list(product(*(rule.axes.values())))
    n = 0
    for a, b in product(points, repeat=2):
        if not rule.relevant(a,b):
            continue
        try:
            x, y = functions[rule.left](*a), functions[rule.right](*b)
        except Exception as error:
            return {"status":"inconclusive","reason":type(error).__name__,"checked_pairs":n}
        lhs, rhs = rule.terms(a,b,x,y)
        n += 1
        if not OPS[rule.op](lhs,rhs):
            return {"status":"violated","checked_pairs":n,
                    "witness":{"left":{"function":rule.left,"inputs":dict(zip(rule.axes,a)),"result":x},
                               "right":{"function":rule.right,"inputs":dict(zip(rule.axes,b)),"result":y}},
                    "failed_comparison":{"left_value":lhs,"operator":rule.op,"right_value":rhs}}
    return {"status":"passed" if n else "inconclusive","checked_pairs":n}
