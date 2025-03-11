import ctypes
from ctypes import wintypes
from PIL import Image

def get_file_icon(file_path):
    SHGFI_ICON = 0x100
    SHGFI_LARGEICON = 0x0  # Large icon
    SHGFI_SMALLICON = 0x1  # Small icon

    # Initialize the SHFILEINFO structure
    class SHFILEINFO(ctypes.Structure):
        _fields_ = [
            ("hIcon", ctypes.wintypes.HICON),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", ctypes.c_ulong),
            ("szDisplayName", ctypes.c_char * 260),
            ("szTypeName", ctypes.c_char * 80),
        ]

    shfileinfo = SHFILEINFO()
    ctypes.windll.shell32.SHGetFileInfoW(file_path, 0, ctypes.byref(shfileinfo), ctypes.sizeof(shfileinfo), SHGFI_ICON | SHGFI_LARGEICON)

    hIcon = shfileinfo.hIcon

    # Get the icon bitmap
    hdc = ctypes.windll.user32.GetDC(None)
    hdc_compat = ctypes.windll.gdi32.CreateCompatibleDC(hdc)
    hbitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc, 32, 32)
    old_hbitmap = ctypes.windll.gdi32.SelectObject(hdc_compat, hbitmap)
    ctypes.windll.user32.DrawIconEx(hdc_compat, 0, 0, hIcon, 32, 32, 0, None, 0x3)
    ctypes.windll.gdi32.SelectObject(hdc_compat, old_hbitmap)
    ctypes.windll.gdi32.DeleteDC(hdc_compat)

    # Create a BITMAPINFO structure
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
            ("bmiColors", ctypes.c_uint32 * 3),
        ]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = 32
    bmi.bmiHeader.biHeight = -32  # Negative to create a top-down DIB
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB
    bmi.bmiHeader.biSizeImage = 0

    bmp_bits = ctypes.create_string_buffer(32 * 32 * 4)
    ctypes.windll.gdi32.GetDIBits(hdc, hbitmap, 0, 32, bmp_bits, ctypes.byref(bmi), 0)

    # Convert the bitmap to a PIL Image
    image = Image.frombuffer("RGBA", (32, 32), bmp_bits, "raw", "BGRA", 0, 1)

    # Clean up
    ctypes.windll.gdi32.DeleteObject(hbitmap)
    ctypes.windll.user32.ReleaseDC(None, hdc)
    ctypes.windll.user32.DestroyIcon(hIcon)

    return image

# Example usage
file_path = "C:\\Windows\\System32\\oobe\\UserOOBEBroker.exe"
icon_image = get_file_icon(file_path)
icon_image.save("windows_icon.png")
