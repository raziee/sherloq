import cv2 as cv
import numpy as np

from gui.sherloq_app.core.headless import equalize_img, norm_img, norm_mat
from gui.sherloq_app.services.results import ServiceResult


def space_conversion(image, space: str = "hsv", channel: str = "hue") -> ServiceResult:
    rows, cols = image.shape[:2]
    scaled = image.astype(np.float32) / 255
    spaces = {
        "rgb": cv.cvtColor(image, cv.COLOR_BGR2RGB),
        "ycrcb": cv.cvtColor(image, cv.COLOR_BGR2YCrCb),
        "xyz": cv.cvtColor(image, cv.COLOR_BGR2XYZ),
        "lab": cv.cvtColor(image, cv.COLOR_BGR2Lab),
        "luv": cv.cvtColor(image, cv.COLOR_BGR2Luv),
    }
    gray = np.zeros((rows, cols, 4), dtype=np.uint8)
    gray[:, :, 0] = ((np.amax(scaled, axis=2) + np.amin(scaled, axis=2)) / 2 * 255).astype(np.uint8)
    gray[:, :, 1] = ((0.21 * scaled[:, :, 2] + 0.72 * scaled[:, :, 1] + 0.07 * scaled[:, :, 0]) * 255).astype(np.uint8)
    gray[:, :, 2] = (np.mean(scaled, axis=2) * 255).astype(np.uint8)
    gray[:, :, 3] = cv.cvtColor(scaled, cv.COLOR_BGR2GRAY) * 255
    hsv = cv.cvtColor(scaled, cv.COLOR_BGR2HSV) * 255
    hsv[:, :, 0] /= 360
    hsv = hsv.astype(np.uint8)
    hls = cv.cvtColor(scaled, cv.COLOR_BGR2HLS) * 255
    hls[:, :, 0] /= 360
    hls = hls.astype(np.uint8)
    cmyk = np.zeros((rows, cols, 4))
    k = np.repeat(np.amin(1 - scaled, axis=2)[:, :, np.newaxis], repeats=3, axis=2)
    k[k == 1] = 1 - np.finfo(np.float32).eps
    cmyk[:, :, :-1] = (1 - scaled - k) / (1 - k) * 255
    cmyk[:, :, -1] = k[:, :, 0] * 255
    cmyk[:, :, [0, 1, 2, 3]] = cmyk[:, :, [2, 1, 0, 3]]
    spaces.update(
        {
            "gray": gray.astype(np.uint8),
            "hsv": hsv,
            "hls": hls,
            "cmyk": cmyk.astype(np.uint8),
        }
    )
    selected_space = spaces.get(space, hsv)
    channel_map = {
        "red": 0,
        "green": 1,
        "blue": 2,
        "hue": 0,
        "saturation": 1,
        "value": 2,
        "lightness": 1,
        "cyan": 0,
        "magenta": 1,
        "yellow": 2,
        "black": 3,
        "x": 0,
        "y": 1,
        "z": 2,
        "l": 0,
        "a": 1,
        "b": 2,
    }
    index = channel_map.get(channel, 0)
    plane = selected_space[:, :, index]
    return ServiceResult(
        data={"space": space, "channel": channel},
        images={"channel": cv.cvtColor(plane, cv.COLOR_GRAY2BGR)},
    )


def pca_projection(image, component: int = 0, mode: str = "distance", invert: bool = False, equalize: bool = False) -> ServiceResult:
    rows, cols, channels = image.shape
    flattened = np.reshape(image, (rows * cols, channels)).astype(np.float64)
    mean, eigenvectors, _ = cv.PCACompute2(flattened, np.array([]))
    projected = np.reshape(cv.PCAProject(flattened, mean, eigenvectors), (rows, cols, channels))
    centered = image.astype(np.float32) - mean
    outputs = []
    for index, vector in enumerate(eigenvectors):
        cross = np.cross(centered, vector)
        distance = np.linalg.norm(cross, axis=2) / np.linalg.norm(vector)
        project = projected[:, :, index]
        outputs.extend(
            [
                norm_mat(distance, to_bgr=True),
                norm_mat(project, to_bgr=True),
                norm_img(cross),
            ]
        )
    mode_index = {"distance": 0, "projection": 1, "cross_product": 2}.get(mode, 0)
    selected = outputs[component * 3 + mode_index]
    if invert:
        selected = cv.bitwise_not(selected)
    if equalize:
        selected = equalize_img(selected)
    return ServiceResult(
        data={
            "component": component + 1,
            "mode": mode,
            "mean_vector": mean.flatten().tolist(),
            "eigenvectors": eigenvectors.tolist(),
        },
        images={"pca": selected},
    )


def pixel_statistics(image, mode: str = "minimum", inclusive: bool = False) -> ServiceResult:
    b, g, r = cv.split(image)
    blue = np.array([255, 0, 0])
    green = np.array([0, 255, 0])
    red = np.array([0, 0, 255])
    minimum = np.zeros_like(image)
    minimum[np.logical_and(b < g, b < r) if not inclusive else np.logical_and(b <= g, b <= r)] = blue
    minimum[np.logical_and(g < r, g < b) if not inclusive else np.logical_and(g <= r, g <= b)] = green
    minimum[np.logical_and(r < b, r < g) if not inclusive else np.logical_and(r <= b, r <= g)] = red
    maximum = np.zeros_like(image)
    maximum[np.logical_and(b > g, b > r) if not inclusive else np.logical_and(b >= g, b >= r)] = blue
    maximum[np.logical_and(g > r, g > b) if not inclusive else np.logical_and(g >= r, g >= b)] = green
    maximum[np.logical_and(r > b, r > g) if not inclusive else np.logical_and(r >= b, r >= g)] = red
    average = np.zeros_like(image)
    average[np.logical_or(np.logical_and(r < b, b < g), np.logical_and(g < b, b < r))] = blue
    average[np.logical_or(np.logical_and(r < g, g < b), np.logical_and(b < g, g < r))] = green
    average[np.logical_or(np.logical_and(b < r, r < g), np.logical_and(g < r, r < b))] = red
    outputs = {"minimum": minimum, "maximum": maximum, "average": average}
    selected = outputs.get(mode, minimum)
    return ServiceResult(data={"mode": mode, "inclusive": inclusive}, images={"stats": selected})


def rgb_hsv_histogram(image) -> ServiceResult:
    rgb = cv.cvtColor(image, cv.COLOR_BGR2RGB)
    hsv = cv.cvtColor(image, cv.COLOR_BGR2HSV)
    channels = {
        "red": compute_channel_hist(rgb[:, :, 0]),
        "green": compute_channel_hist(rgb[:, :, 1]),
        "blue": compute_channel_hist(rgb[:, :, 2]),
        "hue": compute_channel_hist(hsv[:, :, 0]),
        "saturation": compute_channel_hist(hsv[:, :, 1]),
        "value": compute_channel_hist(hsv[:, :, 2]),
    }
    pixels = image.shape[0] * image.shape[1]
    unique_colors = int(np.unique(np.reshape(image, (pixels, 3)), axis=0).shape[0])
    return ServiceResult(
        data={
            "histograms": channels,
            "unique_colors": unique_colors,
            "unique_color_ratio_percent": round(unique_colors / pixels * 100, 2),
        }
    )


def compute_channel_hist(channel):
    hist = cv.calcHist([channel], [0], None, [256], [0, 256]).flatten()
    return hist.astype(int).tolist()
