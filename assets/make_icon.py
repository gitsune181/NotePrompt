"""Vẽ icon NotePrompt (assets/icon.ico + icon.png). Chạy lại khi muốn đổi icon:

    .venv\\Scripts\\python.exe assets\\make_icon.py
"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPainterPathStroker, QPen)

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw(size):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    m = s * 0.04
    r = QRectF(m, m, s - 2 * m, s - 2 * m)
    shape = QPainterPath()
    shape.addRoundedRect(r, s * 0.24, s * 0.24)

    bg = QLinearGradient(r.topLeft(), r.bottomRight())
    bg.setColorAt(0, QColor('#6d7cff'))
    bg.setColorAt(0.55, QColor('#9b5cf6'))
    bg.setColorAt(1, QColor('#ec4899'))
    p.fillPath(shape, bg)

    # ánh kính nửa trên
    p.setClipPath(shape)
    sheen = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + r.height() * 0.55))
    sheen.setColorAt(0, QColor(255, 255, 255, 110))
    sheen.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(r, sheen)
    p.setClipping(False)
    if size >= 32:
        p.setPen(QPen(QColor(255, 255, 255, 90), max(1.0, s / 64)))
        p.drawPath(shape)

    draw_x(p, s)
    p.end()
    return img


def draw_x(p, s):
    """Chữ X cách điệu: 2 dải cong đan chéo, dải dưới luồn qua dải trên."""
    w = s * 0.14
    # dải dưới: từ dưới-trái lên trên-phải, trắng ngả hồng
    under = QPainterPath(QPointF(s * 0.29, s * 0.73))
    under.cubicTo(QPointF(s * 0.45, s * 0.60), QPointF(s * 0.55, s * 0.40), QPointF(s * 0.71, s * 0.27))
    g = QLinearGradient(QPointF(s * 0.29, s * 0.73), QPointF(s * 0.71, s * 0.27))
    g.setColorAt(0, QColor('#ffd6ee'))
    g.setColorAt(1, QColor('#ffffff'))
    p.setPen(QPen(QBrush(g), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(under)

    # dải trên: từ trên-trái xuống dưới-phải, cong ngược chiều
    over = QPainterPath(QPointF(s * 0.29, s * 0.27))
    over.cubicTo(QPointF(s * 0.45, s * 0.40), QPointF(s * 0.55, s * 0.60), QPointF(s * 0.71, s * 0.73))
    if s >= 32:  # bóng mềm của dải trên đổ lên dải dưới cho ra dáng đan ruy băng
        p.save()
        stroker = QPainterPathStroker()
        stroker.setWidth(w)
        stroker.setCapStyle(Qt.RoundCap)
        p.setClipPath(stroker.createStroke(under))   # bóng chỉ nằm trên dải dưới
        for extra, alpha in ((0.08, 40), (0.05, 60), (0.025, 80)):
            p.setPen(QPen(QColor(70, 30, 150, alpha), w + s * extra, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(over)
        p.restore()
    p.setPen(QPen(QColor('#ffffff'), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(over)


def png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, 'PNG')
    return bytes(ba)


def write_ico(path, images):
    """File .ico nhiều kích thước, mỗi ảnh nhúng dạng PNG (Windows Vista trở lên đọc được)."""
    blobs = [png_bytes(im) for im in images]
    out = struct.pack('<HHH', 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    for im, b in zip(images, blobs):
        w = im.width() if im.width() < 256 else 0
        out += struct.pack('<BBBBHHII', w, w, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
    with open(path, 'wb') as f:
        f.write(out + b''.join(blobs))


if __name__ == '__main__':
    app = QGuiApplication(sys.argv)
    images = [draw(n) for n in SIZES]
    write_ico(os.path.join(HERE, 'icon.ico'), images)
    images[-1].save(os.path.join(HERE, 'icon.png'))
    print('Xong: assets/icon.ico, assets/icon.png')
