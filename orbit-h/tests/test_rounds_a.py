"""Black-box solvers: enumerate submissions using only a player's text."""
import itertools
import random
import re
import unittest


def ids(text):
    return [int(x) for x in re.findall(r'\d+', text)]


def schedules(prompt, clues):
    labels = ids(prompt.split('شناسه‌های نمایش‌ها: ')[1])
    assert len(set(labels)) == len(labels) == 7
    rules = []
    for clue in clues:
        nums = ids(clue)
        if 'میان تاریخ' in clue:
            b, a, c = nums
            rules.append(lambda p, a=a, b=b, c=c: (p[a] < p[b]) == (p[b] < p[c]))
        elif 'اختلاف' in clue:
            a, b, d = nums
            rules.append(lambda p, a=a, b=b, d=d: abs(p[a] - p[b]) == d)
        elif 'زودتر' in clue:
            a, b = nums
            rules.append(lambda p, a=a, b=b: p[a] < p[b])
        else:
            raise ValueError(clue)
    for order in itertools.permutations(labels):
        positions = {label: i for i, label in enumerate(order)}
        if all(rule(positions) for rule in rules):
            yield ''.join(map(str, order))


def inventories(prompt, clues):
    labels = sorted(ids(prompt.split('شماره‌های صندوق‌ها: ')[1]))
    assert len(set(labels)) == len(labels) == 9
    reports = []
    for clue in clues:
        assert 'دقیقاً یکی' in clue
        a, b, c = ids(clue)
        assert 'پر است' in clue or 'خالی است' in clue
        reports.append(({a, b, c}, 1 if 'پر است' in clue else 2))
    for count in range(len(labels) + 1):
        for packed in itertools.combinations(labels, count):
            if all(len(group.intersection(packed)) == n for group, n in reports):
                yield ''.join(map(str, packed))


class RoundTests(unittest.TestCase):
    def test_stage2(self):
        from rounds_a import stage2
        self.check_round(stage2, inventories)

    def check_round(self, make, solve):
        seen = set()
        for seed in (0, 1, 27, 436, 8192):
            with self.subTest(seed=seed):
                packet = make(random.Random(seed))
                self.assertEqual(packet, make(random.Random(seed)))
                self.assertEqual(set(packet), {'title', 'prompt', 'format', 'hint', 'answer', 'clues'})
                self.assertRegex(packet['answer'], r'\A[0-9]+\Z')
                cards = packet['clues']
                self.assertEqual(len(cards), 8)
                self.assertEqual(len(set(cards)), 8)
                self.assertEqual(set(solve(packet['prompt'], cards)), {packet['answer']})
                for i, card in enumerate(cards):
                    answers = set(solve(packet['prompt'], cards[:i] + cards[i+1:]))
                    self.assertGreaterEqual(len(answers), 2, card)
                seen.add(packet['answer'])
        self.assertGreater(len(seen), 1)

    def test_stage1(self):
        from rounds_a import stage1
        self.check_round(stage1, schedules)


if __name__ == '__main__':
    unittest.main()
