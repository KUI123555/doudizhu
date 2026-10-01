"""斗地主规则：牌、牌型识别、大小比较、可出牌枚举。"""
import random
from collections import Counter

# 点数：3..10, J=11, Q=12, K=13, A=14, 2=15, 小王=16, 大王=17
RANK_NAMES = {3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9', 10: '10',
              11: 'J', 12: 'Q', 13: 'K', 14: 'A', 15: '2', 16: '小王', 17: '大王'}
SUITS = ['♠', '♥', '♣', '♦']

TYPE_NAMES = {
    'single': '单张', 'pair': '对子', 'triple': '三张', 'triple1': '三带一',
    'triple2': '三带二', 'straight': '顺子', 'dstraight': '连对', 'plane': '飞机',
    'plane1': '飞机', 'plane2': '飞机', 'four2': '四带二', 'four4': '四带两对',
    'bomb': '炸弹', 'rocket': '王炸',
}


class Card:
    __slots__ = ('id', 'rank', 'suit')

    def __init__(self, cid):
        self.id = cid
        if cid < 52:
            self.rank = cid // 4 + 3
            self.suit = cid % 4
        else:
            self.rank = 16 if cid == 52 else 17
            self.suit = -1

    @property
    def red(self):
        return self.suit in (1, 3) or self.rank == 17

    def __repr__(self):
        return RANK_NAMES[self.rank] + (SUITS[self.suit] if self.suit >= 0 else '')


def new_deck():
    deck = [Card(i) for i in range(54)]
    random.shuffle(deck)
    return deck


def sort_cards(cards):
    """从大到小排序（手牌左边大右边小）。"""
    return sorted(cards, key=lambda c: (-c.rank, c.suit))


class Pattern:
    __slots__ = ('type', 'main', 'length')

    def __init__(self, type_, main, length=1):
        self.type = type_
        self.main = main
        self.length = length

    @property
    def is_bomb(self):
        return self.type in ('bomb', 'rocket')

    @property
    def name(self):
        return TYPE_NAMES[self.type]


def _consecutive(ranks):
    ranks = sorted(ranks)
    return all(b - a == 1 for a, b in zip(ranks, ranks[1:]))


def _analyze_plane(cnt, n):
    trips = sorted(r for r, v in cnt.items() if v >= 3 and r <= 14)
    for k in range(len(trips), 1, -1):
        for i in range(len(trips) - k, -1, -1):
            seq = trips[i:i + k]
            if seq[-1] - seq[0] != k - 1:
                continue
            if n == 3 * k:
                return Pattern('plane', seq[-1], k)
            if n == 4 * k:
                return Pattern('plane1', seq[-1], k)
            if n == 5 * k:
                rest = Counter(cnt)
                for r in seq:
                    rest[r] -= 3
                if all(v % 2 == 0 for v in rest.values()):
                    return Pattern('plane2', seq[-1], k)
    return None


def analyze(cards):
    """识别牌型，不合法返回 None。"""
    ranks = [c.rank for c in cards]
    n = len(ranks)
    if n == 0:
        return None
    cnt = Counter(ranks)
    if n == 2 and set(ranks) == {16, 17}:
        return Pattern('rocket', 17)
    if len(cnt) == 1:
        r = ranks[0]
        return {1: Pattern('single', r), 2: Pattern('pair', r),
                3: Pattern('triple', r), 4: Pattern('bomb', r)}.get(n)
    vals = sorted(cnt.values())
    if n == 4 and vals == [1, 3]:
        return Pattern('triple1', max(cnt, key=cnt.get))
    if n == 5 and vals == [2, 3]:
        return Pattern('triple2', max(cnt, key=cnt.get))
    keys = list(cnt)
    if n >= 5 and all(v == 1 for v in vals) and max(keys) <= 14 and _consecutive(keys):
        return Pattern('straight', max(keys), n)
    if n >= 6 and all(v == 2 for v in vals) and max(keys) <= 14 and _consecutive(keys):
        return Pattern('dstraight', max(keys), n // 2)
    p = _analyze_plane(cnt, n)
    if p:
        return p
    fours = sorted((r for r, v in cnt.items() if v == 4), reverse=True)
    if fours:
        if n == 6:
            return Pattern('four2', fours[0])
        if n == 8:
            for f in fours:
                rest = Counter(cnt)
                rest[f] -= 4
                if all(v % 2 == 0 for v in rest.values()):
                    return Pattern('four4', f)
    return None


def can_beat(p, q):
    """牌型 p 能否压过 q（q 为 None 表示自由出牌）。"""
    if p is None:
        return False
    if q is None:
        return True
    if p.type == 'rocket':
        return True
    if q.type == 'rocket':
        return False
    if p.type == 'bomb' and q.type != 'bomb':
        return True
    if p.type != q.type or p.length != q.length:
        return False
    return p.main > q.main


def group(hand):
    g = {}
    for c in sorted(hand, key=lambda c: c.suit):
        g.setdefault(c.rank, []).append(c)
    return g


def _kickers(g, exclude, k, size):
    """挑 k 组带牌（每组 size 张），优先不拆牌、点数小。"""
    cands = [r for r in g if r not in exclude and len(g[r]) >= size]
    rocket = 16 in g and 17 in g
    cands.sort(key=lambda r: (len(g[r]) == 4 or (rocket and r >= 16), len(g[r]) != size, r))
    if len(cands) < k:
        return None
    return [c for r in cands[:k] for c in g[r][:size]]


def plays_beating(hand, t):
    """枚举手牌中所有能压过牌型 t 的出法（列表的列表）。"""
    g = group(hand)
    res = []
    typ = t.type
    if typ == 'rocket':
        return res
    rocket = 16 in g and 17 in g

    def breaks(r, size):
        return (len(g[r]) == 4 or (rocket and r >= 16), len(g[r]) != size, r)

    if typ in ('single', 'pair', 'triple'):
        size = {'single': 1, 'pair': 2, 'triple': 3}[typ]
        rs = [r for r in g if r > t.main and len(g[r]) >= size]
        rs.sort(key=lambda r: breaks(r, size))
        res += [g[r][:size] for r in rs]
    elif typ in ('triple1', 'triple2'):
        size = 1 if typ == 'triple1' else 2
        rs = sorted((r for r in g if r > t.main and len(g[r]) >= 3), key=lambda r: breaks(r, 3))
        for r in rs:
            kick = _kickers(g, {r}, 1, size)
            if kick:
                res.append(g[r][:3] + kick)
    elif typ in ('straight', 'dstraight', 'plane', 'plane1', 'plane2'):
        L = t.length
        size = {'straight': 1, 'dstraight': 2}.get(typ, 3)
        for top in range(t.main + 1, 15):
            ranks = range(top - L + 1, top + 1)
            if ranks[0] < 3 or not all(len(g.get(x, [])) >= size for x in ranks):
                continue
            base = [c for x in ranks for c in g[x][:size]]
            if typ in ('plane1', 'plane2'):
                kick = _kickers(g, set(ranks), L, 1 if typ == 'plane1' else 2)
                if not kick:
                    continue
                base += kick
            res.append(base)
    elif typ in ('four2', 'four4'):
        for r in sorted(g):
            if r > t.main and len(g[r]) == 4:
                kick = _kickers(g, {r}, 2, 1 if typ == 'four2' else 2)
                if kick:
                    res.append(g[r] + kick)
    if typ == 'bomb':
        res += [g[r][:] for r in sorted(g) if r > t.main and len(g[r]) == 4]
    else:
        res += [g[r][:] for r in sorted(g) if len(g[r]) == 4]
    if rocket:
        res.append([g[16][0], g[17][0]])
    # 过滤一遍保证合法
    return [c for c in res if can_beat(analyze(c), t)]


def remove_cards(hand, cards):
    ids = {c.id for c in cards}
    return [c for c in hand if c.id not in ids]
