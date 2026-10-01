"""斗地主 —— 牌桌：发牌、叫分、出牌、结算及其绘制。"""
import math
import random
import threading
import traceback
from collections import Counter

import pygame

from ai import LEVELS, ai_play, choose_bid, choose_play, hint_options, smart_pick
from rules import (RANK_NAMES, SUITS, analyze, can_beat, new_deck, remove_cards,
                   sort_cards)
from sounds import Sounds

W, H = 1280, 760
BIG = (90, 126)
SMALL = (64, 90)
FPS = 60

AVATAR = {0: (70, H - 130), 1: (W - 75, 215), 2: (75, 215)}
STACK_X = {1: W - 204, 2: 140}
STACK_Y = 150
DECK_POS = (W // 2 - 32, 230)
NAMES = ['我', '电脑甲', '电脑乙']
AVATAR_CHAR = ['我', '甲', '乙']
AVATAR_COLOR = [(70, 130, 210), (210, 110, 60), (140, 90, 200)]

FONT_FILE = 'C:/Windows/Fonts/msyh.ttc'
FONT_BOLD_FILE = 'C:/Windows/Fonts/msyhbd.ttc'
SYMBOL_FILE = 'C:/Windows/Fonts/seguisym.ttf'

_fonts = {}


def F(size, bold=False):
    key = ('t', size, bold)
    if key not in _fonts:
        try:
            _fonts[key] = pygame.font.Font(FONT_BOLD_FILE if bold else FONT_FILE, size)
        except Exception:
            _fonts[key] = pygame.font.SysFont('microsoftyahei,simhei,arial', size, bold=bold)
    return _fonts[key]


def SF(size):
    key = ('s', size)
    if key not in _fonts:
        try:
            _fonts[key] = pygame.font.Font(SYMBOL_FILE, size)
        except Exception:
            _fonts[key] = F(size)
    return _fonts[key]


# 游戏时钟：只在没打开菜单时前进，暂停时动画和电脑思考都会停住
_clock = [0.0]


def now():
    return _clock[0]


def advance_clock(dt):
    _clock[0] += dt


# 画面缩放（窗口大小和 1280x760 不同时），用来把鼠标坐标换算回游戏坐标
VIEW = {'scale': 1.0, 'ox': 0, 'oy': 0}


def to_logical(pos):
    return ((pos[0] - VIEW['ox']) / VIEW['scale'], (pos[1] - VIEW['oy']) / VIEW['scale'])


def mouse_pos():
    return to_logical(pygame.mouse.get_pos())


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def lerp(a, b, k):
    return a + (b - a) * k


def lerp_color(a, b, k):
    return tuple(int(lerp(x, y, k)) for x, y in zip(a, b))


def blit_center(surf, img, center):
    surf.blit(img, img.get_rect(center=(int(center[0]), int(center[1]))))


def text_outline(text, font, color, outline=(30, 20, 10), w=2):
    base = font.render(text, True, color)
    out = font.render(text, True, outline)
    surf = pygame.Surface((base.get_width() + 2 * w, base.get_height() + 2 * w), pygame.SRCALPHA)
    for dx in (-w, 0, w):
        for dy in (-w, 0, w):
            if dx or dy:
                surf.blit(out, (dx + w, dy + w))
    surf.blit(base, (w, w))
    return surf


# ---------------- 绘制牌面 ----------------

def render_face(card, w, h):
    s = w / 90
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    r = int(8 * s)
    pygame.draw.rect(surf, (252, 251, 246), (0, 0, w, h), border_radius=r)
    pygame.draw.rect(surf, (140, 140, 140), (0, 0, w, h), 1, border_radius=r)
    color = (205, 30, 40) if card.red else (25, 25, 30)
    if card.rank >= 16:
        f = F(max(8, int(15 * s)), True)
        for i, ch in enumerate('JOKER'):
            img = f.render(ch, True, color)
            blit_center(surf, img, (14 * s, 13 * s + i * 15 * s))
        star = SF(int(50 * s)).render('★', True, color)
        blit_center(surf, star, (w * 0.62, h * 0.55))
        lab = F(max(8, int(13 * s)), True).render('大王' if card.rank == 17 else '小王', True, color)
        surf.blit(lab, (w - lab.get_width() - 6 * s, h - lab.get_height() - 4 * s))
    else:
        name = RANK_NAMES[card.rank]
        f = F(int((22 if name == '10' else 27) * s), True)
        img = f.render(name, True, color)
        if name == '10':
            img = pygame.transform.smoothscale(img, (int(img.get_width() * 0.8), img.get_height()))
        blit_center(surf, img, (16 * s, 18 * s))
        suit = SF(int(20 * s)).render(SUITS[card.suit], True, color)
        blit_center(surf, suit, (16 * s, 42 * s))
        big = SF(int(50 * s)).render(SUITS[card.suit], True, color)
        blit_center(surf, big, (w * 0.62, h * 0.66))
    return surf


def render_back(w, h):
    s = w / 90
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    r = int(8 * s)
    pygame.draw.rect(surf, (250, 250, 250), (0, 0, w, h), border_radius=r)
    inner = pygame.Rect(int(5 * s), int(5 * s), w - int(10 * s), h - int(10 * s))
    pat = pygame.Surface(inner.size, pygame.SRCALPHA)
    pat.fill((40, 85, 165))
    step = max(6, int(10 * s))
    for i in range(-inner.h, inner.w, step):
        pygame.draw.line(pat, (60, 110, 195), (i, 0), (i + inner.h, inner.h), 2)
        pygame.draw.line(pat, (60, 110, 195), (i + inner.h, 0), (i, inner.h), 2)
    mask = pygame.Surface(inner.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255), (0, 0, *inner.size), border_radius=int(6 * s))
    pat.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(pat, inner)
    pygame.draw.circle(surf, (230, 180, 60), (w // 2, h // 2), int(17 * s))
    pygame.draw.circle(surf, (170, 30, 30), (w // 2, h // 2), int(15 * s))
    blit_center(surf, F(int(18 * s), True).render('斗', True, (255, 230, 150)), (w / 2, h / 2))
    pygame.draw.rect(surf, (140, 140, 140), (0, 0, w, h), 1, border_radius=r)
    return surf


def render_shadow(w, h):
    s = w / 90
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, (0, 0, 0, 70), (0, 0, w, h), border_radius=int(8 * s))
    return surf


def make_background():
    bg = pygame.Surface((W, H))
    outer, inner = (10, 58, 34), (34, 125, 72)
    bg.fill(outer)
    steps = 50
    for i in range(steps):
        k = i / (steps - 1)
        rw, rh = W * 1.4 * (1 - k * 0.8), H * 1.5 * (1 - k * 0.8)
        pygame.draw.ellipse(bg, lerp_color(outer, inner, k), (W / 2 - rw / 2, H / 2 - 40 - rh / 2, rw, rh))
    mark = F(110, True).render('斗 地 主', True, (255, 255, 255))
    mark.set_alpha(14)
    blit_center(bg, mark, (W / 2, 300))
    return bg


# ---------------- 按钮 ----------------

class Button:
    def __init__(self, text, center, color, w=124, h=48):
        self.text = text
        self.rect = pygame.Rect(0, 0, w, h)
        self.rect.center = center
        self.color = color
        self.enabled = True

    def draw(self, surf, mouse):
        hover = self.enabled and self.rect.collidepoint(mouse)
        col = self.color if self.enabled else (120, 120, 120)
        if hover:
            col = lerp_color(col, (255, 255, 255), 0.18)
        sh = self.rect.move(0, 4)
        pygame.draw.rect(surf, lerp_color(col, (0, 0, 0), 0.45), sh, border_radius=12)
        pygame.draw.rect(surf, col, self.rect, border_radius=12)
        hi = pygame.Rect(self.rect.x + 4, self.rect.y + 3, self.rect.w - 8, self.rect.h // 2 - 3)
        pygame.draw.rect(surf, lerp_color(col, (255, 255, 255), 0.25), hi, border_radius=10)
        blit_center(surf, text_outline(self.text, F(21, True), (255, 255, 255),
                                       lerp_color(col, (0, 0, 0), 0.5), 1), self.rect.center)

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


# ---------------- 游戏 ----------------

class Game:
    def __init__(self):
        self.canvas = pygame.Surface((W, H))
        self.snd = Sounds()
        self.bg = make_background()
        self.back = {BIG: render_back(*BIG), SMALL: render_back(*SMALL)}
        self.shadow = {BIG: render_shadow(*BIG), SMALL: render_shadow(*SMALL)}
        self.faces = {}
        self.scores = [0, 0, 0]
        self.toasts, self.particles, self.flyers = [], [], []
        self.shake_t0 = self.flash_t0 = -10
        y = 535
        self.bid_btns = [Button(t, (W // 2 - 225 + i * 150, y), c) for i, (t, c) in enumerate(
            [('不叫', (110, 120, 130)), ('1分', (230, 140, 30)), ('2分', (230, 110, 30)), ('3分', (220, 70, 40))])]
        self.btn_pass = Button('不出', (W // 2 - 160, y), (110, 120, 130))
        self.btn_hint = Button('提示', (W // 2, y), (50, 130, 210))
        self.btn_play = Button('出牌', (W // 2 + 160, y), (230, 120, 30))
        self.btn_again = Button('再来一局', (W // 2, H // 2 + 125), (230, 120, 30), w=170, h=52)
        self.dragging = False
        self.drag_start = self.drag_cur = self.drag_hand_len = 0
        self.level = 'normal'
        self.ai_token = 0
        self.ai_result = None
        self.new_round()

    # ---------- 资源 ----------
    def face(self, card, size):
        key = (card.id, size)
        if key not in self.faces:
            self.faces[key] = render_face(card, *size)
        return self.faces[key]

    def draw_card(self, surf, card, pos, size, back=False):
        surf.blit(self.shadow[size], (pos[0] + 2, pos[1] + 3))
        surf.blit(self.back[size] if back else self.face(card, size), pos)

    # ---------- 回合 ----------
    def new_round(self):
        deck = new_deck()
        self.hands = [[], [], []]
        self.bottom = deck[51:]
        self.deal_queue = [(i % 3, deck[i]) for i in range(51)]
        self.state = 'dealing'
        self.next_deal = now() + 0.4
        self.landlord = None
        self.bid = 0
        self.bidder = None
        self.bid_count = 0
        self.bid_turn = random.randrange(3)
        self.turn = None
        self.display = [None, None, None]
        self.last = None
        self.passes = 0
        self.multiplier = 1
        self.play_count = [0, 0, 0]
        self.played = []
        self.ai_token += 1          # 作废还在算的旧结果
        self.ai_result = None
        self.dragging = False
        self.selected = set()
        self.raise_off = {}
        self.hints, self.hint_idx = [], 0
        self.reveal_t0 = None
        self.bottom_given = False
        self.result = None
        self.next_ai = 0
        self.new_ids, self.new_ids_until = set(), 0
        self.flyers = []

    def deal_target(self, p):
        if p == 0:
            return (W // 2 - BIG[0] // 2, H - BIG[1] - 28)
        return (STACK_X[p], STACK_Y + len(self.hands[p]) * 16)

    def receive(self, p, card):
        self.hands[p].append(card)
        self.hands[p] = sort_cards(self.hands[p])

    def start_bid_turn(self):
        self.display[self.bid_turn] = None
        if self.bid_turn != 0:
            self.next_ai = now() + random.uniform(0.8, 1.3)

    def do_bid(self, p, v):
        self.display[p] = {'kind': 'text', 'text': '不叫' if v == 0 else f'{v}分', 't0': now()}
        self.snd.play('bid' if v else 'pass')
        if v > self.bid:
            self.bid, self.bidder = v, p
        self.bid_count += 1
        if v == 3 or self.bid_count == 3:
            if self.bid == 0:
                self.toast('都不叫，重新发牌', (W / 2, 320), 1.8, size=40)
                self.state = 'redeal'
                self.redeal_t = now() + 1.8
            else:
                self.landlord = self.bidder
                self.state = 'reveal'
                self.reveal_t0 = now()
                self.toast(f'{NAMES[self.landlord]} 当地主！' if self.landlord else '你当地主！',
                           (W / 2, 320), 1.6, color=(255, 215, 80), size=44)
        else:
            self.bid_turn = (p + 1) % 3
            self.start_bid_turn()

    def give_bottom(self):
        self.bottom_given = True
        L = self.landlord
        t = now()
        for i, c in enumerate(self.bottom):
            self.flyers.append({'surf': self.face(c, SMALL) if L == 0 else self.back[SMALL],
                                'src': self.bottom_pos(i), 'dst': self.deal_target(L) if L == 0 else
                                (STACK_X[L], STACK_Y + (len(self.hands[L]) + i) * 16),
                                't0': t + i * 0.06, 'dur': 0.35,
                                'done': (lambda c=c: self.receive(L, c))})
        if L == 0:
            self.new_ids = {c.id for c in self.bottom}
            self.new_ids_until = t + 3.0
        self.snd.play('deal')

    def start_playing(self):
        self.state = 'playing'
        self.display = [None, None, None]
        self.turn = self.landlord
        self.begin_turn()

    def begin_turn(self):
        p = self.turn
        self.display[p] = None
        if p == 0:
            self.hints = hint_options(self.hands[0], self.last[0] if self.last else None)
            self.hint_idx = 0
            if self.last and not self.hints:
                self.toast('没有牌能大过上家', (W / 2, 470), 1.6, size=26, pop=False)
        else:
            self.next_ai = now() + random.uniform(0.8, 1.4)
            self.start_ai_thinking(p)

    def start_ai_thinking(self, p):
        """在后台线程里算电脑的出牌，画面不会卡住。"""
        self.ai_token += 1
        token = self.ai_token
        self.ai_result = None
        hands = [list(h) for h in self.hands]
        args = (self.level, hands, p, self.landlord, self.last, list(self.played), list(self.bottom))

        def work():
            try:
                cards = choose_play(*args)
            except Exception:
                traceback.print_exc()
                cards = ai_play(hands, p, self.landlord, args[4])
            self.ai_result = (token, cards)

        threading.Thread(target=work, daemon=True).start()

    def take_ai_result(self, p):
        """取后台算好的出牌；还没算完返回 False。"""
        res = self.ai_result
        if not res or res[0] != self.ai_token:
            return False
        self.ai_result = None
        cards = res[1]
        pat = self.last[0] if self.last else None
        if cards and not can_beat(analyze(cards), pat):
            cards = ai_play(self.hands, p, self.landlord, self.last)
        if not cards and self.last is None:
            cards = [self.hands[p][-1]]
        if cards:
            self.do_play(p, cards)
        else:
            self.do_pass(p)
        return True

    def display_layout(self, p, n):
        sp = 28
        total = (n - 1) * sp + SMALL[0]
        if p == 0:
            x0, y = W / 2 - total / 2, 385
        elif p == 2:
            x0, y = 235, 200
        else:
            x0, y = W - 235 - total, 200
        return [(x0 + i * sp, y) for i in range(n)]

    def display_center(self, p):
        return {0: (W / 2, 430), 1: (W - 330, 245), 2: (330, 245)}[p]

    def do_play(self, p, cards):
        pat = analyze(cards)
        t = now()
        if p == 0:
            pos = dict(zip((c.id for c in self.hands[0]), self.hand_layout()))
            srcs = [pos[c.id] for c in cards]
        else:
            ax, ay = AVATAR[p]
            srcs = [(ax - SMALL[0] / 2, ay - SMALL[1] / 2)] * len(cards)
        cnt = Counter(c.rank for c in cards)
        order = sorted(range(len(cards)), key=lambda i: (-cnt[cards[i].rank], cards[i].rank, cards[i].suit))
        cards = [cards[i] for i in order]
        srcs = [srcs[i] for i in order]
        self.hands[p] = remove_cards(self.hands[p], cards)
        self.played += cards
        self.display[p] = {'kind': 'cards', 'cards': cards, 't0': t, 'srcs': srcs, 'pat': pat}
        self.last = (pat, p)
        self.passes = 0
        self.play_count[p] += 1
        if p == 0:
            self.selected.clear()
        cx, cy = self.display_center(p)
        if pat.type == 'rocket':
            self.multiplier *= 2
            self.toast('王 炸 ！', (W / 2, 300), 1.6, color=(255, 80, 60), size=80)
            self.boom(cx, cy, big=True)
            self.snd.play('rocket')
        elif pat.type == 'bomb':
            self.multiplier *= 2
            self.toast('炸 弹 ！', (W / 2, 300), 1.4, color=(255, 150, 40), size=72)
            self.boom(cx, cy)
            self.snd.play('bomb')
        elif pat.type.startswith('plane'):
            self.toast('飞 机', (cx, cy - 70), 1.2, color=(120, 220, 255), size=40)
            self.snd.play('plane')
            self.snd.play('play')
        elif pat.type in ('straight', 'dstraight'):
            self.toast(pat.name, (cx, cy - 70), 1.0, color=(150, 255, 150), size=34)
            self.snd.play('play')
        else:
            self.snd.play('play')
        n = len(self.hands[p])
        if n == 0:
            self.finish(p)
            return
        if n <= 2:
            ax, ay = AVATAR[p]
            self.toast('我只剩一张啦！' if n == 1 else '我只剩两张啦！',
                       (ax + (90 if p != 1 else -90), ay - 60), 1.6, color=(255, 230, 90), size=22, pop=False)
            self.snd.play('warn')
        self.turn = (p + 1) % 3
        self.begin_turn()

    def do_pass(self, p):
        self.display[p] = {'kind': 'text', 'text': '不出', 't0': now()}
        self.snd.play('pass')
        if p == 0:
            self.selected.clear()
        self.passes += 1
        if self.passes == 2:
            self.last = None
            self.passes = 0
        self.turn = (p + 1) % 3
        self.begin_turn()

    def finish(self, winner):
        L = self.landlord
        lw = winner == L
        spring = lw and self.play_count[(L + 1) % 3] == 0 and self.play_count[(L + 2) % 3] == 0
        anti = (not lw) and self.play_count[L] == 1
        if spring or anti:
            self.multiplier *= 2
        unit = self.bid * self.multiplier
        deltas = [0, 0, 0]
        for p in range(3):
            if p == L:
                deltas[p] = 2 * unit if lw else -2 * unit
            else:
                deltas[p] = -unit if lw else unit
            self.scores[p] += deltas[p]
        self.result = {'win': deltas[0] > 0, 'deltas': deltas, 'spring': spring, 'anti': anti,
                       'landlord_win': lw}
        if spring:
            self.toast('春 天 ！', (W / 2, 300), 1.5, color=(255, 120, 200), size=72)
        elif anti:
            self.toast('反 春 ！', (W / 2, 300), 1.5, color=(255, 120, 200), size=72)
        self.state = 'ending'
        self.end_t = now() + (1.6 if spring or anti else 1.1)

    # ---------- 特效 ----------
    def toast(self, text, pos, dur, color=(255, 255, 255), size=36, pop=True):
        self.toasts.append({'surf': text_outline(text, F(size, True), color, (40, 20, 10), 3 if size > 40 else 2),
                            'pos': pos, 't0': now(), 'dur': dur, 'pop': pop})

    def boom(self, x, y, big=False):
        self.shake_t0 = self.flash_t0 = now()
        colors = [(255, 220, 80), (255, 140, 40), (255, 70, 50), (255, 255, 200)]
        for _ in range(110 if big else 70):
            a = random.uniform(0, math.tau)
            sp = random.uniform(120, 520 if big else 400)
            life = random.uniform(0.5, 1.1)
            self.particles.append({'x': x, 'y': y, 'vx': math.cos(a) * sp, 'vy': math.sin(a) * sp - 120,
                                   'life': life, 'max': life, 'color': random.choice(colors),
                                   'size': random.uniform(3, 7), 'g': 500, 'rect': False})

    def confetti(self):
        colors = [(255, 90, 90), (255, 210, 60), (90, 200, 255), (130, 240, 120), (240, 130, 255)]
        for _ in range(160):
            life = random.uniform(2.0, 3.5)
            self.particles.append({'x': random.uniform(0, W), 'y': random.uniform(-200, 0),
                                   'vx': random.uniform(-60, 60), 'vy': random.uniform(80, 220),
                                   'life': life, 'max': life, 'color': random.choice(colors),
                                   'size': random.uniform(4, 8), 'g': 60, 'rect': True})

    # ---------- 布局 ----------
    def hand_layout(self):
        hand = self.hands[0]
        n = len(hand)
        cw, ch = BIG
        sp = min(42, (W - 380 - cw) / max(1, n - 1))
        total = (n - 1) * sp + cw
        x0 = W / 2 - total / 2
        y = H - ch - 28
        return [(x0 + i * sp, y - self.raise_off.get(c.id, 0)) for i, c in enumerate(hand)]

    def card_at(self, pos):
        layout = self.hand_layout()
        for i in range(len(layout) - 1, -1, -1):
            x, y = layout[i]
            if pygame.Rect(x, y, *BIG).collidepoint(pos):
                return i
        return None

    def bottom_pos(self, i):
        return (W / 2 - 104 + i * 72, 14)

    # ---------- 输入 ----------
    def toggle(self, i):
        cid = self.hands[0][i].id
        if cid in self.selected:
            self.selected.discard(cid)
        else:
            self.selected.add(cid)
        self.snd.play('select')

    def drag_range(self):
        if not self.dragging or self.drag_hand_len != len(self.hands[0]):
            return None
        return min(self.drag_start, self.drag_cur), max(self.drag_start, self.drag_cur)

    def finish_drag(self):
        if self.drag_hand_len != len(self.hands[0]):
            return
        a, b = sorted((self.drag_start, self.drag_cur))
        if a == b:
            self.toggle(a)
            return
        swept = self.hands[0][a:b + 1]
        last = self.last[0] if self.my_turn() and self.last else None
        swept_ids = {c.id for c in swept}
        pick = smart_pick(swept, last)
        pick_ids = {c.id for c in pick} if pick else set()
        if pick_ids and not pick_ids <= self.selected:
            self.selected = pick_ids
        elif pick_ids or swept_ids <= self.selected:
            # 要挑的牌已经都选上了：再划一次就全部落下
            self.selected -= swept_ids
        else:
            self.selected ^= swept_ids
        self.snd.play('select')

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.click_buttons(e.pos):
                return
            if self.state in ('bidding', 'reveal', 'playing') and self.hands[0]:
                i = self.card_at(e.pos)
                if i is not None:
                    self.dragging = True
                    self.drag_start = self.drag_cur = i
                    self.drag_hand_len = len(self.hands[0])
        elif e.type == pygame.MOUSEMOTION and self.dragging:
            i = self.card_at(e.pos)
            if i is not None and i != self.drag_cur:
                self.drag_cur = i
                self.snd.play('deal')
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.dragging:
            self.dragging = False
            self.finish_drag()
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
            if self.selected:
                self.selected.clear()
                self.snd.play('select')
        elif e.type == pygame.KEYDOWN:
            if self.my_turn():
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.human_play()
                elif e.key == pygame.K_SPACE and self.last:
                    self.do_pass(0)
                elif e.key == pygame.K_h:
                    self.human_hint()
            elif self.state == 'over' and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.snd.play('click')
                self.new_round()

    def my_turn(self):
        return self.state == 'playing' and self.turn == 0

    def cannot_beat(self):
        """轮到我跟牌但没有任何牌能管上。"""
        return self.last is not None and not self.hints

    def click_buttons(self, pos):
        if self.state == 'bidding' and self.bid_turn == 0:
            for v, b in enumerate(self.bid_btns):
                if b.hit(pos):
                    self.snd.play('click')
                    self.do_bid(0, v)
                    return True
        elif self.my_turn():
            if self.btn_pass.hit(pos):
                self.do_pass(0)
                return True
            if self.cannot_beat():
                return False
            if self.btn_hint.hit(pos):
                self.snd.play('click')
                self.human_hint()
                return True
            if self.btn_play.hit(pos):
                self.human_play()
                return True
        elif self.state == 'over' and self.btn_again.hit(pos):
            self.snd.play('click')
            self.new_round()
            return True
        return False

    def selected_cards(self):
        return [c for c in self.hands[0] if c.id in self.selected]

    def human_hint(self):
        if not self.hints:
            self.toast('没有牌能大过上家', (W / 2, 470), 1.4, size=26, pop=False)
            return
        self.selected = {c.id for c in self.hints[self.hint_idx % len(self.hints)]}
        self.hint_idx += 1

    def human_play(self):
        cards = self.selected_cards()
        if not cards:
            return
        pat = analyze(cards)
        if not pat:
            self.toast('牌型不符合规则', (W / 2, 470), 1.3, color=(255, 140, 120), size=26, pop=False)
            return
        if self.last and not can_beat(pat, self.last[0]):
            self.toast('管不上哦', (W / 2, 470), 1.3, color=(255, 140, 120), size=26, pop=False)
            return
        self.do_play(0, cards)

    # ---------- 更新 ----------
    def update(self, dt):
        t = now()
        for f in self.flyers[:]:
            if t >= f['t0'] + f['dur']:
                self.flyers.remove(f)
                if f.get('done'):
                    f['done']()
        for p in self.particles[:]:
            p['life'] -= dt
            if p['life'] <= 0:
                self.particles.remove(p)
                continue
            p['vy'] += p['g'] * dt
            p['x'] += p['vx'] * dt
            p['y'] += p['vy'] * dt
        self.toasts = [x for x in self.toasts if t < x['t0'] + x['dur']]
        for c in self.hands[0]:
            target = 22 if c.id in self.selected else 0
            cur = self.raise_off.get(c.id, 0)
            self.raise_off[c.id] = cur + (target - cur) * min(1, dt * 18)

        if self.state == 'dealing':
            if self.deal_queue and t >= self.next_deal:
                p, c = self.deal_queue.pop(0)
                self.next_deal = t + 0.035
                self.flyers.append({'surf': self.back[SMALL], 'src': DECK_POS, 'dst': self.deal_target(p),
                                    't0': t, 'dur': 0.25, 'done': (lambda p=p, c=c: self.receive(p, c))})
                self.snd.play('deal')
            elif not self.deal_queue and not self.flyers:
                self.state = 'bidding'
                self.start_bid_turn()
        elif self.state == 'bidding':
            p = self.bid_turn
            if p != 0 and t >= self.next_ai:
                self.do_bid(p, choose_bid(self.level, self.hands[p], self.bid))
        elif self.state == 'reveal':
            if not self.bottom_given and t >= self.reveal_t0 + 1.2:
                self.give_bottom()
            if self.bottom_given and not self.flyers and t >= self.reveal_t0 + 1.7:
                self.start_playing()
        elif self.state == 'playing':
            p = self.turn
            if p != 0 and t >= self.next_ai:
                self.take_ai_result(p)
        elif self.state == 'ending':
            if t >= self.end_t:
                self.state = 'over'
                if self.result['win']:
                    self.snd.play('win')
                    self.confetti()
                else:
                    self.snd.play('lose')
        elif self.state == 'redeal':
            if t >= self.redeal_t:
                self.new_round()

    # ---------- 绘制 ----------
    def draw(self):
        """画到 self.canvas 上，返回震屏偏移。"""
        t = now()
        c = self.canvas
        c.blit(self.bg, (0, 0))
        mouse = mouse_pos()
        self.draw_info(c)
        self.draw_bottom(c, t)
        self.draw_tracker(c)
        for p in range(3):
            self.draw_player(c, p, t)
        if self.state == 'dealing':
            for i in range(min(8, len(self.deal_queue) // 6 + 1)):
                c.blit(self.shadow[SMALL], (DECK_POS[0] + 2, DECK_POS[1] - i * 2 + 3))
                c.blit(self.back[SMALL], (DECK_POS[0], DECK_POS[1] - i * 2))
        for p in range(3):
            self.draw_display(c, p, t)
        self.draw_hand(c, t)
        self.draw_buttons(c, mouse)
        for f in self.flyers:
            k = ease_out((t - f['t0']) / f['dur'])
            if t < f['t0']:
                continue
            pos = (lerp(f['src'][0], f['dst'][0], k), lerp(f['src'][1], f['dst'][1], k))
            c.blit(f['surf'], pos)
        for p in self.particles:
            k = p['life'] / p['max']
            size = max(1, p['size'] * (0.4 + 0.6 * k))
            if p['rect']:
                pygame.draw.rect(c, p['color'], (p['x'], p['y'], size, size * 0.6))
            else:
                pygame.draw.circle(c, p['color'], (int(p['x']), int(p['y'])), int(size))
        fa = t - self.flash_t0
        if fa < 0.3:
            fl = pygame.Surface((W, H))
            fl.fill((255, 240, 200))
            fl.set_alpha(int(150 * (1 - fa / 0.3)))
            c.blit(fl, (0, 0))
        for x in self.toasts:
            age = t - x['t0']
            img = x['surf']
            if x['pop'] and age < 0.2:
                img = pygame.transform.rotozoom(img, 0, 1.8 - 0.8 * ease_out(age / 0.2))
            rest = x['dur'] - age
            if rest < 0.35:
                if img is x['surf']:
                    img = img.copy()
                img.set_alpha(int(255 * max(0, rest) / 0.35))
            dy = 0 if x['pop'] else -12 * ease_out(age / 0.4)
            blit_center(c, img, (x['pos'][0], x['pos'][1] + dy))
        if self.state == 'over':
            self.draw_result(c, mouse)
        off = (0, 0)
        sa = t - self.shake_t0
        if sa < 0.5:
            amp = 10 * (1 - sa / 0.5)
            off = (random.uniform(-amp, amp), random.uniform(-amp, amp))
        return off

    def panel(self, surf, rect, alpha=120, radius=12):
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 0, 0, alpha), (0, 0, *rect.size), border_radius=radius)
        surf.blit(s, rect.topleft)

    def draw_info(self, c):
        self.panel(c, pygame.Rect(14, 12, 340, 40))
        txt = f'底分 {self.bid if self.landlord is not None else "-"}    倍数 ×{self.multiplier}    难度 {dict(LEVELS)[self.level]}'
        c.blit(F(20, True).render(txt, True, (255, 230, 150)), (28, 18))
        self.panel(c, pygame.Rect(W - 354, 12, 340, 40))
        x = W - 340
        c.blit(F(18, True).render('积分', True, (255, 230, 150)), (x, 20))
        x += 50
        for p in range(3):
            col = (140, 255, 150) if self.scores[p] > 0 else (255, 150, 140) if self.scores[p] < 0 else (230, 230, 230)
            img = F(18).render(f'{NAMES[p]} {self.scores[p]}', True, col)
            c.blit(img, (x, 20))
            x += img.get_width() + 20

    def draw_tracker(self, c):
        """记牌器：显示另外两家手里（含未亮的底牌）每种点数还剩几张。"""
        if self.state in ('dealing', 'redeal'):
            return
        mine = Counter(card.rank for card in self.hands[0])
        played = Counter(card.rank for card in self.played)
        ranks = [17, 16] + list(range(15, 2, -1))
        left = {r: (1 if r >= 16 else 4) - mine[r] - played[r] for r in ranks}
        rocket = left[16] == 1 and left[17] == 1
        col_w, title_w = 32, 30
        width = title_w + col_w * len(ranks) + 10
        rect = pygame.Rect(W // 2 - width // 2, 112, width, 52)
        self.panel(c, rect, 140, 10)
        tf = F(13, True)
        for i, ch in enumerate('记牌器'):
            blit_center(c, tf.render(ch, True, (255, 215, 120)), (rect.x + 18, rect.y + 11 + i * 15))
        for i, r in enumerate(ranks):
            x = rect.x + title_w + 5 + i * col_w
            if i % 2 == 0:
                bgc = pygame.Surface((col_w, rect.h - 8), pygame.SRCALPHA)
                bgc.fill((255, 255, 255, 14))
                c.blit(bgc, (x, rect.y + 4))
            cx = x + col_w / 2
            if r >= 16:
                lab, lc = ('大' if r == 17 else '小'), ((255, 110, 100) if r == 17 else (235, 235, 235))
            else:
                lab, lc = RANK_NAMES[r], (235, 235, 235)
            blit_center(c, F(15, True).render(lab, True, lc), (cx, rect.y + 15))
            n = left[r]
            if n == 0:
                nc = (110, 110, 110)
            elif (n == 4 and r < 16) or (r >= 16 and rocket):
                nc = (255, 120, 80)   # 可能有炸弹 / 王炸
            else:
                nc = (255, 235, 160)
            blit_center(c, F(18, True).render(str(n), True, nc), (cx, rect.y + 37))

    def draw_bottom(self, c, t):
        for i, card in enumerate(self.bottom):
            pos = self.bottom_pos(i)
            if self.reveal_t0 is None:
                if self.state in ('dealing', 'bidding', 'redeal'):
                    self.draw_card(c, card, pos, SMALL, back=True)
                continue
            age = t - self.reveal_t0 - i * 0.12
            if age < 0:
                img, sx = self.back[SMALL], 1
            elif age < 0.18:
                img, sx = self.back[SMALL], 1 - age / 0.18
            elif age < 0.36:
                img, sx = self.face(card, SMALL), (age - 0.18) / 0.18
            else:
                img, sx = self.face(card, SMALL), 1
            w = max(1, int(SMALL[0] * sx))
            img = pygame.transform.smoothscale(img, (w, SMALL[1])) if w != SMALL[0] else img
            c.blit(self.shadow[SMALL], (pos[0] + 2, pos[1] + 3))
            c.blit(img, (pos[0] + (SMALL[0] - w) / 2, pos[1]))

    def draw_player(self, c, p, t):
        ax, ay = AVATAR[p]
        active = (self.state == 'bidding' and self.bid_turn == p) or (self.state == 'playing' and self.turn == p)
        if active:
            r = 44 + 3 * math.sin(t * 6)
            pygame.draw.circle(c, (255, 220, 90), (ax, ay), int(r), 4)
        pygame.draw.circle(c, (255, 255, 255), (ax, ay), 38)
        pygame.draw.circle(c, AVATAR_COLOR[p], (ax, ay), 35)
        blit_center(c, F(30, True).render(AVATAR_CHAR[p], True, (255, 255, 255)), (ax, ay))
        if self.landlord is not None and self.state != 'reveal' or (self.state == 'reveal' and self.bottom_given):
            is_l = p == self.landlord
            badge = pygame.Rect(0, 0, 50, 24)
            badge.center = (ax, ay - 46)
            pygame.draw.rect(c, (240, 180, 40) if is_l else (70, 160, 90), badge, border_radius=12)
            pygame.draw.rect(c, (255, 255, 255), badge, 2, border_radius=12)
            blit_center(c, F(15, True).render('地主' if is_l else '农民', True, (255, 255, 255)), badge.center)
        blit_center(c, text_outline(NAMES[p], F(18, True), (255, 255, 255), (20, 40, 25), 1), (ax, ay + 52))
        if p == 0:
            return
        n = len(self.hands[p])
        col = (255, 90, 80) if 0 < n <= 2 else (255, 240, 200)
        blit_center(c, text_outline(f'剩 {n} 张', F(17, True), col, (20, 40, 25), 1), (ax, ay + 76))
        if active and self.state in ('playing', 'bidding'):
            dots = '.' * (int(t * 3) % 4)
            c.blit(F(16).render('思考中' + dots, True, (230, 230, 230)), (ax - 26, ay + 92))
        x = STACK_X[p]
        if self.state == 'over':
            for i, card in enumerate(self.hands[p]):
                self.draw_card(c, card, (x, STACK_Y + i * 22), SMALL)
        else:
            for i in range(n):
                self.draw_card(c, None, (x, STACK_Y + i * 16), SMALL, back=True)

    def draw_display(self, c, p, t):
        d = self.display[p]
        if not d:
            return
        if d['kind'] == 'text':
            age = t - d['t0']
            img = text_outline(d['text'], F(30, True), (255, 245, 210), (40, 30, 10), 2)
            if age < 0.15:
                img = pygame.transform.rotozoom(img, 0, 1.5 - 0.5 * age / 0.15)
            blit_center(c, img, self.display_center(p))
            return
        cards = d['cards']
        dst = self.display_layout(p, len(cards))
        k = ease_out((t - d['t0']) / 0.28)
        for card, s, e in zip(cards, d['srcs'], dst):
            pos = (lerp(s[0], e[0], k), lerp(s[1], e[1], k))
            self.draw_card(c, card, pos, SMALL)

    def draw_hand(self, c, t):
        layout = self.hand_layout()
        hl = None
        if t < self.new_ids_until:
            hl = pygame.Surface(BIG, pygame.SRCALPHA)
            pygame.draw.rect(hl, (255, 220, 60, 70), (0, 0, *BIG), border_radius=8)
            pygame.draw.rect(hl, (255, 200, 0, 220), (0, 0, *BIG), 3, border_radius=8)
        rng = self.drag_range()
        for i, (card, pos) in enumerate(zip(self.hands[0], layout)):
            self.draw_card(c, card, pos, BIG)
            if rng and rng[0] <= i <= rng[1]:
                sw = pygame.Surface(BIG, pygame.SRCALPHA)
                pygame.draw.rect(sw, (40, 60, 110, 90), (0, 0, *BIG), border_radius=8)
                c.blit(sw, pos)
            elif card.id in self.selected:
                sel = pygame.Surface(BIG, pygame.SRCALPHA)
                pygame.draw.rect(sel, (80, 150, 255, 40), (0, 0, *BIG), border_radius=8)
                c.blit(sel, pos)
            if hl and card.id in self.new_ids:
                c.blit(hl, pos)

    def draw_buttons(self, c, mouse):
        if self.state == 'bidding' and self.bid_turn == 0:
            for v, b in enumerate(self.bid_btns):
                b.enabled = v == 0 or v > self.bid
                b.draw(c, mouse)
        elif self.my_turn():
            if self.cannot_beat():
                # 要不起：只留一个居中的“不出”
                self.btn_pass.rect.centerx = W // 2
                self.btn_pass.enabled = True
                self.btn_pass.draw(c, mouse)
                return
            self.btn_pass.rect.centerx = W // 2 - 160
            self.btn_pass.enabled = self.last is not None
            self.btn_play.enabled = bool(self.selected)
            for b in (self.btn_pass, self.btn_hint, self.btn_play):
                b.draw(c, mouse)
            cards = self.selected_cards()
            if cards:
                pat = analyze(cards)
                if not pat:
                    txt, col = '不合规则', (255, 130, 110)
                elif self.last and not can_beat(pat, self.last[0]):
                    txt, col = f'{pat.name} · 管不上', (255, 190, 100)
                else:
                    txt, col = pat.name, (150, 255, 160)
                c.blit(text_outline(txt, F(20, True), col, (20, 30, 20), 1), (W // 2 + 235, 520))

    def draw_result(self, c, mouse):
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 110))
        c.blit(ov, (0, 0))
        r = self.result
        rect = pygame.Rect(0, 0, 560, 340)
        rect.center = (W // 2, H // 2 - 10)
        pygame.draw.rect(c, (0, 0, 0), rect.move(0, 6), border_radius=18)
        pygame.draw.rect(c, (252, 246, 228), rect, border_radius=18)
        pygame.draw.rect(c, (220, 170, 60), rect, 4, border_radius=18)
        title = '胜 利 ！' if r['win'] else '失 败'
        tc = (230, 120, 20) if r['win'] else (90, 100, 120)
        blit_center(c, text_outline(title, F(46, True), tc, (255, 255, 255), 2), (rect.centerx, rect.y + 46))
        extra = '  春天×2' if r['spring'] else '  反春×2' if r['anti'] else ''
        info = f'地主：{NAMES[self.landlord]}    底分 {self.bid}    倍数 ×{self.multiplier}{extra}'
        blit_center(c, F(19).render(info, True, (80, 60, 40)), (rect.centerx, rect.y + 96))
        y = rect.y + 130
        for p in range(3):
            role = '地主' if p == self.landlord else '农民'
            d = r['deltas'][p]
            col = (40, 150, 60) if d > 0 else (200, 60, 50)
            c.blit(F(21, True).render(NAMES[p], True, (60, 50, 40)), (rect.x + 80, y))
            c.blit(F(20).render(role, True, (120, 100, 80)), (rect.x + 200, y + 1))
            c.blit(F(21, True).render(f'{d:+d}', True, col), (rect.x + 300, y))
            c.blit(F(20).render(f'总分 {self.scores[p]}', True, (90, 80, 70)), (rect.x + 390, y + 1))
            y += 36
        self.btn_again.draw(c, mouse)
