import cv2 as cv
import numpy as np


def _ssim(a, b, maximum=255):
    c1 = (0.01 * maximum) ** 2
    c2 = (0.03 * maximum) ** 2
    kernel = (11, 11)
    sigma = 1.5
    a2 = a ** 2
    b2 = b ** 2
    ab = a * b
    mu_a = cv.GaussianBlur(a, kernel, sigma)
    mu_b = cv.GaussianBlur(b, kernel, sigma)
    mu_a2 = mu_a ** 2
    mu_b2 = mu_b ** 2
    mu_ab = mu_a * mu_b
    s_a2 = cv.GaussianBlur(a2, kernel, sigma) - mu_a2
    s_b2 = cv.GaussianBlur(b2, kernel, sigma) - mu_b2
    s_ab = cv.GaussianBlur(ab, kernel, sigma) - mu_ab
    t1 = 2 * mu_ab + c1
    t2 = 2 * s_ab + c2
    t3 = t1 * t2
    t1 = mu_a2 + mu_b2 + c1
    t2 = s_a2 + s_b2 + c2
    t1 *= t2
    s_map = cv.divide(t3, t1)
    return cv.mean(s_map)[0]


def _get_metrics(pristine, distorted):
    x0 = pristine.astype(np.float64)
    y0 = distorted.astype(np.float64)
    x2 = np.sum(np.square(x0))
    y2 = np.sum(np.square(y0))
    xs = np.sum(x0)
    error = x0 - y0
    maximum = 255
    metrics = np.zeros(8)
    metrics[0] = np.mean(np.square(error))
    metrics[1] = 20 * np.log10(maximum / np.sqrt(metrics[0])) if metrics[0] > 0 else -1
    metrics[2] = np.sum(x0 * y0) / x2 if x2 > 0 else -1
    metrics[3] = np.mean(error)
    metrics[4] = x2 / y2 if y2 > 0 else -1
    metrics[5] = np.max(error)
    metrics[6] = np.sum(np.abs(error)) / xs if xs > 0 else -1
    metrics[7] = _ssim(x0, y0, maximum)
    return metrics


def get_features(image, windows, levels):
    metrics = 8
    features = np.zeros(windows * levels * metrics)
    index = 0
    for window in range(windows):
        kernel = 2 * (window + 1) + 1
        previous = image
        for _ in range(levels):
            filtered = cv.medianBlur(previous, kernel)
            features[index : index + metrics] = _get_metrics(previous, filtered)
            index += metrics
            previous = filtered
    return features
