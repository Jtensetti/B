"""Replay two isolated authors' successive edits and recount their text packets."""
import argparse
import itertools
import json
from pathlib import Path
import subprocess
import sys
from statistics import median
from time import perf_counter_ns

from b_lang.compiler import compile_b
from b_lang.revisions import check_revision

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent
sys.path.insert(0, str(FIXTURES))
import python_baseline
from surface import from_b, from_python

BRIEF = ('Adults also enter free on sponsor day (code `sponsor`). Protect seat accounting and receipt '
         'routing even if a venue has connected them to free entry. Preserve all other bookings.')
FOLLOWUP = ('The previous edit has been accepted. Same program, same one-line response format. '
            'Children also enter free on sponsor day. Keep the same protections.')
GUIDES = {
    'B': ('The language supports `also rule(literals) keeping f, g`. It makes the rule true for that '
          'tuple and rejects the change if the named functions depend on the rule.'),
    'Python': ('The environment provides `also(table, fact, *keeping)`. It inserts the tuple and '
               'rejects the change if the named functions depend on the table.'),
}
ANSWERS = {
    'B': ['also free_entry(false, "sponsor") keeping seats, recipient',
          'also free_entry(true, "sponsor") keeping seats, recipient'],
    'Python': ['also(free_entry, (False, "sponsor"), seats, recipient)',
               'also(free_entry, (True, "sponsor"), seats, recipient)'],
}


INTERFACE_REPAIRS = [
    ('also("free_entry", (False, "sponsor"), "seats", "recipient")',
     "TypeError: 'in <string>' requires string as left operand, not tuple"),
    ('also(next(table for scope in __import__("inspect").getclosurevars(free_entry)[:2] '
     'for table in scope.values() if isinstance(table, set)), (False, "sponsor"), seats, recipient)',
     "TypeError: {(True, 'sat')} is not a Python function"),
]


def trial(language, suffix, *, interface=False, typed_guide=False):
    source = (FIXTURES / f'booking.{suffix}').read_text()
    guide = GUIDES[language]
    if typed_guide:
        guide = guide.replace('also(table, fact, *keeping)', 'also(table: set, fact: tuple, *keeping: Callable)')
    heading = 'Accepted interface' if interface else 'Accepted program'
    context = (from_b(source) if language == 'B' else from_python(source)) if interface else source.rstrip()
    prompt = (f'Solve a small {language} program edit in one attempt. No tools, repository, or commentary. '
              f'Reply only with the single source line to append. {guide}\n\n'
              f'{heading}:\n{context}\n\nRequest: {BRIEF}')
    packets = {'initial_input': prompt}
    if interface and language == 'Python' and not typed_guide:
        for index, (rejected, error) in enumerate(INTERFACE_REPAIRS, 1):
            try:
                python_baseline.load(source + rejected)
            except TypeError as exc:
                assert f'TypeError: {exc}' == error
            else:
                raise AssertionError('Recorded rejected edit ran successfully')
            packets[f'rejected_{index}'] = rejected
            packets[f'feedback_{index}'] = (f'The program rejected the edit. {error}. '
                                             'Reply only with the corrected single source line.')
    packets.update(first_answer=ANSWERS[language][0], followup_input=FOLLOWUP, second_answer=ANSWERS[language][1])
    for stage, answer in enumerate(ANSWERS[language], 1):
        delta = answer + '\n'
        after = source + delta
        if language == 'B':
            assert check_revision(source, after, delta=delta)['status'] == 'proved'
            program = {}
            exec(compile_b(after).code, program)
        else:
            assert python_baseline.check(source, after, delta, []) == 'proved'
            program = python_baseline.load(after)
        for child, day, gift in itertools.product((False, True), ('sat', 'sun', 'sponsor', 'fri'), (False, True)):
            free = (day == 'sat' and child) or (day == 'sponsor' and (stage == 2 or not child))
            price = 0 if free else 100
            rule = program['free_entry']
            actual = rule(child, day) if language == 'B' else (child, day) in rule
            assert actual is free
            assert program['price'](child, day) == price
            assert program['total'](child, day, 41) == 41 + price
            assert program['seats'](child, day, 7) == 6
            assert program['recipient'](child, day, gift) == ('buyer' if gift else 'guest')
        if language == 'B':
            coupled = source.replace('available - 1', 'if free_entry(child, day) then available - 2 else available - 1')
            assert check_revision(coupled, coupled + delta, delta=delta)['status'] == 'invalid'
        else:
            coupled = source.replace('return available - 1',
                                     'return available - (2 if (child, day) in free_entry else 1)')
            assert python_baseline.check(coupled, coupled + delta, delta, []) == 'invalid'
        source = after
    return packets


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tokenizer', nargs='?', help='path to the o200k_base ESM module')
    parser.add_argument('--rounds', type=int, default=1)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    modes = [('B', 'B', 'bee', False, False), ('Python', 'Python', 'py', False, False),
             ('B interface', 'B', 'bee', True, False), ('Python interface', 'Python', 'py', True, False),
             ('Python typed guide', 'Python', 'py', True, True)]
    packets, timings = {}, {name: [] for name, *_ in modes}
    for run in range(args.rounds + 1):
        offset = run % len(modes)
        for name, language, suffix, interface, typed in modes[offset:] + modes[:offset]:
            start = perf_counter_ns()
            packets[name] = trial(language, suffix, interface=interface, typed_guide=typed)
            if run:
                timings[name].append((perf_counter_ns() - start) / 1e6)
    for name, messages in packets.items():
        if args.tokenizer:
            out = subprocess.check_output(['node', FIXTURES / 'tokenize.mjs', args.tokenizer],
                                          input=json.dumps(messages), text=True)
            counts = json.loads(out)
            print(name, counts, 'sum', sum(counts.values()))
        print(f'{name}: {median(timings[name]):.2f} ms local replay')
