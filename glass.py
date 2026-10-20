"""Hiệu ứng kính mờ (blur nền phía sau cửa sổ) trên Windows 10/11.

Dùng SetWindowCompositionAttribute (ACCENT_ENABLE_BLURBEHIND) — không lag khi kéo
cửa sổ như Acrylic trên Win10. Máy khác / lỗi thì app vẫn chạy với nền đặc.
"""
import ctypes
import sys

HAS_BLUR = sys.platform == 'win32'
# Win11 tự bo góc cửa sổ; Win10 phải tự cắt góc để blur không lộ ra ngoài.
NEEDS_MASK = HAS_BLUR and sys.getwindowsversion().build < 22000

ACCENT_ENABLE_BLURBEHIND = 3
WCA_ACCENT_POLICY = 19
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


class _AccentPolicy(ctypes.Structure):
    _fields_ = [('AccentState', ctypes.c_int), ('AccentFlags', ctypes.c_int),
                ('GradientColor', ctypes.c_uint), ('AnimationId', ctypes.c_int)]


class _CompositionData(ctypes.Structure):
    _fields_ = [('Attribute', ctypes.c_int), ('Data', ctypes.c_void_p),
                ('SizeOfData', ctypes.c_size_t)]


def enable_blur(win_id):
    global HAS_BLUR
    if not HAS_BLUR:
        return
    hwnd = ctypes.c_void_p(int(win_id))
    try:
        accent = _AccentPolicy(ACCENT_ENABLE_BLURBEHIND, 0, 0, 0)
        data = _CompositionData(WCA_ACCENT_POLICY, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p),
                                ctypes.sizeof(accent))
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(_CompositionData)]
        if not fn(hwnd, ctypes.byref(data)):
            HAS_BLUR = False
    except (AttributeError, OSError):
        HAS_BLUR = False
        return
    if not NEEDS_MASK:
        try:
            pref = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                                       ctypes.byref(pref), ctypes.sizeof(pref))
        except (AttributeError, OSError):
            pass
