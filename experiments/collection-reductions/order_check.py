"""Check how much order must survive when merging chunks of clock observations."""
from itertools import product
from typing import NamedTuple


class Chunk(NamedTuple):
    starts_late: bool
    ends_late: bool
    has_pair: bool


def summarize(late: tuple[bool, ...]) -> Chunk | None:
    if not late:
        return None
    return Chunk(late[0], late[-1], any(left and right for left, right in zip(late, late[1:])))


def merge(left: Chunk | None, right: Chunk | None) -> Chunk | None:
    if left is None:
        return right
    if right is None:
        return left
    crosses_cut = left.ends_late and right.starts_late
    return Chunk(left.starts_late, right.ends_late, left.has_pair or right.has_pair or crosses_cut)


def check():
    sequences = splits = groupings = 0
    for size in range(9):
        for late in product((False, True), repeat=size):
            expected = summarize(late)
            sequences += 1
            for i in range(size + 1):
                left = summarize(late[:i])
                assert merge(left, summarize(late[i:])) == expected
                splits += 1
                for j in range(i, size + 1):
                    mid, end = summarize(late[i:j]), summarize(late[j:])
                    assert merge(merge(left, mid), end) == merge(left, merge(mid, end)) == expected
                    groupings += 1
    return sequences, splits, groupings


if __name__ == "__main__":
    sequences, splits, groupings = check()
    print(f"{sequences} sequences, {splits} two-part splits, {groupings} three-part splits")
