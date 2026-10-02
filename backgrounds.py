"""牌桌背景：默认绿色、内置几张预设、玩家自选图片。"""
import os

import pygame

from characters import asset_path

PRESETS = [
    ('default', '默认', None),
    ('redwood', '红木', 'redwood.jpg'),
    ('velvet', '绒布', 'velvet.jpg'),
    ('courtyard', '庭院', 'courtyard.jpg'),
]
CUSTOM_FILE = 'custom_bg.jpg'


def cover(img, size):
    """等比缩放到铺满 size，多出的部分居中裁掉。"""
    tw, th = size
    r = max(tw / img.get_width(), th / img.get_height())
    w, h = max(tw, round(img.get_width() * r)), max(th, round(img.get_height() * r))
    img = pygame.transform.smoothscale(img.convert(), (w, h))
    return img.subsurface(((w - tw) // 2, (h - th) // 2, tw, th)).copy()


def load(choice, user_dir, size, default):
    """返回 choice 对应的背景；读不到时退回默认背景。"""
    try:
        if choice == 'custom':
            img = cover(pygame.image.load(os.path.join(user_dir, CUSTOM_FILE)), size)
            shade = pygame.Surface(size, pygame.SRCALPHA)
            shade.fill((0, 0, 0, 50))            # 自选图片可能偏亮，稍微压暗让牌更清楚
            img.blit(shade, (0, 0))
            return img
        fname = dict((k, f) for k, _, f in PRESETS).get(choice)
        if fname:
            return cover(pygame.image.load(asset_path('backgrounds', fname)), size)
    except (pygame.error, FileNotFoundError, ValueError):
        pass
    return default


def has_custom(user_dir):
    return os.path.exists(os.path.join(user_dir, CUSTOM_FILE))


def ask_image_file():
    """弹出系统的“打开文件”对话框选图片，取消返回 None。"""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        path = filedialog.askopenfilename(
            parent=root, title='选择牌桌背景图片',
            filetypes=[('图片', '*.png *.jpg *.jpeg *.bmp *.gif *.webp'), ('所有文件', '*.*')])
    finally:
        root.destroy()
    return path or None


def import_custom(path, user_dir, size):
    """把选中的图片缩放后存一份到设置目录（原图挪走也不影响）。成功返回 True。"""
    try:
        img = cover(pygame.image.load(path), size)
        pygame.image.save(img, os.path.join(user_dir, CUSTOM_FILE))
        return True
    except (pygame.error, FileNotFoundError, ValueError, OSError):
        return False
