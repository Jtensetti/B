"""Reference checker for the small, trusted, pure Python fixtures in this experiment."""

import ast
from types import FunctionType


class InvalidChange(ValueError):
    pass


def also(table, fact, *keeping):
    """Extend a data table unless a protected function reads it via a global name."""
    if fact in table:
        raise InvalidChange("The predicate already accepts this tuple")
    seen = set()

    def reads_table(function):
        if function in seen:
            return False
        seen.add(function)
        for name in function.__code__.co_names:
            obj = function.__globals__.get(name)
            if obj is table or isinstance(obj, FunctionType) and reads_table(obj):
                return True
        return False

    for function in keeping:
        if reads_table(function):
            raise InvalidChange(function.__name__)
    table.add(fact)


def load(source):
    namespace = {"also": also}
    exec(compile(source, "<fixture>", "exec"), namespace)
    return namespace


def check(base, candidate, delta, observations):
    """Structural equality proves a verdict for these fixtures; finite cases refute."""
    expected = base + delta
    try:
        actual = load(candidate)
        if ast.dump(ast.parse(expected)) == ast.dump(ast.parse(candidate)):
            return "proved"
        reference = load(expected)
    except InvalidChange:
        return "invalid"

    for name, args in observations:
        if observe(reference, name, args) != observe(actual, name, args):
            return "counterexample"
    return "unknown"


def observe(program, name, args):
    value = program[name]
    if isinstance(value, set):
        return args in value
    return value(*args)
