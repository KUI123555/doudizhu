"""斗地主 —— 入口：主菜单、暂停菜单、设置（音量 / 难度 / 显示模式）。运行：python main.py"""
import ctypes
import ctypes.wintypes
import json
import math
import os
import sys

import pygame

import game as G
from ai import LEVEL_TIPS, LEVELS
from game import BIG, FPS, H, W, Button, F, Game, blit_center, mouse_pos, text_outline, to_logical
from rules import Card

# 打包成 exe 后 __file__ 在临时目录里，设置文件要放在 exe 旁边
if getattr(sys, 'frozen', False):
    HERE = os.path.dirname(sys.executable)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, 'settings.json')
DISPLAY_MODES = [('windowed', '窗口化'), ('borderless', '全屏窗口化'), ('fullscreen', '全屏')]
MODE_TIPS = {
    'windowed': '普通窗口，可以拖动边框调整大小',
    'borderless': '无边框铺满屏幕，切换到其他窗口更方便',
    'fullscreen': '独占全屏',
}
PANEL_BG = (252, 246, 228)
PANEL_BORDER = (220, 170, 60)
TEXT_DARK = (80, 60, 40)


# ---------------- 设置 ----------------

def load_settings():
    s = {'volume': 0.8, 'display': 'windowed', 'difficulty': 'normal'}
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data.get('volume'), (int, float)):
            s['volume'] = max(0.0, min(1.0, float(data['volume'])))
        if data.get('display') in dict(DISPLAY_MODES):
            s['display'] = data['display']
        if data.get('difficulty') in dict(LEVELS):
            s['difficulty'] = data['difficulty']
    except (OSError, ValueError, AttributeError):
        pass
    return s


def save_settings(s):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _window_rect():
    hwnd = pygame.display.get_wm_info()['window']
    r = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return hwnd, r


def move_window(x=None, y=None, center_in=None):
    """移动已存在的窗口（SDL_VIDEO_WINDOW_POS 只在第一次建窗口时生效）。"""
    if sys.platform != 'win32':
        return
    try:
        hwnd, r = _window_rect()
        if center_in:
            dw, dh = center_in
            w, h = r.right - r.left, r.bottom - r.top
            x, y = (dw - w) // 2, max(0, (dh - h) // 2 - 20)
        SWP_NOSIZE, SWP_NOZORDER = 0x0001, 0x0004
        ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER)
    except Exception:
        pass


def apply_display(mode):
    dw, dh = pygame.display.get_desktop_sizes()[0]
    if mode == 'fullscreen':
        pygame.display.set_mode((dw, dh), pygame.FULLSCREEN)
    elif mode == 'borderless':
        os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
        pygame.display.set_mode((dw, dh), pygame.NOFRAME)
        move_window(0, 0)
    else:
        # 屏幕放不下 1280x760 时按比例缩小窗口
        scale = min(1.0, dw * 0.95 / W, dh * 0.88 / H)
        w, h = int(W * scale), int(H * scale)
        os.environ['SDL_VIDEO_WINDOW_POS'] = f'{(dw - w) // 2},{max(0, (dh - h) // 2 - 20)}'
        pygame.display.set_mode((w, h), pygame.RESIZABLE)
        move_window(center_in=(dw, dh))


# ---------------- 控件 ----------------

class Slider:
    def __init__(self, x, y, w, value):
        self.track = pygame.Rect(x, y - 4, w, 8)
        self.hit_rect = self.track.inflate(30, 30)
        self.value = value
        self.dragging = False

    def set_from(self, px):
        self.value = max(0.0, min(1.0, (px - self.track.x) / self.track.w))

    def draw(self, c, mouse):
        pygame.draw.rect(c, (200, 190, 170), self.track, border_radius=4)
        filled = self.track.copy()
        filled.w = int(self.track.w * self.value)
        pygame.draw.rect(c, (230, 120, 30), filled, border_radius=4)
        kx, ky = self.track.x + self.track.w * self.value, self.track.centery
        r = 15 if self.dragging or self.hit_rect.collidepoint(mouse) else 13
        pygame.draw.circle(c, (230, 120, 30), (int(kx), ky), r)
        pygame.draw.circle(c, (255, 255, 255), (int(kx), ky), r - 4)


def draw_panel(c, rect):
    pygame.draw.rect(c, (0, 0, 0), rect.move(0, 6), border_radius=18)
    pygame.draw.rect(c, PANEL_BG, rect, border_radius=18)
    pygame.draw.rect(c, PANEL_BORDER, rect, 4, border_radius=18)


def dim(c, alpha=130):
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, alpha))
    c.blit(ov, (0, 0))


# ---------------- 程序 ----------------

class App:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception:
            pass
        pygame.display.set_caption('斗地主')
        self.settings = load_settings()
        apply_display(self.settings['display'])
        self.game = Game()
        self.game.snd.set_volume(self.settings['volume'])
        self.game.level = self.settings['difficulty']
        self.menu = 'main'          # 'main' 主菜单 / 'pause' 暂停 / 'settings' 设置 / None 游戏中
        self.settings_back = 'main'
        self.clock = pygame.time.Clock()

        cx = W // 2
        self.main_btns = [
            ('new', Button('新游戏', (cx, 455), (230, 120, 30), w=260, h=58)),
            ('settings', Button('设置', (cx, 530), (50, 130, 210), w=260, h=58)),
            ('quit', Button('退出游戏', (cx, 605), (110, 120, 130), w=260, h=58)),
        ]
        self.pause_rect = pygame.Rect(0, 0, 360, 390)
        self.pause_rect.center = (W // 2, H // 2)
        py = self.pause_rect.y
        self.pause_btns = [
            (key, Button(text, (cx, py + 120 + i * 68), color, w=240, h=52))
            for i, (key, text, color) in enumerate([
                ('resume', '继续游戏', (230, 120, 30)), ('new', '新游戏', (220, 90, 50)),
                ('settings', '设置', (50, 130, 210)), ('quit', '退出游戏', (110, 120, 130))])
        ]
        self.btn_menu = Button('菜单', (W - 62, H - 34), (90, 100, 110), w=96, h=40)

        self.set_rect = pygame.Rect(0, 0, 620, 540)
        self.set_rect.center = (W // 2, H // 2)
        sx, sy = self.set_rect.topleft
        self.slider = Slider(sx + 160, sy + 130, 320, self.settings['volume'])
        self.level_btns = [(lv, Button(label, (sx + 130 + i * 180, sy + 225), (95, 105, 120), w=160, h=50))
                           for i, (lv, label) in enumerate(LEVELS)]
        self.mode_btns = [(mode, Button(label, (sx + 130 + i * 180, sy + 355), (95, 105, 120), w=160, h=50))
                          for i, (mode, label) in enumerate(DISPLAY_MODES)]
        self.btn_back = Button('返回', (W // 2, sy + 480), (230, 120, 30), w=180, h=52)

        self.cover_cards = [Card(i) for i in (42, 45, 48, 52, 53)]  # K♣ A♥ 2♠ 小王 大王

    # ---------- 主循环 ----------
    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            for e in pygame.event.get():
                self.handle(e)
            if self.menu is None:
                G.advance_clock(dt)
                self.game.update(dt)
            self.draw()
            pygame.display.flip()

    def quit(self):
        save_settings(self.settings)
        pygame.quit()
        sys.exit()

    # ---------- 输入 ----------
    def handle(self, e):
        if e.type == pygame.QUIT:
            self.quit()
        if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            e = pygame.event.Event(e.type, {**e.dict, 'pos': to_logical(e.pos)})
        click = e.type == pygame.MOUSEBUTTONDOWN and e.button == 1
        esc = e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE

        if self.menu is None:
            if esc or (click and self.btn_menu.hit(e.pos)):
                self.game.snd.play('click')
                self.open_menu('pause')
            else:
                self.game.handle(e)
            return
        if esc:
            if self.menu == 'pause':
                self.menu = None
            elif self.menu == 'settings':
                self.menu = self.settings_back
            return
        if self.menu == 'settings':
            self.handle_settings(e, click)
            return
        if click:
            for key, b in (self.main_btns if self.menu == 'main' else self.pause_btns):
                if b.hit(e.pos):
                    self.game.snd.play('click')
                    self.action(key)
                    return

    def open_menu(self, menu):
        self.game.dragging = False
        self.menu = menu

    def action(self, key):
        if key == 'new':
            g = self.game
            g.scores = [0, 0, 0]
            g.toasts, g.particles = [], []
            g.new_round()
            self.menu = None
        elif key == 'resume':
            self.menu = None
        elif key == 'settings':
            self.settings_back = self.menu
            self.menu = 'settings'
        elif key == 'quit':
            self.quit()

    def handle_settings(self, e, click):
        if click:
            if self.slider.hit_rect.collidepoint(e.pos):
                self.slider.dragging = True
                self.set_volume(e.pos[0])
                return
            for lv, b in self.level_btns:
                if b.hit(e.pos):
                    self.game.snd.play('click')
                    self.settings['difficulty'] = lv
                    self.game.level = lv
                    save_settings(self.settings)
                    return
            for mode, b in self.mode_btns:
                if b.hit(e.pos):
                    self.game.snd.play('click')
                    if mode != self.settings['display']:
                        self.settings['display'] = mode
                        apply_display(mode)
                        save_settings(self.settings)
                    return
            if self.btn_back.hit(e.pos):
                self.game.snd.play('click')
                self.menu = self.settings_back
        elif e.type == pygame.MOUSEMOTION and self.slider.dragging:
            self.set_volume(e.pos[0])
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.slider.dragging:
            self.slider.dragging = False
            self.game.snd.play('play')   # 试听
            save_settings(self.settings)

    def set_volume(self, px):
        self.slider.set_from(px)
        self.settings['volume'] = round(self.slider.value, 2)
        self.game.snd.set_volume(self.slider.value)

    # ---------- 绘制 ----------
    def draw(self):
        c = self.game.canvas
        mouse = mouse_pos()
        off = (0, 0)
        on_cover = self.menu == 'main' or (self.menu == 'settings' and self.settings_back == 'main')
        if on_cover:
            self.draw_cover(c, mouse if self.menu == 'main' else (-1, -1))
        else:
            off = self.game.draw()
            if self.menu is None:
                self.btn_menu.draw(c, mouse)
            else:
                off = (0, 0)
                dim(c)
            if self.menu == 'pause':
                self.draw_pause(c, mouse)
        if self.menu == 'settings':
            if on_cover:
                dim(c)
            self.draw_settings(c, mouse)
        self.present(off)

    def present(self, off):
        screen = pygame.display.get_surface()
        sw, sh = screen.get_size()
        scale = min(sw / W, sh / H)
        dw, dh = max(1, round(W * scale)), max(1, round(H * scale))
        ox, oy = (sw - dw) // 2, (sh - dh) // 2
        G.VIEW.update(scale=scale, ox=ox, oy=oy)
        screen.fill((0, 0, 0))
        c = self.game.canvas
        img = c if (dw, dh) == (W, H) else pygame.transform.smoothscale(c, (dw, dh))
        screen.blit(img, (ox + off[0] * scale, oy + off[1] * scale))

    def draw_cover(self, c, mouse):
        c.blit(self.game.bg, (0, 0))
        t = pygame.time.get_ticks() / 1000.0
        pivot_x, pivot_y, r = W / 2, 455, 210
        for i, card in enumerate(self.cover_cards):
            a = (i - 2) * 14
            bob = 5 * math.sin(t * 1.6 + i * 0.8)
            x = pivot_x + r * math.sin(math.radians(a))
            y = pivot_y - r * math.cos(math.radians(a)) + bob
            shadow = pygame.transform.rotozoom(self.game.shadow[BIG], -a, 1.15)
            blit_center(c, shadow, (x + 4, y + 6))
            blit_center(c, pygame.transform.rotozoom(self.game.face(card, BIG), -a, 1.15), (x, y))
        blit_center(c, text_outline('斗 地 主', F(96, True), (255, 215, 90), (100, 35, 10), 5), (W / 2, 100))
        for _, b in self.main_btns:
            b.draw(c, mouse)
        tip = 'Esc 打开菜单   ·   回车 出牌   ·   空格 不出   ·   H 提示   ·   右键 取消选牌'
        blit_center(c, F(16).render(tip, True, (190, 220, 195)), (W / 2, H - 28))

    def draw_pause(self, c, mouse):
        draw_panel(c, self.pause_rect)
        blit_center(c, F(34, True).render('暂 停', True, TEXT_DARK), (W / 2, self.pause_rect.y + 52))
        for _, b in self.pause_btns:
            b.draw(c, mouse)

    def draw_settings(self, c, mouse):
        rect = self.set_rect
        draw_panel(c, rect)
        sx, sy = rect.topleft
        blit_center(c, F(34, True).render('设 置', True, TEXT_DARK), (W / 2, sy + 50))
        lab = F(22, True)
        c.blit(lab.render('音量', True, TEXT_DARK), (sx + 60, sy + 114))
        self.slider.draw(c, mouse)
        c.blit(F(21, True).render(f'{round(self.slider.value * 100)}%', True, (200, 100, 30)), (sx + 505, sy + 115))
        tip = F(16)
        c.blit(lab.render('电脑难度', True, TEXT_DARK), (sx + 60, sy + 170))
        for lv, b in self.level_btns:
            b.color = (230, 120, 30) if lv == self.settings['difficulty'] else (150, 155, 165)
            b.draw(c, mouse)
        blit_center(c, tip.render(LEVEL_TIPS[self.settings['difficulty']], True, (140, 120, 100)),
                    (W / 2, sy + 268))
        c.blit(lab.render('显示模式', True, TEXT_DARK), (sx + 60, sy + 300))
        for mode, b in self.mode_btns:
            b.color = (230, 120, 30) if mode == self.settings['display'] else (150, 155, 165)
            b.draw(c, mouse)
        blit_center(c, tip.render(MODE_TIPS[self.settings['display']], True, (140, 120, 100)),
                    (W / 2, sy + 398))
        self.btn_back.draw(c, mouse)


if __name__ == '__main__':
    App().run()
