"""电脑玩家：难度分发、“简单”难度的策略、玩家提示和智能选牌。"""
from collections import Counter

import ai_hard
from rules import analyze, can_beat, group, plays_beating, remove_cards

LEVELS = [('easy', '简单'), ('normal', '普通'), ('hard', '困难')]
LEVEL_TIPS = {
    'easy': '最初版本的电脑，适合熟悉规则',
    'normal': '会最优拆牌、记牌、农民之间互相配合',
    'hard': '每一步都推演几十种可能的牌局再出牌',
}


def choose_bid(level, hand, current):
    if level == 'easy':
        return ai_bid(hand, current)
    return ai_hard.hard_bid(hand, current)


def choose_play(level, hands, me, landlord, last, played, bottom):
    """电脑出牌。只用公开信息：自己的手牌、已出的牌、各家张数、亮出的底牌。"""
    if level == 'easy':
        return ai_play(hands, me, landlord, last)
    sizes = [len(h) for h in hands]
    if level == 'normal':
        return ai_hard.hard_play(hands[me], me, landlord, last, sizes, played)
    return ai_hard.search_play(hands[me], me, landlord, last, sizes, played, bottom, budget=1.0)


# ---------- 拆牌 ----------

def _runs(ranks, min_len):
    """把有序点数切成连续段，返回长度 >= min_len 的段。"""
    out, cur = [], []
    for r in ranks:
        if cur and r == cur[-1] + 1:
            cur.append(r)
        else:
            if len(cur) >= min_len:
                out.append(cur)
            cur = [r]
    if len(cur) >= min_len:
        out.append(cur)
    return out


def _decompose(cnt, use_straight):
    combos = []
    if cnt[16] and cnt[17]:
        combos.append(('rocket', [16, 17]))
        cnt[16] = cnt[17] = 0
    for r in range(3, 16):
        if cnt[r] == 4:
            combos.append(('bomb', [r] * 4))
            cnt[r] = 0
    if use_straight:
        while True:
            runs = _runs([r for r in range(3, 15) if cnt[r] >= 1], 5)
            if not runs:
                break
            run = max(runs, key=len)
            # 两端是三张的尽量不拆
            while len(run) > 5 and cnt[run[0]] >= 3:
                run = run[1:]
            while len(run) > 5 and cnt[run[-1]] >= 3:
                run = run[:-1]
            combos.append(('straight', run))
            for r in run:
                cnt[r] -= 1
    trips = [r for r in range(3, 16) if cnt[r] == 3]
    used = set()
    for run in _runs([r for r in trips if r <= 14], 2):
        combos.append(('plane', [x for r in run for x in (r, r, r)]))
        used.update(run)
        for r in run:
            cnt[r] = 0
    for r in trips:
        if r not in used:
            combos.append(('triple', [r] * 3))
            cnt[r] = 0
    for run in _runs([r for r in range(3, 15) if cnt[r] == 2], 3):
        combos.append(('dstraight', [x for r in run for x in (r, r)]))
        for r in run:
            cnt[r] = 0
    for r in range(3, 18):
        if cnt[r] == 2:
            combos.append(('pair', [r, r]))
        elif cnt[r] == 1:
            combos.append(('single', [r]))
    return combos


def combos_score(combos):
    """估算出完需要几手，越小越好。"""
    trip_like = sum(len(rs) // 3 for t, rs in combos if t in ('triple', 'plane'))
    small = sum(1 for t, rs in combos if t in ('single', 'pair') and rs[0] < 15)
    small_singles = sum(1 for t, rs in combos if t == 'single' and rs[0] < 11)
    return len(combos) - min(trip_like, small) + 0.1 * small_singles


def decompose(hand):
    cnt = Counter(c.rank for c in hand)
    best = None
    for use_straight in (True, False):
        combos = _decompose(Counter(cnt), use_straight)
        sc = combos_score(combos)
        if best is None or sc < best[0]:
            best = (sc, combos)
    return best[1]


def hand_score(hand):
    return combos_score(decompose(hand)) if hand else 0


def _to_cards(g, ranks):
    taken = Counter()
    out = []
    for r in ranks:
        out.append(g[r][taken[r]])
        taken[r] += 1
    return out


def lead_options(hand):
    """自由出牌时的候选（按“最小牌优先”排序），每项为 (最小点数, 牌列表)。"""
    combos = decompose(hand)
    g = group(hand)
    singles = sorted(rs[0] for t, rs in combos if t == 'single' and rs[0] < 15)
    pairs = sorted(rs[0] for t, rs in combos if t == 'pair' and rs[0] < 14)
    opts = []
    for t, rs in combos:
        ranks = list(rs)
        if t == 'triple' or t == 'plane':
            k = len(rs) // 3
            if len(singles) >= k:
                ranks += singles[:k]
            elif len(pairs) >= k:
                ranks += [x for p in pairs[:k] for x in (p, p)]
        opts.append((min(rs), _to_cards(g, ranks), t))
    opts.sort(key=lambda o: (o[2] in ('bomb', 'rocket'), o[0], -len(o[1])))
    return opts


# ---------- 叫分 ----------

def ai_bid(hand, current):
    cnt = Counter(c.rank for c in hand)
    s = cnt[17] * 4 + cnt[16] * 3 + cnt[15] * 2 + cnt[14] * 0.5
    s += sum(4 for r, v in cnt.items() if v == 4)
    if cnt[16] and cnt[17]:
        s += 1
    want = 3 if s >= 10 else 2 if s >= 7 else 1 if s >= 5 else 0
    return want if want > current else 0


# ---------- 出牌 ----------

def ai_play(hands, me, landlord, last):
    """返回要出的牌（列表），None 表示不出。last = (pattern, player) 或 None。"""
    hand = hands[me]
    nxt = (me + 1) % 3
    is_landlord = me == landlord
    if is_landlord:
        enemy_min = min(len(hands[p]) for p in range(3) if p != me)
    else:
        enemy_min = len(hands[landlord])

    if last is None:
        return _lead(hands, me, landlord, enemy_min)

    pat, lp = last
    cands = [c for c in plays_beating(hand, pat) if can_beat(analyze(c), pat)]
    if not cands:
        return None
    for c in cands:
        if len(c) == len(hand):
            return c
    if not is_landlord and lp != landlord:
        # 队友出的牌：一般不压
        return None

    base = hand_score(hand)
    scored = []
    for c in cands:
        pc = analyze(c)
        rest = remove_cards(hand, c)
        cost = hand_score(rest) - base
        if not pc.is_bomb:
            if pc.main >= 16 and enemy_min > 6:
                cost += 1.5
            elif pc.main == 15 and enemy_min > 8:
                cost += 0.8
        scored.append((pc.is_bomb, cost, pc.main, c, rest))
    normal = [s for s in scored if not s[0]]
    threshold = 0.5 if is_landlord else 0.2
    if enemy_min <= 5:
        threshold = 99
    # 上家是地主、下家是队友且快走完时，尽量顶一下
    if not is_landlord and len(hands[nxt]) <= 2 and nxt != landlord:
        threshold = max(threshold, 1)
    if normal:
        best = min(normal, key=lambda s: (s[1], s[2]))
        if best[1] <= threshold:
            return best[3]
    bombs = [s for s in scored if s[0]]
    if bombs:
        b = min(bombs, key=lambda s: s[2])
        if enemy_min <= 6 or hand_score(b[4]) <= 1.5:
            return b[3]
    return None


def _lead(hands, me, landlord, enemy_min):
    hand = hands[me]
    if analyze(hand):
        return hand
    nxt = (me + 1) % 3
    opts = lead_options(hand)
    # 队友只剩一张：送个最小单张
    if me != landlord and nxt != landlord and len(hands[nxt]) == 1:
        return [min(hand, key=lambda c: c.rank)]
    # 剩两手且有一手是炸弹：先炸
    if len(opts) == 2 and opts[1][2] in ('bomb', 'rocket'):
        return opts[1][1]
    normal = [o for o in opts if o[2] not in ('bomb', 'rocket')] or opts
    if enemy_min == 1:
        multi = [o for o in normal if len(o[1]) > 1]
        if multi:
            return multi[0][1]
        return [max(hand, key=lambda c: c.rank)]
    if enemy_min == 2:
        nonpair = [o for o in normal if o[2] != 'pair']
        if nonpair:
            return nonpair[0][1]
    return normal[0][1]


SEQ_TYPES = ('straight', 'dstraight', 'plane', 'plane1', 'plane2')


def smart_pick(cards, last_pattern=None):
    """划选多张牌时挑出顺子/连对/飞机；挑不出返回 None。"""
    # 跟牌且上家是连牌：挑最小的、能管上的同型牌
    if last_pattern is not None and last_pattern.type in SEQ_TYPES:
        for c in plays_beating(cards, last_pattern):
            if not analyze(c).is_bomb:
                return c
    if analyze(cards):
        return cards
    g = group(cards)
    best = None
    for size, min_len in ((1, 5), (2, 3), (3, 2)):
        ranks = [r for r in range(3, 15) if len(g.get(r, [])) >= size]
        for run in _runs(ranks, min_len):
            n = len(run) * size
            if best is None or n > best[0]:
                best = (n, [c for r in run for c in g[r][:size]])
    return best[1] if best else None


def hint_options(hand, last_pattern):
    """给玩家用的提示列表。"""
    return ai_hard.hard_hints(hand, last_pattern)
