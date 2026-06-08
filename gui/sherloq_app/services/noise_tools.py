import cv2 as cv
import numpy as np
import pywt

from gui.sherloq_app.core.headless import create_lut, equalize_img, norm_mat
from gui.sherloq_app.services.results import ServiceResult

CHANNEL_MAP = {
    "luminance": 0,
    "red": 1,
    "green": 2,
    "blue": 3,
    "rgb_norm": 4,
}


def _select_channel(image, channel: str):
    index = CHANNEL_MAP.get(channel, 0)
    if index == 0:
        return cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    if index == 4:
        b, g, r = cv.split(image.astype(np.float64))
        return cv.sqrt(cv.pow(b, 2) + cv.pow(g, 2) + cv.pow(r, 2)).astype(np.uint8)
    return image[:, :, 4 - index]


def noise_separation(
    image,
    mode: str = "median",
    radius: int = 1,
    sigma: int = 3,
    levels: int = 32,
    grayscale: bool = False,
    show_denoised: bool = False,
) -> ServiceResult:
    original = cv.cvtColor(image, cv.COLOR_BGR2GRAY) if grayscale else image
    kernel = radius * 2 + 1
    if mode == "median":
        denoised = cv.medianBlur(original, kernel)
    elif mode == "gaussian":
        denoised = cv.GaussianBlur(original, (kernel, kernel), 0)
    elif mode == "box":
        denoised = cv.blur(original, (kernel, kernel))
    elif mode == "bilateral":
        denoised = cv.bilateralFilter(original, kernel, sigma, sigma)
    else:
        if grayscale:
            denoised = cv.fastNlMeansDenoising(original, None, kernel)
        else:
            denoised = cv.fastNlMeansDenoisingColored(original, None, kernel, kernel)
    if show_denoised:
        result = denoised
    else:
        noise = cv.absdiff(original, denoised)
        if levels == 0:
            result = cv.equalizeHist(noise) if grayscale else equalize_img(noise)
        else:
            result = cv.LUT(noise, create_lut(0, 255 - levels))
    if grayscale:
        result = cv.cvtColor(result, cv.COLOR_GRAY2BGR)
    return ServiceResult(
        data={"mode": mode, "radius": radius, "sigma": sigma, "levels": levels, "grayscale": grayscale},
        images={"result": result},
    )


def minmax_deviation(
    image,
    channel: str = "luminance",
    minimum_color: str = "green",
    maximum_color: str = "red",
    filter_radius: int = 0,
) -> ServiceResult:
    img = _select_channel(image, channel)
    kernel = 3
    border = kernel // 2
    shape = (img.shape[0] - kernel + 1, img.shape[1] - kernel + 1, kernel, kernel)
    strides = 2 * img.strides
    patches = np.lib.stride_tricks.as_strided(img, shape=shape, strides=strides)
    patches = patches.reshape((-1, kernel, kernel))
    mask = np.full((kernel, kernel), 255, dtype=np.uint8)
    mask[border, border] = 0
    blocks = []
    for patch in patches:
        center = patch[1, 1]
        minimum, maximum, _, _ = cv.minMaxLoc(patch, mask)
        if center < minimum:
            blocks.append(-1)
        elif center > maximum:
            blocks.append(1)
        else:
            blocks.append(0)
    output = np.array(blocks).reshape(shape[:-2])
    output = cv.copyMakeBorder(output, border, border, border, border, cv.BORDER_CONSTANT)
    low = output == -1
    high = output == 1
    color_lookup = {
        "red": [0, 0, 255],
        "green": [0, 255, 0],
        "blue": [255, 0, 0],
        "white": [255, 255, 255],
        "black": [0, 0, 0],
    }
    minmax = np.zeros_like(image)
    if filter_radius > 0:
        radius = filter_radius + 3

        def block_filter(binary):
            result = np.zeros_like(binary, np.float32)
            rows, cols = result.shape
            block = 2 * radius + 1
            for i in range(radius, rows, block):
                for j in range(radius, cols, block):
                    patch = binary[i - radius : i + radius + 1, j - radius : j + radius + 1]
                    result[i - radius : i + radius + 1, j - radius : j + radius + 1] = np.std(patch)
            return cv.normalize(result, None, 0, 127, cv.NORM_MINMAX, cv.CV_8UC1)

        if minimum_color != "black":
            low_map = block_filter(low)
            channel_index = {"red": 2, "green": 1, "blue": 0, "white": None}[minimum_color]
            if channel_index is None:
                minmax = np.repeat(low_map[:, :, np.newaxis], 3, axis=2)
            else:
                minmax[:, :, channel_index] = low_map
        if maximum_color != "black":
            high_map = block_filter(high)
            channel_index = {"red": 2, "green": 1, "blue": 0, "white": None}[maximum_color]
            if channel_index is None:
                minmax += np.repeat(high_map[:, :, np.newaxis], 3, axis=2)
            else:
                minmax[:, :, channel_index] += high_map
        minmax = norm_mat(minmax)
    else:
        minmax[low] = color_lookup[minimum_color]
        minmax[high] = color_lookup[maximum_color]
    return ServiceResult(
        data={"channel": channel, "minimum_color": minimum_color, "maximum_color": maximum_color},
        images={"deviation": minmax},
    )


def bit_planes(image, channel: str = "luminance", plane: int = 0, filter_mode: str = "disabled") -> ServiceResult:
    img = _select_channel(image, channel)
    planes = [
        norm_mat(cv.bitwise_and(np.full_like(img, 2 ** bit), img), to_bgr=True) for bit in range(8)
    ]
    selected = planes[plane]
    if filter_mode == "median":
        selected = cv.medianBlur(selected, 3)
    elif filter_mode == "gaussian":
        selected = cv.GaussianBlur(selected, (3, 3), 0)
    return ServiceResult(
        data={"channel": channel, "plane": plane, "filter_mode": filter_mode},
        images={"plane": selected, **{f"bit_{i}": planes[i] for i in range(8)}},
    )


def wavelet_blocking(file_path: str, image, blocksize: int = 8) -> ServiceResult:
    gray = cv.imread(file_path, cv.IMREAD_GRAYSCALE)
    if gray is None:
        gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    signal = np.double(gray)
    _, (_, _, detail) = pywt.dwt2(signal, "db8")
    detail = detail[: detail.shape[0] // blocksize * blocksize, : detail.shape[1] // blocksize * blocksize]
    block = np.zeros((detail.shape[0] // blocksize, detail.shape[1] // blocksize, blocksize ** 2))
    for row in range(0, detail.shape[0] - blocksize + 1, blocksize):
        for col in range(0, detail.shape[1] - blocksize + 1, blocksize):
            block_elements = detail[row : row + blocksize, col : col + blocksize]
            block[row // blocksize, col // blocksize, :] = block_elements.flatten()
    noise_map = np.median(np.abs(block), axis=2) / 0.6745
    noise_map_8u = cv.normalize(noise_map, None, 0, 255, cv.NORM_MINMAX, dtype=cv.CV_8U)
    resized = cv.resize(noise_map_8u, (image.shape[1], image.shape[0]), interpolation=cv.INTER_NEAREST)
    return ServiceResult(
        data={"blocksize": blocksize},
        images={"noise_map": cv.cvtColor(resized, cv.COLOR_GRAY2BGR)},
    )
