import unittest
from puzzles import puzzle, normalize, STAGES, deal

class HardEdition(unittest.TestCase):
    def test_eight_distinct_cards_shared_without_duplicates(self):
        self.assertEqual(STAGES,4)
        for stage in range(1,5):
            p=puzzle('TESTCREW',stage)
            self.assertEqual(len(set(p['clues'])),8)
            for n in range(1,9):
                hands=deal(p['clues'],n)
                self.assertTrue(all(hands)); self.assertEqual(sum(map(len,hands)),8)
                self.assertEqual(set(sum(hands,[])),set(p['clues']))
    def test_normalization(self):
        self.assertEqual(normalize(' ۰ ١\u200c۲ '),'012');self.assertNotEqual(normalize('01'),'1')
    def test_replay(self):
        baseline=[puzzle('crew',s) for s in range(1,5)]
        for s in reversed(range(1,5)):
            puzzle('other',s);self.assertEqual(puzzle('crew',s),baseline[s-1])
    def test_invalid_stage(self):
        for v in (0,5,True):
            with self.assertRaises(ValueError):puzzle('crew',v)
