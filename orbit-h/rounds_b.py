"""Two eight-card rounds. Only the supplied random stream is consumed."""
from random import Random


__all__ = ['stage3', 'stage4']


def _series(values):
    return '، '.join(map(str, values))


def stage3(r: Random):
    """Recover relative dial readings along a tree, then decode its leaves."""
    names = ['باد', 'مهر', 'ابر', 'ماه', 'موج', 'نور', 'رعد', 'برف']
    r.shuffle(names)
    names.insert(0, 'آذر')
    readings = [r.randrange(6)]
    clues = []
    # Every edge separates at least one output dial from the reference.
    for child, parent in enumerate((0, 1, 1, 2, 2, 3, 6, 6), 1):
        readings.append((readings[parent] + r.randint(1, 5)) % 6)
        a, b = (parent, child) if r.randrange(2) else (child, parent)
        gap = (readings[a] - readings[b]) % 6
        clues.append(f'عقربهٔ {names[a]} {gap} خانه جلوتر از عقربهٔ {names[b]} است.')
    r.shuffle(clues)

    leaves = [4, 5, 7, 8]
    r.shuffle(leaves)
    rows, digits = [], []
    for leaf in leaves:
        row = r.sample(range(10), 6)  # Changing this dial must change its digit.
        rows.append(f'لوح {names[leaf]}: {_series(row)}')
        digits.append(str(row[readings[leaf]]))
    return dict(
        title='قفل چهار لوح',
        prompt=('صفحهٔ هر ایستگاه شش خانه دارد. در جهت جلو، خانه‌ها از ۰ تا ۵ شماره دارند و بعد از ۵ دوباره به ۰ می‌رسند. '
                f'عقربهٔ ایستگاه آذر روی {readings[0]} است. با کمک گزارش‌ها جای عقربه‌های چهار ایستگاه دارای لوح را پیدا کنید. '
                'روی هر لوح، رقم‌های مربوط به خانه‌های صفر تا پنج به ترتیب نوشته شده‌اند؛ مثلاً خانهٔ صفر یعنی اولین رقم بعد از نام لوح. رمز قفل چیست؟\n'
                + '\n'.join(rows)),
        format='چهار رقم بدون فاصله بنویسید. از چپ به راست، رقم لوح سطر اول تا سطر چهارم را وارد کنید؛ صفر اول را نگه دارید.',
        clues=clues,
        hint='از آذر شروع کنید. هر بار گزارشی پیدا کنید که جای یکی از دو عقربه‌اش معلوم است. اگر عقربهٔ جلوتر معلوم باشد، برای یافتن دیگری عقب بشمارید.',
        answer=''.join(digits),
    )


def stage4(r: Random):
    """Recover a lamp panel by comparing overlapping parity reports."""
    labels = r.sample(range(1, 9), 8)
    lit = {label: r.randrange(2) for label in labels}
    # ab vs abc reveals c. Propagate through d..h; agh then fixes a and ab fixes b.
    groups = [(0, 1), (0, 1, 2), (2, 3), (2, 3, 4),
              (4, 5), (4, 5, 6), (6, 7), (0, 6, 7)]
    clues = []
    for indices in groups:
        group = sorted(labels[i] for i in indices)
        parity = 'فرد' if sum(lit[i] for i in group) % 2 else 'زوج'
        clues.append(f'در گروه {_series(group)}، تعداد چراغ‌های روشن {parity} است.')
    r.shuffle(clues)
    order = r.sample(labels, len(labels))
    return dict(
        title='بازخوانی تابلو در خاموشی',
        prompt=('هشت چراغ شماره‌دار داریم. گزارش‌ها همه از یک لحظه‌اند. هر حسگر فقط می‌گوید تعداد چراغ‌های روشن در گروه خودش زوج است یا فرد؛ '
                'صفر هم زوج است. چراغی که در چند گزارش آمده، در همهٔ آن‌ها همان وضعیت را دارد. کدام چراغ‌ها روشن بوده‌اند؟\n'
                'ترتیب خواندن چراغ‌ها: ' + _series(order)),
        format='هشت رقم بدون فاصله بنویسید: روشن را ۱ و خاموش را ۰ بگذارید. از چپ به راست با اولین شمارهٔ فهرست شروع کنید و صفرهای اول را حذف نکنید.',
        clues=clues,
        hint='دو گروه پیدا کنید که یکی فقط یک چراغ بیشتر از دیگری دارد. اگر با اضافه شدن آن چراغ تعداد روشن‌ها از زوج به فرد یا از فرد به زوج تبدیل شده، آن چراغ چه وضعیتی دارد؟',
        answer=''.join(str(lit[i]) for i in order),
    )
