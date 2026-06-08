import sys

import cv2 as cv
import numpy as np
import xgboost as xgb

from gui.sherloq_app.core.headless import gray_to_bgr, norm_img, norm_mat, pad_image
from gui.sherloq_app.paths import GUI_ROOT, TRUFOR_DIR, model_path
from gui.sherloq_app.services.results import ServiceResult
from gui.sherloq_app.services.median_features import get_features


def stereogram_decoder(image, mode: str = "pattern") -> ServiceResult:
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    small = cv.resize(gray, None, None, 1, 0.5)
    start = 10
    end = small.shape[1] // 3
    diff = np.fromiter(
        [cv.mean(cv.absdiff(small[:, offset:], small[:, :-offset]))[0] for offset in range(start, end)],
        np.float32,
    )
    _, maximum, _, argmax = cv.minMaxLoc(np.ediff1d(diff))
    if maximum < 2:
        raise ValueError("Unable to detect stereogram pattern")
    offset = argmax[1] + start
    left = image[:, offset:]
    right = image[:, :-offset]
    pattern = norm_img(cv.absdiff(left, right))
    temp = cv.cvtColor(pattern, cv.COLOR_BGR2GRAY)
    threshold, _ = cv.threshold(temp, 0, 255, cv.THRESH_TRIANGLE)
    silhouette = cv.medianBlur(gray_to_bgr(cv.threshold(temp, threshold, 255, cv.THRESH_BINARY)[1]), 3)
    left_gray = cv.cvtColor(left, cv.COLOR_BGR2GRAY)
    right_gray = cv.cvtColor(right, cv.COLOR_BGR2GRAY)
    flow = cv.calcOpticalFlowFarneback(
        left_gray, right_gray, None, 0.5, 5, 15, 5, 5, 1.2, cv.OPTFLOW_FARNEBACK_GAUSSIAN
    )[:, :, 0]
    depth = gray_to_bgr(norm_mat(flow))
    flow_norm = np.repeat(cv.normalize(flow, None, 0, 1, cv.NORM_MINMAX)[:, :, np.newaxis], 3, axis=2)
    shaded = cv.normalize(pattern.astype(np.float32) * flow_norm, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)
    outputs = {
        "pattern": pattern,
        "silhouette": silhouette,
        "depth": depth,
        "shaded": shaded,
    }
    return ServiceResult(
        data={"detected_offset": int(offset)},
        images={**outputs, "selected": outputs.get(mode, pattern)},
    )


def median_filtering(
    image,
    min_variance: int = 5,
    threshold: float = 0.4,
    show_probability: bool = True,
    speckle_filter: bool = True,
    block_size: int = 64,
) -> ServiceResult:
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    booster = xgb.Booster()
    modelfile = model_path(f"median_b{block_size}.json")
    booster.load_model(modelfile)
    columns = booster.num_features()
    if columns == 8:
        levels, windows = 1, 1
    elif columns == 24:
        levels, windows = 3, 1
    elif columns == 96:
        levels, windows = 3, 4
    elif columns == 128:
        levels, windows = 4, 4
    else:
        raise ValueError("Unknown median-filter detection model format")
    padded = pad_image(gray, block_size)
    rows, cols = padded.shape
    probability = np.zeros(((rows // block_size) + 1, (cols // block_size) + 1))
    variance = np.zeros_like(probability)
    for i in range(0, rows, block_size):
        for j in range(0, cols, block_size):
            roi = padded[i : i + block_size, j : j + block_size]
            features = xgb.DMatrix(np.reshape(get_features(roi, windows, levels), (1, columns)))
            probability[i // block_size, j // block_size] = booster.predict(features)[0]
            variance[i // block_size, j // block_size] = np.var(roi)
    mask = variance < min_variance
    prob = cv.medianBlur(probability.astype(np.float32), 3) if speckle_filter else probability.astype(np.float32)
    if show_probability:
        output = np.repeat(prob[:, :, np.newaxis], 3, axis=2)
        output[mask] = 0
    else:
        output = np.zeros((prob.shape[0], prob.shape[1], 3))
        blue, green, red = cv.split(output)
        blue[mask] = 1
        green[(prob < threshold) & ~mask] = 1
        red[(prob >= threshold) & ~mask] = 1
        output = cv.merge((blue, green, red))
    output = cv.convertScaleAbs(output, None, 255)
    output = cv.resize(output, None, None, block_size, block_size, cv.INTER_LINEAR)
    output = np.copy(output[: image.shape[0], : image.shape[1]])
    avg_prob = float(cv.mean(prob, 1 - mask.astype(np.uint8))[0] * 100)
    return ServiceResult(
        data={"average_probability_percent": avg_prob, "threshold": threshold},
        images={"median_map": output},
    )


def trufor_analysis(file_path: str, gpu: int = -1) -> ServiceResult:
    weights = TRUFOR_DIR / "test_docker" / "weights" / "trufor.pth.tar"
    if not weights.exists():
        raise RuntimeError(
            "TruFor weights not found. Install gui/requirements_ai_solutions.txt and place weights under gui/TruFor_main/test_docker/weights/"
        )
    if str(GUI_ROOT) not in sys.path:
        sys.path.insert(0, str(GUI_ROOT))
    from TruFor_main.test_docker.src.analyze_image import process_image

    prediction, detection_score = process_image(file_path, gpu)
    if prediction is None:
        raise RuntimeError("TruFor did not return a prediction")
    heatmap = cv.applyColorMap((prediction * 255).astype(np.uint8), cv.COLORMAP_JET)
    return ServiceResult(
        data={"detection_score": float(detection_score), "gpu": gpu},
        images={"forgery_map": heatmap},
    )
