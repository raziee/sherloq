import cv2 as cv
import numpy as np

from gui.sherloq_app.core.headless import compute_hist, create_lut
from gui.sherloq_app.services.results import ServiceResult


def global_adjustments(
    image,
    brightness: int = 0,
    saturation: int = 0,
    hue: int = 0,
    gamma: float = 1.0,
    shadows: int = 0,
    highlights: int = 0,
    sweep: int = 127,
    width: int = 255,
    threshold: int = 255,
    sharpen: int = 0,
    equalize: int = 0,
    invert: bool = False,
) -> ServiceResult:
    result = np.copy(image)
    if sharpen > 0:
        kernel = 2 * sharpen + 1
        gaussian = cv.GaussianBlur(result, (kernel, kernel), 0)
        result = cv.addWeighted(result, 1.5, gaussian, -0.5, 0)
    if brightness != 0 or saturation != 0 or hue != 0:
        h, s, v = cv.split(cv.cvtColor(result, cv.COLOR_BGR2HSV))
        if hue != 0:
            h = h.astype(np.float64) + hue
            h[h < 0] += 180
            h[h > 180] -= 180
            h = h.astype(np.uint8)
        if saturation != 0:
            s = cv.add(s, saturation)
        if brightness != 0:
            v = cv.add(v, brightness)
        result = cv.cvtColor(cv.merge([h, s, v]), cv.COLOR_HSV2BGR)
    if gamma != 1.0:
        inverse = 1 / gamma
        lut = np.array([((value / 255) ** inverse) * 255 for value in range(256)]).astype(np.uint8)
        result = cv.LUT(result, lut)
    if shadows != 0:
        result = cv.LUT(result, create_lut(int(shadows / 100 * 255), 0))
    if highlights != 0:
        result = cv.LUT(result, create_lut(0, int(highlights / 100 * 255)))
    if width < 255:
        radius = width // 2
        low = max(sweep - radius, 0)
        high = 255 - min(sweep + radius, 255)
        result = cv.LUT(result, create_lut(low, high))
    if equalize > 0:
        h, s, v = cv.split(cv.cvtColor(result, cv.COLOR_BGR2HSV))
        if equalize == 1:
            v = cv.equalizeHist(v)
        else:
            clip = {2: 2, 3: 5, 4: 10, 5: 20}.get(equalize, 2)
            v = cv.createCLAHE(clip).apply(v)
        result = cv.cvtColor(cv.merge([h, s, v]), cv.COLOR_HSV2BGR)
    if threshold < 255:
        if threshold == 0:
            gray = cv.cvtColor(result, cv.COLOR_BGR2GRAY)
            threshold, _ = cv.threshold(gray, 0, 255, cv.THRESH_OTSU)
        _, result = cv.threshold(result, threshold, 255, cv.THRESH_BINARY)
    if invert:
        result = cv.bitwise_not(result)
    return ServiceResult(images={"adjusted": result})


def channel_histogram(image) -> ServiceResult:
    channels = list(cv.split(cv.cvtColor(image, cv.COLOR_BGR2RGB)))
    channels.append(cv.cvtColor(image, cv.COLOR_BGR2GRAY))
    histograms = {
        "red": compute_hist(channels[0]).tolist(),
        "green": compute_hist(channels[1]).tolist(),
        "blue": compute_hist(channels[2]).tolist(),
        "value": compute_hist(channels[3]).tolist(),
    }
    pixels = image.shape[0] * image.shape[1]
    unique_colors = int(np.unique(np.reshape(image, (pixels, 3)), axis=0).shape[0])
    return ServiceResult(
        data={
            "histograms": histograms,
            "unique_colors": unique_colors,
            "unique_color_ratio_percent": round(unique_colors / pixels * 100, 2),
        }
    )


def enhancing_magnifier(image, center_x: int, center_y: int, radius: int = 64, gain: float = 2.0) -> ServiceResult:
    output = image.copy()
    rows, cols = image.shape[:2]
    x0 = max(center_x - radius, 0)
    y0 = max(center_y - radius, 0)
    x1 = min(center_x + radius, cols)
    y1 = min(center_y + radius, rows)
    patch = image[y0:y1, x0:x1].astype(np.float32)
    enhanced = np.clip(patch * gain, 0, 255).astype(np.uint8)
    laplacian = cv.Laplacian(cv.cvtColor(enhanced, cv.COLOR_BGR2GRAY), cv.CV_16S, ksize=3)
    laplacian = cv.convertScaleAbs(laplacian)
    sharpened = cv.addWeighted(enhanced, 1.2, cv.cvtColor(laplacian, cv.COLOR_GRAY2BGR), 0.4, 0)
    output[y0:y1, x0:x1] = sharpened
    cv.rectangle(output, (x0, y0), (x1, y1), (0, 255, 255), 1)
    return ServiceResult(
        data={"center": {"x": center_x, "y": center_y}, "radius": radius, "gain": gain},
        images={"magnifier": output},
    )


def reference_comparison(image_a, image_b) -> ServiceResult:
    if image_a.shape != image_b.shape:
        image_b = cv.resize(image_b, (image_a.shape[1], image_a.shape[0]))
    diff = cv.absdiff(image_a, image_b)
    gray_a = cv.cvtColor(image_a, cv.COLOR_BGR2GRAY).astype(np.float64)
    gray_b = cv.cvtColor(image_b, cv.COLOR_BGR2GRAY).astype(np.float64)
    mse = float(np.mean((gray_a - gray_b) ** 2))
    psnr = 20 * np.log10(255 / np.sqrt(mse)) if mse > 0 else float("inf")
    return ServiceResult(
        data={"mse": mse, "psnr": psnr},
        images={"difference": diff, "reference": image_b},
    )
