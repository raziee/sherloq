"""Pure image-processing helpers without Qt dependencies."""

import sys

import cv2 as cv
import numpy as np

from gui.sherloq_app.paths import BUTTERAUGLI_DIR, PYEXIFTOOL_DIR, SSIMULACRA_DIR


def human_size(total, binary=False, suffix="B"):
    units = ["", "K", "M", "G", "T", "P", "E", "Z", "Y"]
    if binary:
        units = [unit + "i" for unit in units]
        factor = 1024.0
    else:
        factor = 1000.0
    for unit in units:
        if abs(total) < factor:
            return f"{total:3.1f} {unit}{suffix}"
        total /= factor
    return f"{total:.1f} {units[-1]}{suffix}"


def create_lut(low, high):
    if low >= 0:
        p1 = (+low, 0)
    else:
        p1 = (0, -low)
    if high >= 0:
        p2 = (255 - high, 255)
    else:
        p2 = (255, 255 + high)
    if p1[0] == p2[0]:
        return np.full(256, 255, np.uint8)
    lut = [
        (x * (p1[1] - p2[1]) + p1[0] * p2[1] - p1[1] * p2[0]) / (p1[0] - p2[0])
        for x in range(256)
    ]
    return np.clip(np.array(lut), 0, 255).astype(np.uint8)


def compute_hist(image, normalize=False):
    hist = np.array(
        [h[0] for h in cv.calcHist([image], [0], None, [256], [0, 256])], int
    )
    return hist / image.size if normalize else hist


def equalize_img(image):
    return cv.merge([cv.equalizeHist(channel) for channel in cv.split(image)])


def norm_img(image):
    return cv.merge([norm_mat(channel) for channel in cv.split(image)])


def norm_mat(matrix, to_bgr=False):
    norm = cv.normalize(matrix, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)
    if not to_bgr:
        return norm
    return cv.cvtColor(norm, cv.COLOR_GRAY2BGR)


def desaturate(image):
    return cv.cvtColor(cv.cvtColor(image, cv.COLOR_BGR2GRAY), cv.COLOR_GRAY2BGR)


def pad_image(image, bsize, reflect=False):
    rows, cols = image.shape[:2]
    top = left = 0
    bottom = bsize - rows % bsize
    right = bsize - cols % bsize
    border = cv.BORDER_CONSTANT if not reflect else cv.BORDER_REFLECT_101
    return cv.copyMakeBorder(image, top, bottom, left, right, border)


def gray_to_bgr(image):
    return cv.cvtColor(image, cv.COLOR_GRAY2BGR)


def exiftool_exe():
    if sys.platform.startswith("linux"):
        return str(PYEXIFTOOL_DIR / "exiftool" / "linux" / "exiftool")
    if sys.platform.startswith("win32"):
        return str(PYEXIFTOOL_DIR / "exiftool" / "windows" / "exiftool(-k).exe")
    if sys.platform.startswith("darwin"):
        return str(PYEXIFTOOL_DIR / "exiftool" / "linux" / "exiftool")
    return None


def butter_exe():
    if sys.platform.startswith("linux"):
        return str(BUTTERAUGLI_DIR / "linux" / "butteraugli")
    return None


def ssimul_exe():
    if sys.platform.startswith("linux"):
        return str(SSIMULACRA_DIR / "linux" / "ssimulacra")
    return None
