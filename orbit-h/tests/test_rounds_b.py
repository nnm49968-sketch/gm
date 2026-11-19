"""Independent player-side solvers; neither receives a seed or an answer key."""
import itertools
import random
import re
import unittest

import rounds_b


def nums(text):
    return list(map(int, re.findall(r'\d+', text)))


def dial_codes(prompt, clues):
    anchor, = nums(re.search(r'ایستگاه آذر روی (\d) است', prompt)[0])
    tables = re.findall(r'لوح (\w+): ([\d، ]+)', prompt)
    assert len(tables) == 4 and all(len(nums(row)) == 6 for _, row in tables)
    links = [re.fullmatch(r'عقربهٔ (\w+) (\d) خانه جلوتر از عقربهٔ (\w+) است\.', c).groups()
             for c in clues]

    # Constraint search: try dial readings and reject inconsistent endpoints.
    def visit(readings):
        candidates = {}
        for end, offset, start in links:
            for a, b, delta in ((start, end, int(offset)), (end, start, -int(offset))):
                if a in readings:
                    target = (readings[a] + delta) % 6
                    if b in readings and readings[b] != target:
                        return
                    if b not in readings:
                        candidates[b] = [target]
        if not candidates:
            missing = ({v for end, _, start in links for v in (end, start)} |
                       {name for name, _ in tables}) - readings.keys()
            if not missing:
                yield ''.join(str(nums(row)[readings[name]]) for name, row in tables)
                return
            candidates[min(missing)] = range(6)
        name, values = next(iter(candidates.items()))
        for value in values:
            yield from visit({**readings, name: value})

    return set(visit({'آذر': anchor}))


class PacketChecks:
    def check_round(self, name, solver, pattern):
        factory = getattr(rounds_b, name)
        variation = set()
        for seed in range(32):
            with self.subTest(stage=name, seed=seed):
                packet = factory(random.Random(seed))
                self.assertEqual(packet, factory(random.Random(seed)))
                self.assertEqual(set(packet), {'title', 'prompt', 'format', 'clues', 'hint', 'answer'})
                clues = packet['clues']
                self.assertEqual(len(clues), 8)
                self.assertEqual(len(set(clues)), 8)
                self.assertIsNotNone(re.fullmatch(pattern, packet['answer']))
                variation.add(packet['answer'])
                self.assertEqual(solver(packet['prompt'], clues), {packet['answer']})
                for i in range(8):
                    with self.subTest(omitted=i):
                        self.assertGreater(len(solver(packet['prompt'], clues[:i] + clues[i+1:])), 1)
        self.assertGreater(len(variation), 1)


class DialTest(PacketChecks, unittest.TestCase):
    def test_stage3(self):
        self.check_round('stage3', dial_codes, r'[0-9]{4}')

def lamp_codes(prompt, clues):
    order = nums(prompt.split('ترتیب خواندن چراغ‌ها: ')[1])
    assert sorted(order) == list(range(1, 9))
    constraints = []
    for clue in clues:
        group, parity = re.fullmatch(r'در گروه (.*?)، تعداد چراغ‌های روشن (زوج|فرد) است\.', clue).groups()
        constraints.append((nums(group), parity == 'فرد'))
    return {''.join(str(bits[i-1]) for i in order)
            for bits in itertools.product(range(2), repeat=8)
            if all(sum(bits[i-1] for i in group) % 2 == odd for group, odd in constraints)}


class LampsTest(PacketChecks, unittest.TestCase):
    def test_stage4(self):
        self.check_round('stage4', lamp_codes, r'[01]{8}')

