"""Fixed irreducible clue sets, relabelled and dealt by the caller's RNG."""

_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def _fa(n):
    return str(n).translate(_DIGITS)


def stage1(r):
    order = r.sample(range(1, 10), 7)
    a, b, c, d, e, f, g = map(_fa, order)

    def between(x, y, z):
        return f'تاریخ نمایش {y} میان تاریخ دو نمایش {x} و {z} است.'

    clues = [
        f'اختلاف تاریخ دو نمایش {c} و {f} دقیقاً ۳ روز است.',
        between(d, e, g), between(a, f, g),
        f'نمایش {c} زودتر از نمایش {g} اجرا شد.',
        between(d, f, g), between(c, d, f),
        f'اختلاف تاریخ دو نمایش {a} و {b} دقیقاً ۱ روز است.',
        between(a, b, f),
    ]
    r.shuffle(clues)
    return dict(title='هفت شب جشنواره',
                prompt='از دهم تا شانزدهم مهر، هر شب یک نمایش متفاوت اجرا شد. «میان» یعنی بعد از یکی و قبل از دیگری، نه لزوماً در نقطهٔ وسط.\nشناسه‌های نمایش‌ها: ' + '، '.join(map(_fa, sorted(order))),
                format='شناسه‌ها را بدون فاصله از چپ به راست بنویسید؛ رقم اول برای دهم مهر و رقم آخر برای شانزدهم مهر است.',
                clues=clues, hint='برای هر سرنخِ «میان» دو جهت ممکن را نگه دارید. کدام جهت با سرنخ «زودتر» سازگار است؟',
                answer=''.join(map(str, order)))


def stage2(r):
    boxes = r.sample(range(1, 10), 9)
    # Each triple contains exactly one of the first four slots. Swapping
    # full and empty preserves both uniqueness and the deletion witnesses.
    full = r.choice([True, False])
    status = 'پر' if full else 'خالی'
    triples = ((2, 4, 7), (2, 7, 8), (1, 6, 8), (0, 4, 5),
               (0, 4, 6), (3, 6, 8), (0, 4, 7), (1, 5, 6))
    clues = []
    for triple in triples:
        a, b, c = map(_fa, sorted(boxes[i] for i in triple))
        clues.append(f'از سه صندوق {a}، {b} و {c} دقیقاً یکی {status} است.')
    r.shuffle(clues)
    return dict(title='صورت‌برداری از انبار',
                prompt='هنگام بستن انبار، هر صندوق یا پر بود یا خالی. هر برگه نتیجهٔ بازرسی سه صندوق را در همان لحظه نشان می‌دهد. کدام صندوق‌ها پر بودند؟\nشماره‌های صندوق‌ها: ' + '، '.join(map(_fa, sorted(boxes))),
                format='فقط شمارهٔ صندوق‌های پر را بدون فاصله از چپ به راست بنویسید؛ از کوچک‌ترین شماره شروع کنید و به بزرگ‌ترین برسید.',
                clues=clues, hint='دو برگه پیدا کنید که دو صندوق مشترک دارند. وضعیت صندوق سومِ این دو برگه چه رابطه‌ای با هم دارد؟',
                answer=''.join(map(str, sorted(boxes[:4] if full else boxes[4:]))))

