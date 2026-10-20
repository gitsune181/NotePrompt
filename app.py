"""NotePrompt — copy nhanh prompt Prom / Go / Img của Niche/Kênh đang làm việc.

App dùng 1 "thư mục dữ liệu" chứa 2 file:
  data.json      — prompt của các niche/kênh (sửa được trong app)
  settings.json  — cài đặt: vị trí cửa sổ, ghim, mục đang chọn, màu nút
Dữ liệu mặc định ở %APPDATA%\\NotePrompt, tách riêng khỏi các ứng dụng khác.
Lần đầu mở luôn trống; người dùng chủ động chọn file để nhập prompt.
"""
import html
import json
import os
import sys
from datetime import datetime

from PySide6.QtCore import (QEasingCurve, QPoint, QRectF, QSize, Qt, QTimer, QUrl,
                            QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QIcon, QLinearGradient,
                           QPainter, QPainterPath, QPen, QRadialGradient, QRegion)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QFileDialog, QGridLayout,
                               QFrame, QGraphicsColorizeEffect,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMenu, QPlainTextEdit, QPushButton, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

import glass
import prompts
import store

APP_NAME = 'NotePrompt'
HOME_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), APP_NAME)
POINTER_FILE = os.path.join(HOME_DIR, 'folder.txt')   # nhớ thư mục dữ liệu đã chọn
DATA_NAME = 'data.json'
SETTINGS_NAME = 'settings.json'
HISTORY_NAME = 'history.json'   # các bản trước mỗi phiên sửa
WATCH_MS = 2000
FLASH_MS = 800   # giữ màu xanh sau khi copy (giống Auto Prompt)
FADE_MS = 180    # thời gian mờ từ xanh về màu gốc
GREEN = '#10b981'
# Cửa sổ chính chỉ còn chế độ Niche nên giữ dạng hẹp, bằng nửa bề
# rộng cũ (380 px). Các hộp thoại chỉnh sửa vẫn giữ kích thước riêng.
WIDTH = 190
ROW_H = 30
SUGG_ROWS = 7   # số dòng gợi ý tối đa hiện cùng lúc

ICON_FONT = 'Segoe MDL2 Assets'
I_PIN, I_UNPIN, I_MORE, I_MIN, I_CLOSE = '\uE718', '\uE77A', '\uE712', '\uE921', '\uE8BB'
I_ADD, I_EDIT = '\uE710', '\uE70F'

KIND_LABEL = {'niche': 'Niche', 'channel': 'Kênh'}
# (field, nhãn, màu mặc định, mô tả) — màu đổi được trong Cài đặt
ACTIONS = [
    ('prom', 'Prom', '#ec4899', 'Prompt riêng lẻ, không nối Style'),
    ('go', 'Go', '#f5b428', 'Prompt chính (đã gồm Style)'),
    ('img', 'Img', '#22d3ee', 'Prompt Gen Ảnh (đã gồm Style)'),
]
DEFAULT_COLORS = {f: c for f, _, c, _ in ACTIONS}
DEFAULT_NAMES = {f: lb for f, lb, _, _ in ACTIONS}
NAMES = dict(DEFAULT_NAMES)   # tên nút đang dùng (đổi được trong Cài đặt)
SAVE_DELAY_MS = 600   # ngừng gõ bao lâu thì tự lưu


def resource(name):
    """File đóng gói kèm exe (PyInstaller giải nén vào sys._MEIPASS) hoặc nằm cạnh app.py."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def app_dir():
    """Thư mục chứa exe (khi đã đóng gói) hoặc chứa app.py (khi chạy source)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def find_folder():
    """Thư mục chứa data.json + settings.json."""
    try:
        with open(POINTER_FILE, 'r', encoding='utf-8') as f:
            chosen = f.read().strip()
        if chosen and os.path.isdir(chosen):
            return chosen
    except OSError:
        pass
    if os.path.isfile(os.path.join(app_dir(), DATA_NAME)):
        return app_dir()   # để data.json cạnh exe là tự dùng luôn
    return HOME_DIR


def remember_folder(folder):
    os.makedirs(HOME_DIR, exist_ok=True)
    if same_path(folder, HOME_DIR):
        if os.path.isfile(POINTER_FILE):
            os.remove(POINTER_FILE)
        return
    with open(POINTER_FILE, 'w', encoding='utf-8') as f:
        f.write(folder)


def load_settings(folder):
    try:
        with open(os.path.join(folder, SETTINGS_NAME), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(folder, data):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, SETTINGS_NAME), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def preview_tip(title, text):
    text = text.strip()
    body = html.escape(text[:400] + ('…' if len(text) > 400 else '')) if text else '(chưa có nội dung)'
    return (f'<b>{html.escape(title)}</b><p style="white-space:pre-wrap; margin-top:4px">{body}</p>')


def text_color(hex_color):
    """Chữ trắng trên nền tối, chữ đen trên nền sáng."""
    c = QColor(hex_color)
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return '#14161f' if lum > 150 else '#ffffff'


def action_style(hex_color):
    c = QColor(hex_color)
    r, g, b = c.red(), c.green(), c.blue()
    return (f'QPushButton#action[empty="false"] {{ color: {text_color(hex_color)};'
            f' border: 1px solid rgba(255,255,255,80);'
            f' background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba({r},{g},{b},240),'
            f' stop:0.5 rgba({r},{g},{b},200), stop:1 rgba({r},{g},{b},170)); }}'
            f'QPushButton#action[empty="false"]:hover {{ background: rgba({r},{g},{b},255); }}'
            f'QPushButton#action[done="true"] {{ color: #ffffff; border: 1px solid #6ee7b7;'
            f' background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #34d399, stop:0.5 {GREEN},'
            f' stop:1 #059669); }}')


def flash(button):
    """Giống nút Prom / Go / Img ở Bảng phân tích thẻ (Auto Prompt): cả nút chuyển xanh lá,
    giữ 0,8 giây rồi mờ nhanh về màu gốc."""
    if button.property('done'):
        return
    button.setProperty('done', True)
    repolish(button)

    def restore():
        button.setProperty('done', False)
        repolish(button)
        fx = QGraphicsColorizeEffect(button)
        fx.setColor(QColor(GREEN))
        button.setGraphicsEffect(fx)
        anim = QVariantAnimation(button, startValue=1.0, endValue=0.0, duration=FADE_MS)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(fx.setStrength)
        anim.finished.connect(lambda: button.setGraphicsEffect(None))
        anim.start(QVariantAnimation.DeleteWhenStopped)
    QTimer.singleShot(FLASH_MS, restore)


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


STYLE = """
* { color: #f3f5fa; font-family: 'Segoe UI'; font-size: 9pt; }
QToolTip { background: #1b1e2c; color: #e9ecf5; border: 1px solid rgba(255,255,255,40);
           padding: 6px 8px; border-radius: 6px; }
QLabel#appName { font-weight: 600; font-size: 8.5pt; color: rgba(255,255,255,220); }
QLabel#muted, QLabel#status { color: rgba(225,232,255,140); }
QLabel#muted { font-size: 8pt; }
QLabel#status { font-size: 7pt; }
QLabel#dlgTitle { font-size: 11pt; font-weight: 600; }

QPushButton#icon { font-family: 'Segoe MDL2 Assets'; font-size: 9pt; background: transparent;
                   border: none; border-radius: 6px; min-width: 26px; min-height: 24px;
                   color: rgba(240,244,255,190); }
QPushButton#icon:hover { background: rgba(255,255,255,28); color: #ffffff; }
QPushButton#icon:checked { background: rgba(120,160,255,70); color: #ffffff; }
QPushButton#icon::menu-indicator { image: none; width: 0; }

QFrame#segment { background: rgba(0,0,0,60); border: 1px solid rgba(255,255,255,22);
                 border-radius: 9px; }
QPushButton#seg { background: transparent; border: none; border-radius: 7px; padding: 4px 12px;
                  color: rgba(230,236,255,150); font-weight: 600; }
QPushButton#seg:hover { color: #ffffff; }
QPushButton#seg:checked { color: #ffffff; border: 1px solid rgba(255,255,255,45);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(255,255,255,60),
                                stop:1 rgba(255,255,255,22)); }

QLineEdit, QPlainTextEdit {
    background: rgba(0,0,0,70); border: 1px solid rgba(255,255,255,30); border-radius: 9px;
    padding: 5px 9px; selection-background-color: rgba(110,150,255,150); }
QLineEdit:hover, QPlainTextEdit:hover { border-color: rgba(255,255,255,55); }
QLineEdit:focus, QPlainTextEdit:focus { border-color: rgba(130,170,255,200);
                                        background: rgba(0,0,0,95); }
QLineEdit#search { font-weight: 600; font-size: 8.5pt; padding-left: 7px; padding-right: 7px; }

QListWidget#sugg { background: rgba(0,0,0,85); border: 1px solid rgba(255,255,255,35);
                   border-radius: 10px; padding: 4px; outline: none; }
QListWidget#sugg::item { border-radius: 7px; color: rgba(225,232,255,125); padding-left: 6px; }
QListWidget#sugg::item:hover { background: rgba(255,255,255,20); }
QListWidget#sugg::item:selected { background: rgba(110,150,255,95); }
QLabel#suggName { font-weight: 700; font-size: 8pt; }
QLabel#suggInfo { color: rgba(225,232,255,125); font-size: 7pt; }
QLabel#suggWarn { color: #fbbf24; font-size: 7pt; }

QPushButton#action { border-radius: 11px; font-weight: 700; font-size: 9pt; padding: 7px 0; }
QPushButton#action[empty="true"] { background: rgba(255,255,255,10); color: rgba(225,232,255,110);
                                   border: 1px dashed rgba(255,255,255,50); font-weight: 600; }
QPushButton#action[empty="true"]:hover { background: rgba(255,255,255,26); color: #ffffff; }

QPushButton#primary, QPushButton#ghost, QPushButton#danger {
    border-radius: 9px; padding: 6px 16px; font-weight: 600; }
QPushButton#primary { border: 1px solid rgba(255,255,255,70);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(120,160,255,235),
                                stop:1 rgba(80,110,240,215)); }
QPushButton#primary:hover { background: rgba(130,170,255,245); }
QPushButton#ghost { background: rgba(255,255,255,18); border: 1px solid rgba(255,255,255,35); }
QPushButton#ghost:hover { background: rgba(255,255,255,34); }
QPushButton#danger { border: 1px solid rgba(255,255,255,60); background: rgba(225,45,75,210); }
QPushButton#danger:hover { background: rgba(240,60,90,235); }

QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,50); border-radius: 3px;
                              min-height: 24px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,90); }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
    height: 0; background: none; }

QMenu { background: #1b1e2c; border: 1px solid rgba(255,255,255,40); border-radius: 8px;
        padding: 5px; }
QMenu::item { padding: 6px 22px 6px 12px; border-radius: 5px; }
QMenu::item:selected { background: rgba(110,150,255,110); }
QMenu::item:disabled { color: rgba(225,232,255,70); }
QMenu::separator { height: 1px; background: rgba(255,255,255,30); margin: 4px 6px; }
"""


# ---------------------------------------------------------------- nền kính
class GlassMixin:
    """Nền "liquid glass": blur của Windows + lớp kính có ánh sáng, viền sáng mảnh."""
    RADIUS = 14

    def init_glass(self):
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._glass_ready = False

    def showEvent(self, e):
        if not self._glass_ready:
            self._glass_ready = True
            glass.enable_blur(self.winId())
        super().showEvent(e)

    def resizeEvent(self, e):
        if glass.NEEDS_MASK:  # Win10: blur phủ cả góc vuông nên phải cắt bo góc
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), self.RADIUS, self.RADIUS)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        super().resizeEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        shape = QPainterPath()
        shape.addRoundedRect(r, self.RADIUS, self.RADIUS)
        p.setClipPath(shape)

        tint = QLinearGradient(r.topLeft(), r.bottomRight())
        tint.setColorAt(0, QColor(38, 44, 78, 165 if glass.HAS_BLUR else 245))
        tint.setColorAt(1, QColor(14, 16, 30, 190 if glass.HAS_BLUR else 250))
        p.fillRect(r, tint)

        # Các vệt màu mờ tạo cảm giác chất lỏng phía sau kính
        for cx, cy, rad, color in ((0.0, 0.0, 0.9, QColor(99, 102, 241, 70)),
                                   (1.0, 0.25, 0.8, QColor(236, 72, 153, 45)),
                                   (0.2, 1.0, 0.9, QColor(34, 211, 238, 40))):
            g = QRadialGradient(r.left() + r.width() * cx, r.top() + r.height() * cy,
                                max(r.width(), r.height()) * rad)
            g.setColorAt(0, color)
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(r, g)

        # Ánh sáng phản chiếu ở nửa trên
        sheen = QLinearGradient(r.topLeft(), QPoint(int(r.left()), int(r.top() + 90)))
        sheen.setColorAt(0, QColor(255, 255, 255, 34))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, sheen)

        p.setClipping(False)
        border = QLinearGradient(r.topLeft(), r.bottomLeft())
        border.setColorAt(0, QColor(255, 255, 255, 95))
        border.setColorAt(0.5, QColor(255, 255, 255, 30))
        border.setColorAt(1, QColor(255, 255, 255, 50))
        p.setPen(QPen(QBrush(border), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(shape)


class GlassDialog(GlassMixin, QDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.init_glass()
        self.setWindowTitle(title)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 14, 18, 16)
        self.lay.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel(title, objectName='dlgTitle')
        head.addWidget(t)
        head.addStretch()
        head.addWidget(icon_button(I_CLOSE, 'Đóng (Esc)', self.reject, name='close'))
        self.lay.addLayout(head)

    def add_buttons(self, ok_text='Lưu', ok_style='primary'):
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 0)
        row.addStretch()
        cancel = QPushButton('Huỷ', objectName='ghost', cursor=Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok = QPushButton(ok_text, objectName=ok_style, cursor=Qt.PointingHandCursor)
        ok.setDefault(True)
        ok.clicked.connect(self.try_accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        self.lay.addLayout(row)

    def try_accept(self):
        self.accept()

    def field_label(self, text):
        lbl = QLabel(text, objectName='muted')
        self.lay.addWidget(lbl)
        return lbl

    def error(self, text):
        self.err.setText(text)
        self.err.setVisible(bool(text))

    def add_error(self):
        self.err = QLabel('', wordWrap=True)
        self.err.setStyleSheet('color: #ff8fa3;')
        self.err.hide()
        self.lay.addWidget(self.err)


# ---------------------------------------------------------------- widget nhỏ
def icon_button(glyph, tip, slot=None, name='icon', checkable=False):
    b = QPushButton(glyph, objectName='icon', cursor=Qt.PointingHandCursor)
    if name == 'close':
        b.setStyleSheet('QPushButton:hover { background: rgba(232,17,35,200); color: #fff; }')
    b.setFont(QFont(ICON_FONT, 9))
    b.setToolTip(tip)
    # Không để sizeHint của font icon làm các nút chiếm hết chiều
    # ngang khi cửa sổ chính ở chế độ hẹp 190 px.
    b.setFixedSize(26, 24)
    b.setCheckable(checkable)
    b.setFocusPolicy(Qt.NoFocus)
    if slot:
        b.clicked.connect(slot)
    return b


class ElidedLabel(QLabel):
    """Label 1 dòng, tự cắt '…' khi hẹp."""

    def __init__(self, text='', **kw):
        super().__init__(**kw)
        self.full = text
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(10)

    def setText(self, text):
        self.full = text
        self.setToolTip(text)
        self.update()

    def sizeHint(self):
        s = super().sizeHint()
        s.setHeight(self.fontMetrics().height() + 2)
        return s

    def paintEvent(self, _):
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        text = self.fontMetrics().elidedText(self.full, Qt.ElideRight, self.width())
        p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, text)




class SearchBox(QLineEdit):
    """Ô tìm giống ô Kênh ở tab Phân Kênh (Auto Prompt): bấm vào là hiện hết,
    gõ là lọc, lên/xuống để di chuyển, Enter chọn, Esc đóng."""
    opened = Signal()
    closed = Signal()
    nav = Signal(str)
    KEYS = {Qt.Key_Up: 'up', Qt.Key_Down: 'down', Qt.Key_Return: 'enter',
            Qt.Key_Enter: 'enter', Qt.Key_Escape: 'esc'}

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self.opened.emit()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.closed.emit()

    def keyPressEvent(self, e):
        key = self.KEYS.get(e.key())
        if key:
            self.nav.emit(key)
        else:
            super().keyPressEvent(e)


def sugg_row(item):
    """1 dòng gợi ý gọn: tên và ghi chú của niche."""
    w = QWidget()
    w.setAttribute(Qt.WA_TransparentForMouseEvents)
    lay = QHBoxLayout(w)
    lay.setContentsMargins(9, 0, 9, 0)
    lay.setSpacing(8)
    lay.addWidget(QLabel(item['key'], objectName='suggName'))
    lay.addWidget(ElidedLabel(item['note'], objectName='suggInfo'), 1)
    return w


def segmented(labels, on_click):
    """Nhóm nút gạt kiểu iOS. Trả về (khung, {key: nút})."""
    seg = QFrame(objectName='segment')
    lay = QHBoxLayout(seg)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)
    group = QButtonGroup(seg)
    buttons = {}
    for key, label in labels:
        b = QPushButton(label, objectName='seg', checkable=True, cursor=Qt.PointingHandCursor)
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(lambda _=False, k=key: on_click(k))
        group.addButton(b)
        buttons[key] = b
        lay.addWidget(b)
    return seg, buttons


class SaveButton(QPushButton):
    """Nút Lưu: đang lưu thì hiện vòng xoay, lưu xong hiện '✓ Đã lưu' một lúc."""

    def __init__(self):
        super().__init__('Lưu', objectName='primary', cursor=Qt.PointingHandCursor)
        self.angle = 0
        self.gen = 0
        self.spin = QTimer(self, interval=16, timeout=self.tick)
        self.setFixedWidth(self.fontMetrics().horizontalAdvance('Đang lưu') + 58)

    def tick(self):
        self.angle = (self.angle + 10) % 360
        self.update()

    def saving(self):
        self.gen += 1
        self.setText('     Đang lưu')
        self.spin.start()

    def saved(self):
        self.spin.stop()
        self.setText('✓ Đã lưu')
        gen = self.gen
        QTimer.singleShot(1500, lambda: gen == self.gen and self.setText('Lưu'))

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self.spin.isActive():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        d = 12
        r = QRectF(14, (self.height() - d) / 2, d, d)
        p.setPen(QPen(QColor(255, 255, 255, 70), 2))
        p.drawEllipse(r)
        p.setPen(QPen(QColor('#ffffff'), 2, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, -self.angle * 16, 100 * 16)


# ---------------------------------------------------------------- hộp thoại
class EntryEditor(GlassDialog):
    """Sửa tên, ghi chú và 3 prompt của 1 niche/kênh. Sửa gì cũng tự lưu sau ~0,6 giây;
    Huỷ = trả lại như lúc mở hộp."""
    KEYS = ('key', 'note') + tuple(f for f, *_ in ACTIONS)

    def __init__(self, parent, item, exists, on_save, versions, field='prom'):
        label = 'Default' if item['kind'] == 'default' else KIND_LABEL[item['kind']]
        super().__init__(parent, f'Sửa {label}')
        self.item, self.exists, self.on_save, self.versions = item, exists, on_save, versions
        self.snapshot = {k: item[k] for k in self.KEYS}
        self.resize(500, 470)
        self.timer = QTimer(self, singleShot=True, interval=SAVE_DELAY_MS, timeout=self.autosave)

        top = QHBoxLayout()
        name_box, note_box = QVBoxLayout(), QVBoxLayout()
        name_box.addWidget(QLabel('Tên', objectName='muted'))
        self.name = QLineEdit(item['key'])
        self.name.setReadOnly(item['kind'] == 'default')
        name_box.addWidget(self.name)
        note_box.addWidget(QLabel('Ghi chú', objectName='muted'))
        self.note = QLineEdit(item['note'], placeholderText='Không bắt buộc')
        note_box.addWidget(self.note)
        top.addLayout(name_box, 2)
        top.addLayout(note_box, 3)
        self.lay.addLayout(top)

        # Prom / Go / Img bên trái — Huỷ / Lưu góc phải, cùng 1 dòng
        row = QHBoxLayout()
        seg, self.tabs = segmented([(f, NAMES[f]) for f, *_ in ACTIONS], self.show_field)
        row.addWidget(seg)
        row.addStretch()
        hist = QPushButton('Lịch sử', objectName='ghost', cursor=Qt.PointingHandCursor)
        hist.setToolTip('Xem và khôi phục bản của các phiên sửa trước')
        hist.clicked.connect(self.open_history)
        row.addWidget(hist)
        cancel = QPushButton('Huỷ', objectName='ghost', cursor=Qt.PointingHandCursor)
        cancel.setToolTip('Bỏ mọi thay đổi, trả lại như lúc mở hộp này')
        cancel.clicked.connect(self.revert)
        self.save_btn = SaveButton()
        self.save_btn.setToolTip('Tự lưu khi sửa — bấm để lưu ngay và đóng')
        self.save_btn.clicked.connect(self.save_and_close)
        row.addWidget(cancel)
        row.addWidget(self.save_btn)
        self.lay.addSpacing(4)
        self.lay.addLayout(row)

        self.stack = QStackedWidget()
        self.texts = {}
        for f, *_ in ACTIONS:
            edit = QPlainTextEdit(item[f], placeholderText='Dán nội dung prompt vào đây…')
            edit.textChanged.connect(self.timer.start)
            self.texts[f] = edit
            self.stack.addWidget(edit)
        self.lay.addWidget(self.stack, 1)
        self.add_error()
        self.name.textChanged.connect(self.timer.start)
        self.note.textChanged.connect(self.timer.start)
        self.show_field(field)
        self.texts[field].setFocus()

    def show_field(self, field):
        self.tabs[field].setChecked(True)
        self.stack.setCurrentWidget(self.texts[field])

    def values(self):
        v = {'key': self.name.text().strip(), 'note': self.note.text().strip()}
        v.update({f: edit.toPlainText() for f, edit in self.texts.items()})
        return v

    def valid(self):
        name = self.name.text().strip()
        if not name:
            self.error('Nhập tên trước đã — chưa lưu.')
        elif name.upper() != self.item['key'].upper() and self.exists(name):
            self.error(f'"{name}" đã có rồi — chưa lưu.')
        else:
            self.error('')
            return True
        return False

    def autosave(self):
        """Lưu nếu có thay đổi hợp lệ. Trả về False nếu tên đang sai."""
        self.timer.stop()
        if not self.valid():
            return False
        v = self.values()
        if all(self.item[k] == v[k] for k in self.KEYS):
            return True
        self.item.update(v)
        self.save_btn.saving()
        self.on_save(self.item)
        QTimer.singleShot(500, self.save_btn.saved)   # để kịp thấy vòng xoay
        return True

    def save_and_close(self):
        if self.autosave():
            self.accept()

    def revert(self):
        self.timer.stop()
        if any(self.item[k] != self.snapshot[k] for k in self.KEYS):
            self.item.update(self.snapshot)
            self.on_save(self.item)
        super().reject()

    def open_history(self):
        self.autosave()
        dlg = HistoryDialog(self, self.versions(), self.values())
        if dlg.exec():
            vals = dlg.chosen()
            if self.item['kind'] != 'default':
                self.name.setText(vals.get('key', self.name.text()))
            self.note.setText(vals.get('note', ''))
            for f, edit in self.texts.items():
                edit.setPlainText(vals.get(f, ''))
            self.autosave()

    def reject(self):
        """Nút X / phím Esc: đóng, giữ những gì đã lưu (tên sai thì chưa lưu phần đó)."""
        self.autosave()
        super().reject()


class HistoryDialog(GlassDialog):
    """Danh sách các bản trước (mỗi lần đóng hộp Sửa có thay đổi = 1 bản). Chọn 1 bản để khôi phục."""

    def __init__(self, parent, versions, current):
        super().__init__(parent, 'Lịch sử sửa')
        self.resize(500, 440)
        self.versions = versions
        if not versions:
            self.lay.addWidget(QLabel('Chưa có bản cũ nào.\nMỗi lần sửa xong (đóng hộp Sửa), bản trước '
                                      'khi sửa sẽ được cất ở đây.', objectName='muted', wordWrap=True))
            self.resize(380, 0)
            self.add_buttons('Khôi phục')
            self.findChild(QPushButton, 'primary').hide()
            return
        self.field_label('Bản trước của mỗi phiên sửa — mới nhất ở trên')
        self.list = QListWidget(objectName='sugg')
        self.list.setFixedHeight(min(len(versions), 5) * ROW_H + 10)
        for v in versions:
            vals = v.get('values') or {}
            changed = [NAMES.get(k, 'Tên' if k == 'key' else 'Ghi chú')
                       for k in EntryEditor.KEYS if vals.get(k, '') != current.get(k, '')]
            it = QListWidgetItem(f"{v.get('time', '?')}   ·   khác bản hiện tại: "
                                 f"{', '.join(changed) if changed else 'không khác'}")
            it.setSizeHint(QSize(0, ROW_H))
            self.list.addItem(it)
        self.lay.addWidget(self.list)
        self.field_label('Nội dung bản đã chọn')
        self.preview = QPlainTextEdit(readOnly=True)
        self.lay.addWidget(self.preview, 1)
        self.list.currentRowChanged.connect(self.show_version)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.add_buttons('Khôi phục')
        self.list.setCurrentRow(0)

    def show_version(self, row):
        vals = self.versions[row].get('values') or {}
        parts = [f"Tên: {vals.get('key', '')}"]
        if vals.get('note'):
            parts.append(f"Ghi chú: {vals['note']}")
        for f, *_ in ACTIONS:
            parts.append(f"── {NAMES[f]} ──\n{vals.get(f, '').strip() or '(trống)'}")
        self.preview.setPlainText('\n\n'.join(parts))

    def chosen(self):
        return dict(self.versions[self.list.currentRow()].get('values') or {})


class NewEntryDialog(GlassDialog):
    def __init__(self, parent, kind, exists):
        super().__init__(parent, f'Thêm {KIND_LABEL[kind]} mới')
        self.exists = exists
        self.resize(360, 0)
        self.field_label(f'Tên {KIND_LABEL[kind].lower()}')
        self.name = QLineEdit(placeholderText='VD: GA200, SINGLE-MOM…')
        self.lay.addWidget(self.name)
        self.add_error()
        self.add_buttons('Tạo')
        self.name.setFocus()

    def try_accept(self):
        name = self.name.text().strip()
        if not name:
            self.error('Nhập tên trước đã.')
        elif self.exists(name):
            self.error(f'"{name}" đã có rồi.')
        else:
            self.accept()


class ConfirmDialog(GlassDialog):
    def __init__(self, parent, title, message, ok_text='Xoá', ok_style='danger'):
        super().__init__(parent, title)
        self.resize(340, 0)
        self.lay.addWidget(QLabel(message, wordWrap=True))
        self.add_buttons(ok_text, ok_style)


PRESET_COLORS = ['#ec4899', '#f43f5e', '#ef4444', '#f97316', '#f5b428', '#eab308',
                 '#84cc16', '#22c55e', '#10b981', '#14b8a6', '#22d3ee', '#0ea5e9',
                 '#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#d946ef', '#e5e7eb',
                 '#94a3b8', '#475569']


class ColorDialog(GlassDialog):
    """Chọn màu: bấm ô màu có sẵn hoặc điền mã màu (#rrggbb)."""

    def __init__(self, parent, label, color):
        super().__init__(parent, f'Màu nút {label}')
        self.resize(340, 0)
        self.color = color
        self.preview = QPushButton(label, objectName='action')
        self.preview.setProperty('empty', False)
        self.preview.setFocusPolicy(Qt.NoFocus)
        self.lay.addWidget(self.preview)

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, c in enumerate(PRESET_COLORS):
            b = QPushButton(cursor=Qt.PointingHandCursor)
            b.setFixedSize(26, 26)
            b.setToolTip(c)
            b.setFocusPolicy(Qt.NoFocus)
            b.setStyleSheet(f'QPushButton {{ background: {c}; border-radius: 13px;'
                            f' border: 1px solid rgba(255,255,255,70); }}'
                            f'QPushButton:hover {{ border: 2px solid #ffffff; }}')
            b.clicked.connect(lambda _=False, c=c: self.hex.setText(c))
            grid.addWidget(b, i // 10, i % 10)
        self.lay.addSpacing(4)
        self.lay.addLayout(grid)

        self.lay.addSpacing(4)
        self.field_label('Hoặc điền mã màu')
        self.hex = QLineEdit(color, placeholderText='#ec4899')
        self.hex.textChanged.connect(self.update_preview)
        self.lay.addWidget(self.hex)
        self.add_error()
        self.add_buttons('Chọn')
        self.update_preview(color)

    def parse(self, text):
        text = text.strip()
        if text and not text.startswith('#'):
            text = '#' + text
        return QColor(text).name() if QColor.isValidColorName(text) else None

    def update_preview(self, text):
        c = self.parse(text)
        if c:
            self.color = c
            self.preview.setStyleSheet(action_style(c))
            self.error('')

    def try_accept(self):
        if not self.parse(self.hex.text()):
            self.error('Mã màu không hợp lệ — vd #ec4899')
            return
        self.accept()


class SettingsDialog(GlassDialog):
    def __init__(self, parent, folder, colors, names):
        super().__init__(parent, 'Cài đặt')
        self.resize(480, 0)
        self.colors = dict(colors)
        self.field_label('Nút copy — bấm vào nút để đổi màu, sửa ô bên dưới để đổi tên')
        grid = QGridLayout()
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(6)
        self.swatches, self.names = {}, {}
        for col, (field, *_) in enumerate(ACTIONS):
            b = QPushButton(names[field], objectName='action', cursor=Qt.PointingHandCursor)
            b.setProperty('empty', False)
            b.clicked.connect(lambda _=False, f=field: self.pick_color(f))
            edit = QLineEdit(names[field], placeholderText=DEFAULT_NAMES[field], maxLength=12)
            edit.setAlignment(Qt.AlignCenter)
            edit.textChanged.connect(lambda t, bt=b, f=field: bt.setText(t.strip() or DEFAULT_NAMES[f]))
            self.swatches[field], self.names[field] = b, edit
            grid.addWidget(b, 0, col)
            grid.addWidget(edit, 1, col)
        reset = QPushButton('Mặc định', objectName='ghost', cursor=Qt.PointingHandCursor)
        reset.setToolTip('Trả lại tên và màu gốc')
        reset.clicked.connect(self.reset_colors)
        grid.addWidget(reset, 0, len(ACTIONS))
        self.lay.addLayout(grid)
        self.paint_swatches()
        self.lay.addSpacing(8)
        self.field_label(f'Thư mục dữ liệu (chứa {DATA_NAME} và {SETTINGS_NAME})')
        row = QHBoxLayout()
        self.path = QLineEdit(folder)
        btn = QPushButton('Chọn thư mục…', objectName='ghost', cursor=Qt.PointingHandCursor)
        btn.clicked.connect(self.pick)
        row.addWidget(self.path, 1)
        row.addWidget(btn)
        self.lay.addLayout(row)
        self.found = QLabel(objectName='muted', wordWrap=True)
        self.lay.addWidget(self.found)
        self.path.textChanged.connect(self.check_folder)
        self.check_folder(folder)
        self.add_error()
        self.add_buttons()

    def check_folder(self, folder):
        """Cho biết thư mục đã có sẵn file nào — có thì app dùng luôn, chưa có thì chép sang."""
        folder = folder.strip().strip('"')
        if not folder:
            self.found.setText('')
            return
        parts = []
        for name in (DATA_NAME, SETTINGS_NAME):
            has = os.path.isfile(os.path.join(folder, name))
            parts.append(f'✓ có {name} — dùng luôn' if has else f'• chưa có {name} — sẽ chép sang')
        self.found.setText('\n'.join(parts))

    def paint_swatches(self):
        for field, b in self.swatches.items():
            b.setStyleSheet(action_style(self.colors[field]))

    def pick_color(self, field):
        dlg = ColorDialog(self, self.swatches[field].text(), self.colors[field])
        if dlg.exec():
            self.colors[field] = dlg.color
            self.paint_swatches()

    def name_values(self):
        return {f: e.text().strip() or DEFAULT_NAMES[f] for f, e in self.names.items()}

    def reset_colors(self):
        self.colors = dict(DEFAULT_COLORS)
        for f, e in self.names.items():
            e.setText(DEFAULT_NAMES[f])
        self.paint_swatches()

    def pick(self):
        p = QFileDialog.getExistingDirectory(self, 'Chọn thư mục dữ liệu NotePrompt',
                                             self.value() or HOME_DIR)
        if p:
            self.path.setText(os.path.normpath(p))

    def try_accept(self):
        folder = self.value()
        if not folder:
            self.error('Chọn thư mục trước đã.')
            return
        data = os.path.join(folder, DATA_NAME)
        if os.path.isfile(data):
            try:
                store.load(data)
            except (OSError, ValueError) as e:
                self.error(f'{DATA_NAME} trong thư mục này không phải dữ liệu NotePrompt:\n{e}')
                return
        self.accept()

    def value(self):
        return self.path.text().strip().strip('"')


# ---------------------------------------------------------------- cửa sổ chính
class App(GlassMixin, QWidget):
    def __init__(self):
        super().__init__()
        self.init_glass()
        self.folder = find_folder()
        self.settings = load_settings(self.folder)
        self.migrate_settings()
        self.data = []
        self.current = None
        self.db_mtime = None

        self.setWindowTitle(APP_NAME)
        pos = self.settings.get('pos')
        if isinstance(pos, list) and len(pos) == 2:
            self.move(*pos)
        self.setFixedWidth(WIDTH)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(self.settings.get('topmost')))

        self.build_ui()
        # Giao diện rút gọn chỉ làm việc với Niche. Vẫn giữ hỗ trợ
        # dữ liệu channel trong file để không làm mất dữ liệu cũ.
        self.kind = 'niche'
        NAMES.update(self.names())
        self.load_db()

        self.timer = QTimer(self, interval=WATCH_MS, timeout=self.watch_file)
        self.timer.start()

    def migrate_settings(self):
        """Bản cũ lưu đường dẫn niches.json ở 'data_path' — giờ chỉ dùng để nhập dữ liệu."""
        s = self.settings
        if s.get('data_path') and not s.get('import_path'):
            s['import_path'] = s['data_path']
        for old in ('data_path', 'custom_dir', 'geometry', 'kind_filter', 'window', 'db_path'):
            s.pop(old, None)

    def db_path(self):
        return os.path.join(self.folder, DATA_NAME)

    def history_path(self):
        return os.path.join(self.folder, HISTORY_NAME)

    def versions(self, key):
        return store.load_history(self.history_path()).get(key, [])

    def push_history(self, old, new):
        """Cất bản trước phiên sửa (old) dưới tên mới của mục; đổi tên thì mang lịch sử theo."""
        path = self.history_path()
        hist = store.load_history(path)
        items = hist.pop(old['key'], [])
        items.insert(0, {'time': datetime.now().strftime('%d/%m/%Y %H:%M'), 'values': dict(old)})
        hist[new['key']] = items[:store.HISTORY_KEEP]
        try:
            store.save_history(path, hist)
        except OSError as e:
            self.set_status(f'Không lưu được lịch sử: {e}', path)

    # ---------- giao diện ----------
    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 7)
        root.setSpacing(7)

        # Thanh tiêu đề (kéo để di chuyển)
        bar = QHBoxLayout()
        bar.setSpacing(2)
        bar.addWidget(QLabel(APP_NAME, objectName='appName'))
        bar.addStretch()
        self.pin = icon_button(I_PIN, 'Luôn nổi trên cửa sổ khác', self.toggle_pin, checkable=True)
        self.pin.setChecked(bool(self.settings.get('topmost')))
        self.pin.setText(I_UNPIN if self.pin.isChecked() else I_PIN)
        bar.addWidget(self.pin)
        more = icon_button(I_MORE, 'Thêm')
        self.menu = QMenu(self)
        self.menu.aboutToShow.connect(self.fill_menu)
        more.setMenu(self.menu)
        bar.addWidget(more)
        bar.addWidget(icon_button(I_MIN, 'Thu nhỏ', self.showMinimized))
        bar.addWidget(icon_button(I_CLOSE, 'Đóng', self.close, name='close'))
        root.addLayout(bar)

        # Chọn Niche. Bỏ thanh Niche/Kênh để giao diện hẹp còn đủ chỗ.
        pick = QHBoxLayout()
        pick.setSpacing(3)
        self.search = SearchBox(objectName='search')
        self.search.setClearButtonEnabled(True)
        self.search.textEdited.connect(lambda _: self.show_sugg())
        self.search.textChanged.connect(self.on_search_changed)
        self.search.opened.connect(lambda: self.show_sugg(show_all=True))
        self.search.closed.connect(lambda: QTimer.singleShot(120, self.close_sugg_if_blur))
        self.search.nav.connect(self.on_nav)
        pick.addWidget(self.search, 1)
        self.edit_btn = icon_button(I_EDIT, 'Sửa prompt của niche này', lambda: self.edit_entry())
        self.add_btn = icon_button(I_ADD, 'Thêm niche mới', self.new_entry)
        for button in (self.edit_btn, self.add_btn):
            button.setFixedSize(22, 20)
            button.setFont(QFont(ICON_FONT, 8))
        root.addLayout(pick)

        self.sugg = QListWidget(objectName='sugg')
        self.sugg.setFocusPolicy(Qt.NoFocus)
        self.sugg.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sugg.itemClicked.connect(self.on_sugg_click)
        self.sugg.hide()
        root.addWidget(self.sugg)

        self.note = QLabel(objectName='muted', wordWrap=True)
        self.note.hide()
        root.addWidget(self.note)

        # Nút Prom / Go / Img
        acts = QHBoxLayout()
        acts.setSpacing(4)
        self.action_buttons = {}
        for field, label, _, _ in ACTIONS:
            b = QPushButton(label, objectName='action', cursor=Qt.PointingHandCursor)
            b.setProperty('empty', False)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, f=field, bt=b: self.on_action(f, bt))
            self.action_buttons[field] = b
            acts.addWidget(b)
        root.addLayout(acts)
        self.apply_colors()
        self.apply_names()

        self.status = ElidedLabel('', objectName='status')
        foot = QHBoxLayout()
        foot.setSpacing(3)
        foot.addWidget(self.status, 1)
        foot.addWidget(self.edit_btn)
        foot.addWidget(self.add_btn)
        root.addLayout(foot)

    def colors(self):
        saved = self.settings.get('colors') or {}
        return {f: saved.get(f) if QColor.isValidColorName(saved.get(f) or '') else c
                for f, c in DEFAULT_COLORS.items()}

    def apply_colors(self):
        for field, color in self.colors().items():
            self.action_buttons[field].setStyleSheet(action_style(color))

    def names(self):
        saved = self.settings.get('names') or {}
        return {f: str(saved.get(f) or '').strip() or n for f, n in DEFAULT_NAMES.items()}

    def apply_names(self):
        NAMES.update(self.names())
        if hasattr(self, 'items'):
            self.render_current()

    def fit_height(self):
        self.setFixedHeight(self.layout().sizeHint().height())

    def fill_menu(self):
        e = self.current
        self.menu.clear()
        self.menu.addAction('Nhập prompt từ file…', self.import_prompts)
        self.menu.addAction('Nạp lại dữ liệu', self.load_db)
        self.menu.addAction('Mở thư mục dữ liệu', self.open_db_dir)
        self.menu.addSeparator()
        act = self.menu.addAction('Xoá mục này…', self.delete_entry)
        act.setEnabled(bool(e and e['kind'] != 'default'))
        self.menu.addSeparator()
        self.menu.addAction('Cài đặt…', self.open_settings)

    def set_status(self, text, tip=''):
        self.status.setText(text)
        self.status.setToolTip(tip or text)

    # ---------- dữ liệu ----------
    def load_db(self):
        path = self.db_path()
        if not os.path.isfile(path):
            self.first_import(path)
            return
        try:
            self.data = store.load(path)
            self.db_mtime = prompts.mtime(path)
            self.set_status(f'{len(self.data)} mục  •  {os.path.basename(path)}', path)
        except (OSError, ValueError) as e:
            self.data = []
            self.set_status(f'Không đọc được file dữ liệu: {e}', path)
        self.fill_items()

    def first_import(self, path):
        """Tạo dữ liệu trống, không tự đọc nguồn prompt cạnh ứng dụng."""
        self.data = []
        self.save_db()
        self.set_status('Chưa có dữ liệu — bấm + hoặc chọn Nhập prompt từ file', path)
        self.fill_items()

    def import_prompts(self):
        """Chỉ nhập file người dùng chọn; nhớ đường dẫn trong cài đặt cục bộ."""
        source, _ = QFileDialog.getOpenFileName(
            self, 'Chọn file prompt của bạn',
            self.settings.get('import_path') or self.folder,
            'Dữ liệu JSON (*.json)')
        if not source:
            return
        try:
            with open(source, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            incoming = store.load(source) if isinstance(raw, dict) and isinstance(raw.get('items'), list) else store.from_niches(source)
            existing = {item['key'].casefold() for item in self.data}
            added = [item for item in incoming if item['key'].casefold() not in existing]
            if not added:
                self.set_status('Không có mục mới; các mục trùng tên được giữ nguyên', source)
                return
            previous = self.data
            self.data = previous + added
            if not self.save_db():
                self.data = previous
                return
            self.settings['import_path'] = source
            self.persist()
            self.fill_items()
            self.set_status(f'Đã nhập {len(added)} mục; giữ nguyên các mục trùng tên', source)
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as e:
            self.set_status(f'Không nhập được file: {e}', source)

    def save_db(self):
        path = self.db_path()
        try:
            store.save(path, self.data)
            self.db_mtime = prompts.mtime(path)
            return True
        except OSError as e:
            self.set_status(f'Không lưu được: {e}', path)
            return False

    def watch_file(self):
        """File dữ liệu bị sửa từ ngoài (vd Drive sync) thì nạp lại."""
        m = prompts.mtime(self.db_path())
        if m and self.db_mtime and m != self.db_mtime:
            self.load_db()

    def exists(self, name):
        return name.strip().upper() in {x['key'].upper() for x in self.data}

    # ---------- chọn niche/kênh ----------
    def options(self, kind):
        out = sorted((x for x in self.data if x['kind'] == kind), key=lambda x: x['key'].upper())
        return out + [x for x in self.data if x['kind'] == 'default']

    def set_kind(self, kind):
        self.kind = kind
        self.fill_items()

    def fill_items(self, select=None):
        """Nạp danh sách của tab đang chọn và chọn lại mục cũ (hoặc mục đầu)."""
        self.items = self.options(self.kind)
        want = select or self.settings.get(f'current_{self.kind}')
        hit = next((x for x in self.items if x['key'] == want), None)
        self.search.setPlaceholderText('Tìm niche…')
        self.pick(hit or (self.items[0] if self.items else None))

    # ----- Ô tìm: giống ô Kênh ở tab Phân Kênh -----
    def show_sugg(self, show_all=False):
        q = '' if show_all else self.search.text().strip().upper()
        hits = [x for x in self.items if q in f"{x['key']} {x['note']}".upper()]
        self.sugg.clear()
        for x in hits:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, x['key'])
            details = x['key'] + (f' — {x["note"]}' if x['note'] else '')
            it.setToolTip(details)
            it.setSizeHint(QSize(0, ROW_H))
            self.sugg.addItem(it)
            self.sugg.setItemWidget(it, sugg_row(x))
        if not hits:
            it = QListWidgetItem(f'Không có mục nào khớp “{self.search.text().strip()}”.')
            it.setFlags(Qt.NoItemFlags)
            it.setSizeHint(QSize(0, ROW_H))
            self.sugg.addItem(it)
        row = hits.index(self.current) if show_all and self.current in hits else 0
        self.sugg.setCurrentRow(row if hits else -1)
        self.sugg.setFixedHeight(min(max(len(hits), 1), SUGG_ROWS) * ROW_H + 10)
        self.sugg.show()
        if show_all:
            self.search.selectAll()
        self.fit_height()

    def on_search_changed(self, text):
        """Bấm nút xoá trong ô tìm → hiện lại toàn bộ danh sách."""
        if not text and self.search.hasFocus():
            self.show_sugg(show_all=True)

    def on_nav(self, key):
        n = self.sugg.count()
        if key == 'esc':
            self.close_sugg()
            self.search.clearFocus()
        elif not self.sugg.isVisible():
            self.show_sugg(show_all=True)
        elif key in ('up', 'down') and n:
            step = 1 if key == 'down' else -1
            self.sugg.setCurrentRow((self.sugg.currentRow() + step) % n)
        elif key == 'enter':
            self.on_sugg_click(self.sugg.currentItem())

    def on_sugg_click(self, it):
        key = it.data(Qt.UserRole) if it else None
        hit = next((x for x in self.items if x['key'] == key), None)
        if hit:
            self.pick(hit)

    def close_sugg_if_blur(self):
        if not self.search.hasFocus():
            self.close_sugg()

    def close_sugg(self):
        """Đóng gợi ý; chưa chọn gì thì ô tìm trả về tên mục đang làm."""
        self.sugg.hide()
        self.search.setText(self.current['key'] if self.current else '')
        self.search.setCursorPosition(0)
        self.fit_height()

    def pick(self, item):
        self.current = item
        if item:
            self.settings[f'current_{self.kind}'] = item['key']
        self.search.clearFocus()
        self.close_sugg()
        self.render_current()

    def render_current(self):
        e = self.current
        note = e['note'] if e else ''
        self.search.setToolTip(e['key'] if e else '')
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self.edit_btn.setEnabled(bool(e))
        for field, _, _, tip in ACTIONS:
            label = NAMES[field]
            b = self.action_buttons[field]
            has = bool(e and e[field].strip())
            b.setEnabled(bool(e))
            b.setText(label if has else f'+ {label}')
            b.setProperty('empty', not has)
            b.setToolTip(preview_tip(tip, e[field]) if has
                         else f'{label} chưa có nội dung — bấm để thêm')
            repolish(b)
        QTimer.singleShot(0, self.fit_height)

    # ---------- copy ----------
    def on_action(self, field, button):
        e = self.current
        if not e:
            return
        if not e[field].strip():
            self.edit_entry(field)
            return
        QApplication.clipboard().setText(e[field])
        flash(button)

    # ---------- thêm / sửa / xoá ----------
    def edit_entry(self, field='prom'):
        e = self.current
        if not e:
            return
        dlg = EntryEditor(self, e, self.exists, self.save_edit, lambda: self.versions(e['key']), field)
        dlg.exec()
        new = {k: e[k] for k in EntryEditor.KEYS}
        if new != dlg.snapshot:
            self.push_history(dlg.snapshot, new)

    def save_edit(self, item):
        """Hộp Sửa gọi mỗi lần tự lưu: ghi file và cập nhật cửa sổ chính ngay."""
        self.save_db()
        self.fill_items(select=item['key'])

    def new_entry(self):
        dlg = NewEntryDialog(self, self.kind, self.exists)
        if dlg.exec():
            item = {'key': dlg.name.text().strip(), 'kind': self.kind, 'note': '',
                    'prom': '', 'go': '', 'img': ''}
            self.data.append(item)
            self.save_db()
            self.fill_items(select=item['key'])
            self.edit_entry()

    def delete_entry(self):
        e = self.current
        if not e or e['kind'] == 'default':
            return
        label = KIND_LABEL[e['kind']].lower()
        dlg = ConfirmDialog(self, f'Xoá {label}',
                            f'Xoá {label} "{e["key"]}" cùng 3 prompt Prom / Go / Img của nó?')
        if dlg.exec():
            self.data = [x for x in self.data if x is not e]
            self.save_db()
            self.fill_items()

    # ---------- khác ----------
    def toggle_pin(self):
        on = self.pin.isChecked()
        self.pin.setText(I_UNPIN if on else I_PIN)
        self.settings['topmost'] = on
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self._glass_ready = False  # đổi cờ cửa sổ tạo lại handle nên phải bật lại blur
        self.show()

    def open_db_dir(self):
        folder = self.folder
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def open_settings(self):
        dlg = SettingsDialog(self, self.folder, self.colors(), self.names())
        if not dlg.exec():
            return
        folder = dlg.value()
        if not same_path(folder, self.folder):
            self.switch_folder(folder)
        self.settings['colors'] = {f: c for f, c in dlg.colors.items() if c != DEFAULT_COLORS[f]}
        self.settings['names'] = {f: n for f, n in dlg.name_values().items() if n != DEFAULT_NAMES[f]}
        self.apply_colors()
        self.apply_names()
        self.persist()

    def switch_folder(self, folder):
        """Chuyển sang thư mục khác: file nào đã có thì dùng luôn, chưa có thì chép bản hiện tại sang."""
        self.persist()
        try:
            os.makedirs(folder, exist_ok=True)
            if not os.path.isfile(os.path.join(folder, DATA_NAME)):
                store.save(os.path.join(folder, DATA_NAME), self.data)
            if os.path.isfile(os.path.join(folder, SETTINGS_NAME)):
                self.settings = load_settings(folder)
                self.migrate_settings()
            else:
                save_settings(folder, self.settings)
            remember_folder(folder)
        except OSError as e:
            self.set_status(f'Không dùng được thư mục này: {e}', folder)
            return
        self.folder = folder
        on = bool(self.settings.get('topmost'))
        if on != self.pin.isChecked():
            self.pin.setChecked(on)
            self.toggle_pin()
        self.kind = 'niche'
        self.load_db()

    def persist(self):
        self.settings['pos'] = [self.x(), self.y()]
        self.settings['kind'] = self.kind
        try:
            save_settings(self.folder, self.settings)
        except OSError:
            pass

    def closeEvent(self, e):
        self.persist()
        super().closeEvent(e)


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    if sys.platform == 'win32':
        # Để taskbar dùng icon của NotePrompt thay vì icon mặc định của Python
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('NotePrompt.App')
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(resource(os.path.join('assets', 'icon.ico'))))
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    w = App()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
