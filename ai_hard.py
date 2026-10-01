"""困难电脑：动态规划拆牌 + 记牌（只用公开信息：自己的手牌、已出的牌、各家剩余张数）。"""
from collections import Counter

from rules import Card, analyze, can_beat, plays_beating, remove_cards

W = 7            # 每多一手牌的代价
INF = float('inf')
ALL_CARDS = [Card(i) for i in range(54)]

# ---------------- 动态规划拆牌 ----------------
# 状态：长度 15 的计数元组（下标 0..14 对应点数 3..17）
# 返回 {e: (cost, combo, e_sub, child)}，e = 可当带牌的小单/小对数 - 三张能带的数量
# 手数 = 组合数 - 小单小对数 + max(e, 0)；cost = W*手数 - 组合价值和（越小越好）

_memo = {}


def _options(c, i):
    rank = i + 3
    n = c[i]
    out = []

    def take(idxs, k):
        lst = list(c)
        for j in idxs:
            lst[j] -= k
        return tuple(lst)

    if i == 13:
        if c[14]:
            out.append((('rocket', 16, 1), take((13, 14), 1), 1, 0, 11.0))
        else:
            out.append((('single', 16, 1), take((13,), 1), 1, 0, 6.0))
        return out
    if i == 14:
        out.append((('single', 17, 1), take((14,), 1), 1, 0, 7.0))
        return out
    if n == 4:
        out.append((('bomb', rank, 1), take((i,), 4), 1, 0, 9.0 + (rank - 3) * 0.1))
        return out
    small = i <= 11
    v = rank - 10.0
    out.append((('single', rank, 1), take((i,), 1), 0 if small else 1, 1 if small else 0, v))
    if n >= 2:
        out.append((('pair', rank, 1), take((i,), 2), 0 if small else 1, 1 if small else 0, 2 * v))
    if n >= 3:
        out.append((('triple', rank, 1), take((i,), 3), 1, -1, v))
    if i <= 11:
        for size, min_len, typ, bonus in ((1, 5, 'straight', 1.0), (2, 3, 'dstraight', 1.0), (3, 2, 'plane', 2.0)):
            j = i
            while j <= 11 and size <= c[j] < 4:
                j += 1
                L = j - i
                if L >= min_len:
                    top = i + L - 1 + 3
                    de = -L if typ == 'plane' else 0
                    out.append(((typ, top, L), take(range(i, j), size), 1, de, top - 10.0 + bonus))
    return out


def _solve(c):
    res = _memo.get(c)
    if res is not None:
        return res
    i = next((k for k in range(15) if c[k]), None)
    if i is None:
        res = {0: (0.0, None, 0, None)}
    else:
        raw = {}
        for combo, child, turns, de, val in _options(c, i):
            add = W * turns - val
            for e, ent in _solve(child).items():
                k = e + de
                v = ent[0] + add
                cur = raw.get(k)
                if cur is None or v < cur[0]:
                    raw[k] = (v, combo, e, child)
        res, best = {}, INF
        for k in sorted(raw):           # e 越大越差：只保留帕累托前沿
            if raw[k][0] < best:
                res[k] = raw[k]
                best = raw[k][0]
    if len(_memo) > 300000:
        _memo.clear()
    _memo[c] = res
    return res


def counts_of(cards):
    c = [0] * 15
    for x in cards:
        c[x.rank - 3] += 1
    return tuple(c)


def evaluate(cards):
    """手牌评分（越小越好）。"""
    if not cards:
        return -100.0
    res = _solve(counts_of(cards))
    return min(v[0] + W * max(e, 0) for e, v in res.items())


def decompose(cards):
    """最优拆牌，返回 [(type, main, length)]。"""
    c = counts_of(cards)
    res = _solve(c)
    e = min(res, key=lambda k: res[k][0] + W * max(k, 0))
    combos = []
    while True:
        ent = _solve(c)[e]
        if ent[1] is None:
            return combos
        combos.append(ent[1])
        c, e = ent[3], ent[2]


def combo_ranks(combo):
    typ, main, L = combo
    if typ == 'rocket':
        return [16, 17]
    size = {'single': 1, 'pair': 2, 'triple': 3, 'bomb': 4}.get(typ)
    if size:
        return [main] * size
    size = {'straight': 1, 'dstraight': 2, 'plane': 3}[typ]
    return [r for r in range(main - L + 1, main + 1) for _ in range(size)]


def plays_from_hand(cards):
    """把最优拆牌变成具体出法（三张/飞机带上最小的单或对），按价值从小到大排序。"""
    combos = decompose(cards)
    singles = sorted(m for t, m, _ in combos if t == 'single' and m <= 14)
    pairs = sorted(m for t, m, _ in combos if t == 'pair' and m <= 14)
    plays = []
    for t, m, L in sorted(combos, key=lambda x: x[1]):
        if t in ('single', 'pair') and m <= 14:
            continue
        ranks = combo_ranks((t, m, L))
        if t in ('triple', 'plane'):
            free_s = [r for r in singles if r not in ranks]
            free_p = [r for r in pairs if r not in ranks]
            if len(free_s) >= L:
                for r in free_s[:L]:
                    singles.remove(r)
                ranks = ranks + free_s[:L]
            elif len(free_p) >= L:
                for r in free_p[:L]:
                    pairs.remove(r)
                ranks = ranks + [r for r in free_p[:L] for _ in range(2)]
        plays.append(ranks)
    plays += [[r] for r in singles]
    plays += [[r, r] for r in pairs]
    out = []
    for ranks in plays:
        cs = _pick(cards, ranks)
        out.append((analyze(cs), cs))
    out.sort(key=lambda x: (_play_value(x[0]), -len(x[1])))
    return out


def _pick(cards, ranks):
    pool = {}
    for c in sorted(cards, key=lambda c: c.suit):
        pool.setdefault(c.rank, []).append(c)
    need = Counter(ranks)
    return [c for r, k in need.items() for c in pool[r][:k]]


def _play_value(p):
    if p.type == 'rocket':
        return 30
    if p.type == 'bomb':
        return 20 + p.main / 100
    return p.main - 10 + (1 if p.length > 1 or p.type in ('straight', 'dstraight') else 0)


# ---------------- 局面信息 ----------------

class Ctx:
    def __init__(self, hand, me, landlord, last, sizes, played):
        self.hand = hand
        self.me = me
        self.L = landlord
        self.last = last
        self.sizes = sizes
        self.nxt = (me + 1) % 3
        if me == landlord:
            self.enemies = [p for p in range(3) if p != me]
            self.mate = None
        else:
            self.enemies = [landlord]
            self.mate = 3 - me - landlord
        known = {c.id for c in hand} | {c.id for c in played}
        self.pool = [c for c in ALL_CARDS if c.id not in known]   # 别人手里的牌（合在一起）
        self.enemy_min = min(sizes[p] for p in self.enemies)
        self.enemy_max = max(sizes[p] for p in self.enemies)
        self._boss = {}

    def is_boss(self, pat):
        """除炸弹外，对手没有牌能管上。"""
        if pat.type == 'rocket':
            return True
        key = (pat.type, pat.main, pat.length)
        if key not in self._boss:
            n = {'single': 1, 'pair': 2, 'triple': 3, 'triple1': 4, 'triple2': 5, 'bomb': 4,
                 'four2': 6, 'four4': 8}.get(pat.type)
            if n is None:
                n = pat.length * {'straight': 1, 'dstraight': 2, 'plane': 3, 'plane1': 4, 'plane2': 5}[pat.type]
            if n > self.enemy_max and not pat.is_bomb:
                self._boss[key] = True
            else:
                beats = [b for b in plays_beating(self.pool, pat)
                         if (pat.is_bomb or not analyze(b).is_bomb) and len(b) <= self.enemy_max]
                self._boss[key] = not beats
        return self._boss[key]

    def loose_count(self, cards):
        """拆牌后不是“最大”的牌有几手。"""
        if not cards:
            return 0
        return sum(1 for p, _ in plays_from_hand(cards) if not self.is_boss(p))


def _winning_line(ctx, plays):
    """如果除一手外都是最大牌，返回下一步该出的牌。"""
    loose = [x for x in plays if not ctx.is_boss(x[0])]
    if len(loose) > 1:
        return None
    boss = [x for x in plays if ctx.is_boss(x[0])]
    normal_boss = [x for x in boss if not x[0].is_bomb]
    if normal_boss:
        return normal_boss[0][1]
    if loose:
        # 剩一手普通牌 + 若干炸弹：先出普通牌（被管再炸）
        return loose[0][1]
    return boss[0][1] if boss else None


# ---------------- 出牌 ----------------

def hard_play(hand, me, landlord, last, sizes, played):
    ctx = Ctx(hand, me, landlord, last, sizes, played)
    if last is None:
        return _lead(ctx)
    return _follow(ctx)


def _lead(ctx):
    hand = ctx.hand
    if analyze(hand):
        return hand
    plays = plays_from_hand(hand)
    line = _winning_line(ctx, plays)
    if line:
        return line
    # 队友（下家）快走完了：送牌
    if ctx.mate is not None and ctx.nxt == ctx.mate:
        if ctx.sizes[ctx.mate] == 1:
            return [min(hand, key=lambda c: c.rank)]
    normal = [x for x in plays if not x[0].is_bomb] or plays
    if ctx.enemy_min == 1:
        multi = [x for x in normal if len(x[1]) > 1]
        if multi:
            return multi[0][1]
        boss = [x for x in normal if ctx.is_boss(x[0])]
        if boss:
            return boss[0][1]
        return [max(hand, key=lambda c: c.rank)]
    if ctx.enemy_min == 2:
        safe = [x for x in normal if x[0].type != 'pair' or ctx.is_boss(x[0])]
        if safe:
            normal = safe
    # 队友在下家且牌少：出小对/小单方便他接
    if ctx.mate is not None and ctx.nxt == ctx.mate and ctx.sizes[ctx.mate] == 2:
        g = Counter(c.rank for c in hand)
        pr = [r for r, k in g.items() if k >= 2 and r < 14]
        if pr:
            r = min(pr)
            return [c for c in hand if c.rank == r][:2]
    # 默认：先出价值最低的非最大牌，最大的牌留着收尾
    loose = [x for x in normal if not ctx.is_boss(x[0])] or normal
    return loose[0][1]


def _follow(ctx):
    hand = ctx.hand
    pat, lp = ctx.last
    cands = plays_beating(hand, pat)
    if not cands:
        return None
    for c in cands:
        if len(c) == len(hand):
            return c
    base = evaluate(hand)
    scored = []
    for c in cands:
        p = analyze(c)
        rest = remove_cards(hand, c)
        gain = base - evaluate(rest)
        boss = ctx.is_boss(p)
        win = boss and ctx.loose_count(rest) <= 1
        scored.append((c, p, gain, boss, win))

    # 能直接打出必胜局面
    wins = [s for s in scored if s[4]]
    if wins:
        return min(wins, key=lambda s: (s[1].is_bomb, -s[2]))[0]

    normal = [s for s in scored if not s[1].is_bomb]
    bombs = [s for s in scored if s[1].is_bomb]

    if ctx.mate is not None and lp == ctx.mate:
        # 队友出的牌：一般让他走
        if ctx.sizes[ctx.mate] <= 3 or ctx.is_boss(pat) or pat.main >= 13:
            return None
        if ctx.nxt == ctx.L and normal:
            # 地主在下家，顶一手不伤牌型的
            best = max(normal, key=lambda s: (s[2], -s[1].main))
            if best[2] >= W - 1 and best[1].main <= 14:
                return best[0]
        return None

    danger = ctx.sizes[lp] <= 2 or ctx.enemy_min <= 2
    if normal:
        best = max(normal, key=lambda s: (s[2], -s[1].main))
        c, p, gain, boss, _ = best
        uses_control = p.main >= 15
        thr = 1.0
        if uses_control and ctx.enemy_min > 8:
            thr = 3.0
        if ctx.enemy_min <= 5:
            thr = -4.0
        if danger:
            # 对手要走了：尽量用能压死的牌
            bosses = [s for s in normal if s[3]]
            if bosses:
                return max(bosses, key=lambda s: s[2])[0]
            return best[0]
        if gain >= thr:
            return c
    if bombs:
        b = max(bombs, key=lambda s: (s[2], -s[1].main))
        if danger or ctx.enemy_min <= 4 or ctx.loose_count(remove_cards(hand, b[0])) <= 2:
            return b[0]
    return None


# ---------------- 搜索（蒙特卡洛） ----------------
# 把看不见的牌按各家张数随机分配若干次（底牌没出的一定在地主手里），
# 每个候选出法都在这些“可能的牌局”里用上面的策略打到底，选赢得最多的。

def _rollout(hands, turn, L, last, played):
    sizes = [len(h) for h in hands]
    while True:
        if last is not None and last[1] == turn:
            last = None
        c = hard_play(hands[turn], turn, L, last, sizes, played)
        if c:
            hands[turn] = remove_cards(hands[turn], c)
            sizes[turn] -= len(c)
            played = played + c
            if not hands[turn]:
                return turn
            last = (analyze(c), turn)
        turn = (turn + 1) % 3


def _candidates(ctx, heuristic):
    """挑几个值得搜索的出法（None 表示不出）。"""
    hand = ctx.hand
    if ctx.last is None:
        cands = [cs for _, cs in plays_from_hand(hand)][:7]
    else:
        beats = plays_beating(hand, ctx.last[0])
        if not beats:
            return []
        base = evaluate(hand)
        normal = [b for b in beats if not analyze(b).is_bomb]
        normal.sort(key=lambda b: base - evaluate(remove_cards(hand, b)), reverse=True)
        bombs = [b for b in beats if analyze(b).is_bomb]
        cands = normal[:5] + bombs[:1] + [None]
    key = lambda cs: None if cs is None else frozenset(c.id for c in cs)
    if key(heuristic) not in {key(c) for c in cands}:
        cands.insert(0, heuristic)
    return cands


def search_play(hand, me, landlord, last, sizes, played, bottom=(), budget=0.8, max_worlds=60,
                min_worlds=8, rng=None):
    import random
    import time
    rng = rng or random
    heuristic = hard_play(hand, me, landlord, last, sizes, played)
    ctx = Ctx(hand, me, landlord, last, sizes, played)
    cands = _candidates(ctx, heuristic)
    if len(cands) <= 1:
        return heuristic
    if heuristic and len(heuristic) == len(hand):
        return heuristic
    played_ids = {c.id for c in played}
    others = [p for p in range(3) if p != me]
    forced = [c for c in bottom if c.id not in played_ids] if me != landlord else []
    forced_ids = {c.id for c in forced}
    free = [c for c in ctx.pool if c.id not in forced_ids]
    wins = [0] * len(cands)
    t_end = time.perf_counter() + budget
    worlds = 0
    while worlds < max_worlds and (worlds < min_worlds or time.perf_counter() < t_end):
        rng.shuffle(free)
        world = [None, None, None]
        world[me] = list(hand)
        rest = list(free)
        for p in others:
            need = sizes[p]
            got = list(forced) if p == landlord else []
            take = need - len(got)
            world[p] = got + rest[:take]
            rest = rest[take:]
        for k, cs in enumerate(cands):
            hands = [list(h) for h in world]
            nplayed = list(played)
            if cs:
                hands[me] = remove_cards(hands[me], cs)
                if not hands[me]:
                    wins[k] += 1
                    continue
                nplayed += cs
                nlast = (analyze(cs), me)
            else:
                nlast = last
            winner = _rollout(hands, (me + 1) % 3, landlord, nlast, nplayed)
            if (winner == landlord) == (me == landlord):
                wins[k] += 1
        worlds += 1
    hkey = None if heuristic is None else frozenset(c.id for c in heuristic)
    ckeys = [None if cs is None else frozenset(c.id for c in cs) for cs in cands]
    best = max(range(len(cands)), key=lambda k: (wins[k], ckeys[k] == hkey))
    return cands[best]


# ---------------- 叫分 ----------------

def hard_bid(hand, current):
    cnt = Counter(c.rank for c in hand)
    control = cnt[17] * 3 + cnt[16] * 2.5 + cnt[15] * 1.5 + cnt[14] * 0.5
    bombs = sum(1 for r, v in cnt.items() if v == 4) + (1 if cnt[16] and cnt[17] else 0)
    control += bombs * 3
    turns = len(decompose(hand))
    s = control - 0.6 * turns
    # 阈值来自 2 万局自我对战：s≈-0.5 时地主胜率约 52%，s≈1 约 60%，s≈2.5 约 68%
    want = 3 if s >= 2.5 else 2 if s >= 1 else 1 if s >= -0.5 else 0
    return want if want > current else 0


def hard_hints(hand, last_pattern):
    if last_pattern is None:
        return [cs for _, cs in plays_from_hand(hand)]
    return plays_beating(hand, last_pattern)
