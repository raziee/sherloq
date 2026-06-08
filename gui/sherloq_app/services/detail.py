from copy import deepcopy

import cv2 as cv
import numpy as np
import pywt

from gui.sherloq_app.core.headless import create_lut, equalize_img, norm_mat
from gui.sherloq_app.services.results import ServiceResult

WAVELET_FAMILIES = {
    "daubechies": [f"db{i}" for i in range(1, 21)],
    "symlets": [f"sym{i}" for i in range(2, 21)],
    "coiflets": [f"coif{i}" for i in range(1, 6)],
    "biorthogonal": [
        "bior1.1",
        "bior1.3",
        "bior1.5",
        "bior2.2",
        "bior2.4",
        "bior2.6",
        "bior2.8",
        "bior3.1",
        "bior3.3",
        "bior3.5",
        "bior3.7",
        "bior3.9",
        "bior4.4",
        "bior5.5",
        "bior6.8",
    ],
}


def luminance_gradient(
    image,
    intensity: int = 95,
    blue_mode: str = "abs",
    invert: bool = False,
    equalize: bool = False,
) -> ServiceResult:
    dx, dy = cv.spatialGradient(cv.cvtColor(image, cv.COLOR_BGR2GRAY))
    if invert:
        dx = (-dx).astype(np.float32)
        dy = (-dy).astype(np.float32)
    else:
        dx = dx.astype(np.float32)
        dy = dy.astype(np.float32)
    dx_abs = np.abs(dx)
    dy_abs = np.abs(dy)
    red = ((dx / np.max(dx_abs) * 127) + 127).astype(np.uint8)
    green = ((dy / np.max(dy_abs) * 127) + 127).astype(np.uint8)
    if blue_mode == "none":
        blue = np.zeros_like(red)
    elif blue_mode == "flat":
        blue = np.full_like(red, 255)
    elif blue_mode == "abs":
        blue = norm_mat(dx_abs + dy_abs)
    else:
        blue = norm_mat(np.linalg.norm(cv.merge((red, green)), axis=2))
    gradient = cv.merge([blue, green, red])
    if equalize:
        gradient = equalize_img(gradient)
    else:
        tone = int(intensity / 100 * 127)
        if tone > 0:
            gradient = cv.LUT(gradient, create_lut(tone, tone))
    return ServiceResult(
        data={"intensity": intensity, "blue_mode": blue_mode, "invert": invert, "equalize": equalize},
        images={"gradient": gradient},
    )


def echo_edge(image, radius: int = 2, contrast: int = 85, grayscale: bool = False) -> ServiceResult:
    kernel = 2 * radius + 1
    contrast_value = int(contrast / 100 * 255)
    lut = create_lut(0, contrast_value)
    laplace = []
    for channel in cv.split(image):
        deriv = np.fabs(cv.Laplacian(channel, cv.CV_64F, None, kernel))
        deriv = cv.normalize(deriv, None, 0, 255, cv.NORM_MINMAX, cv.CV_8UC1)
        laplace.append(cv.LUT(deriv, lut))
    result = cv.merge(laplace)
    if grayscale:
        result = cv.cvtColor(cv.cvtColor(result, cv.COLOR_BGR2GRAY), cv.COLOR_GRAY2BGR)
    return ServiceResult(
        data={"radius": radius, "contrast": contrast, "grayscale": grayscale},
        images={"echo": result},
    )


def wavelet_threshold(
    image,
    family: str = "daubechies",
    wavelet: str = "db4",
    threshold: int = 0,
    mode: str = "soft",
    level: int | None = None,
) -> ServiceResult:
    if wavelet not in WAVELET_FAMILIES.get(family, []):
        wavelet = WAVELET_FAMILIES[family][0]
    max_level = pywt.dwtn_max_level(image.shape[:-1], wavelet)
    level = level or max(max_level // 2, 1)
    level = min(max(level, 1), max_level)
    coeffs = pywt.wavedec2(image[:, :, 0], wavelet)
    if threshold > 0:
        working = deepcopy(coeffs)
        threshold_value = threshold / 100
        threshold_mode = mode.lower()
        for i in range(1, level + 1):
            octave = []
            for plane in working[-i]:
                t = threshold_value * np.max(np.abs(plane))
                octave.append(pywt.threshold(plane, t, threshold_mode))
            working[-i] = tuple(octave)
        coeffs = working
    reconstructed = cv.cvtColor(pywt.waverec2(coeffs, wavelet).astype(np.uint8), cv.COLOR_GRAY2BGR)
    return ServiceResult(
        data={
            "family": family,
            "wavelet": wavelet,
            "threshold_percent": threshold,
            "mode": mode,
            "level": level,
        },
        images={"reconstructed": reconstructed},
    )


def frequency_split(
    image,
    separation: int = 15,
    smooth: int = 25,
    threshold: int = 0,
    filter_radius: int = 0,
) -> ServiceResult:
    rows0, cols0 = image.shape[:2]
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    rows, cols = gray.shape
    height = cv.getOptimalDFTSize(rows)
    width = cv.getOptimalDFTSize(cols)
    padded = cv.copyMakeBorder(gray, 0, height - rows, 0, width - cols, cv.BORDER_CONSTANT)
    dft = np.fft.fftshift(cv.dft(padded.astype(np.float32), flags=cv.DFT_COMPLEX_OUTPUT))
    magnitude0, phase0 = cv.cartToPolar(dft[:, :, 0], dft[:, :, 1])
    magnitude0 = cv.normalize(cv.log(magnitude0), None, 0, 255, cv.NORM_MINMAX)
    phase0 = cv.normalize(phase0, None, 0, 255, cv.NORM_MINMAX)

    mask = np.zeros((rows, cols), np.float32)
    half = np.sqrt(rows ** 2 + cols ** 2) / 2
    radius = int(half * separation / 100)
    mask = cv.circle(mask, (cols // 2, rows // 2), radius, 1, cv.FILLED)
    kernel = 2 * int(half * smooth / 100) + 1
    mask = cv.GaussianBlur(mask, (kernel, kernel), 0)
    mask /= np.max(mask)
    threshold_value = int(threshold / 100 * 255)
    if threshold_value > 0:
        mask[magnitude0 < threshold_value] = 0
        zeros = (mask.size - np.count_nonzero(mask)) / mask.size * 100
    else:
        zeros = 0.0
    mask2 = np.repeat(mask[:, :, np.newaxis], 2, axis=2)

    low = cv.idft(np.fft.ifftshift(dft * mask2), flags=cv.DFT_SCALE)
    low = norm_mat(cv.magnitude(low[:, :, 0], low[:, :, 1])[:rows0, :cols0], to_bgr=True)
    high = cv.idft(np.fft.ifftshift(dft * (1 - mask2)), flags=cv.DFT_SCALE)
    high = norm_mat(cv.magnitude(high[:, :, 0], high[:, :, 1]), to_bgr=True)
    high = np.copy(high[:rows0, :cols0])
    magnitude = (magnitude0 * mask).astype(np.uint8)
    phase = (phase0 * mask).astype(np.uint8)
    blur_kernel = 2 * filter_radius + 1
    if blur_kernel >= 3:
        magnitude = cv.GaussianBlur(magnitude, (blur_kernel, blur_kernel), 0)
        phase = cv.GaussianBlur(phase, (blur_kernel, blur_kernel), 0)
    return ServiceResult(
        data={
            "separation_percent": separation,
            "smooth_percent": smooth,
            "threshold_percent": threshold,
            "zeroed_coefficients_percent": zeros,
            "filter_radius": filter_radius,
        },
        images={
            "low_frequency": low,
            "high_frequency": high,
            "dft_magnitude": cv.cvtColor(magnitude, cv.COLOR_GRAY2BGR),
            "dft_phase": cv.cvtColor(phase, cv.COLOR_GRAY2BGR),
        },
    )
