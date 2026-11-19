"""Hard-edition packets. Stage here is 1-based; public API uses solved count."""
import random
import unicodedata

STAGES=4
_FOLD=str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩كيى','01234567890123456789کیی','\u200c\u200d\u200e\u200f\u061c\ufeff')

def normalize(text):
    return ''.join(unicodedata.normalize('NFC',text).translate(_FOLD).split()).casefold()

def deal(clues,size):
    if type(size) is not int or not 1<=size<=len(clues):
        raise ValueError('Each seat needs a distinct card')
    return [clues[i::size] for i in range(size)]

def puzzle(team_code,stage):
    if type(stage) is not int or not 1<=stage<=STAGES:
        raise ValueError('stage must be 1 through 4')
    from rounds_a import stage1,stage2
    from rounds_b import stage3,stage4
    r=random.Random(f'orbit/hard/1/{team_code}/{stage}')
    p=(stage1,stage2,stage3,stage4)[stage-1](r)
    r.shuffle(p['clues'])
    return p
