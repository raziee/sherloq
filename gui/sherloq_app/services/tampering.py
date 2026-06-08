import os
from itertools import compress

import cv2 as cv
import numpy as np

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

from gui.noiseprint.noiseprint import genNoiseprint
from gui.noiseprint.noiseprint_blind import genMappUint8, noiseprint_blind_post
from gui.sherloq_app.core.jpeg import estimate_qf
from gui.sherloq_app.core.headless import compute_hist, gray_to_bgr, norm_mat, pad_image
from gui.sherloq_app.services.results import ServiceResult


def contrast_enhancement(image, algorithm: str = "joint", block_size: int = 64) -> ServiceResult:
    rows0, cols0, _ = image.shape
    color = pad_image(image, block_size)
    gray = cv.cvtColor(color, cv.COLOR_BGR2GRAY)
    rows, cols = gray.shape
    kx, ky = cv.getDerivKernels(1, 1, 1)
    bd, gd, rd = [cv.sepFilter2D(channel, cv.CV_32F, kx, ky) for channel in cv.split(color)]
    tri = (np.abs(gd - rd) + np.abs(gd - bd) + np.abs(rd - bd)) / 3
    avg = (np.abs(bd) + np.abs(gd) + np.abs(rd)) / 3
    window = np.arange(256).astype(np.float32)
    cutoff = 8
    window[:cutoff] = (1 - np.cos(np.pi * window[:cutoff] / cutoff)) / 2
    window[-cutoff:] = (1 + np.cos(np.pi * (window[-cutoff:] + cutoff - 255) / cutoff)) / 2
    window[cutoff:-cutoff] = 1
    weight = ((np.arange(256) - 128) / 128) ** 2
    chsim = np.zeros(((rows // block_size) + 1, (cols // block_size) + 1), np.float32)
    error = np.copy(chsim)
    joint = np.copy(chsim)
    max_err = 0.185
    max_sim = 0.75
    for i in range(0, rows, block_size):
        for j in range(0, cols, block_size):
            hist = compute_hist(gray[i : i + block_size, j : j + block_size]) * window
            hist = cv.normalize(hist, None, 0, 1, cv.NORM_MINMAX)
            dft = np.fft.fftshift(cv.dft(hist, flags=cv.DFT_COMPLEX_OUTPUT))
            mag = cv.magnitude(dft[:, :, 0], dft[:, :, 1])
            mag = cv.normalize(mag, None, 0, 1, cv.NORM_MINMAX).flatten()
            diff = 0.0
            for k in range(2, 254):
                yl = 2 * hist[k - 1] - hist[k - 2]
                yr = 2 * hist[k + 1] - hist[k + 2]
                delta = abs(hist[k] - (yl + yr) / 2)
                diff = max(diff, delta)
            energy_den = np.sum(mag)
            if energy_den == 0:
                err = 0.0
            else:
                err = np.sum(mag * weight) / energy_den
                err = 1.0 if err > max_err else err / max_err
                err *= np.sqrt(diff)
            error[i // block_size, j // block_size] = err
            avg_mean = np.mean(avg[i : i + block_size, j : j + block_size])
            if avg_mean == 0:
                similarity = 0.0
            else:
                similarity = np.mean(tri[i : i + block_size, j : j + block_size]) / avg_mean
                similarity = 1.0 if similarity > max_sim else similarity / max_sim
            chsim[i // block_size, j // block_size] = similarity
            joint[i // block_size, j // block_size] = err * similarity

    def upscale(map2d):
        scaled = cv.medianBlur(cv.convertScaleAbs(map2d, None, 255), 3)
        return gray_to_bgr(cv.resize(scaled, None, None, block_size, block_size, cv.INTER_NEAREST)[:rows0, :cols0])

    outputs = {
        "histogram_error": upscale(error),
        "channel_similarity": upscale(chsim),
        "joint_probability": upscale(joint),
    }
    selected = outputs.get(algorithm, outputs["joint_probability"])
    return ServiceResult(
        data={"algorithm": algorithm, "block_size": block_size},
        images={**outputs, "selected": selected},
    )


def copy_move_forgery(
    image,
    detector: str = "brisk",
    response_percent: int = 90,
    matching_percent: int = 20,
    distance_percent: int = 15,
    cluster_size: int = 5,
    show_keypoints: bool = False,
    hide_lines: bool = False,
) -> ServiceResult:
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    detectors = {
        "brisk": cv.BRISK_create,
        "orb": cv.ORB_create,
        "akaze": cv.AKAZE_create,
    }
    creator = detectors.get(detector, cv.BRISK_create)
    detector_obj = creator()
    keypoints, descriptors = detector_obj.detectAndCompute(gray, None)
    total = len(keypoints)
    responses = np.array([k.response for k in keypoints])
    strongest = (cv.normalize(responses, None, 0, 100, cv.NORM_MINMAX) >= (100 - response_percent)).flatten()
    keypoints = list(compress(keypoints, strongest))
    descriptors = descriptors[strongest]
    if len(keypoints) > 30000:
        raise ValueError(f"Too many keypoints found ({total}); reduce response threshold")
    matcher = cv.BFMatcher_create(cv.NORM_HAMMING, True)
    matching_threshold = matching_percent / 100 * 255
    matches = matcher.radiusMatch(descriptors, descriptors, matching_threshold)
    if matches is None:
        return ServiceResult(data={"keypoints": total, "matches": 0, "clusters": 0, "regions": 0}, images={"result": image})
    matches = [item for sublist in matches for item in sublist]
    matches = [match for match in matches if match.queryIdx != match.trainIdx]
    clusters = []
    min_dist = distance_percent / 100 * np.min(gray.shape) / 2
    keypoint_points = np.array([point.pt for point in keypoints])
    distances = np.linalg.norm(
        [keypoint_points[m.queryIdx] - keypoint_points[m.trainIdx] for m in matches], axis=1
    )
    matches = [match for index, match in enumerate(matches) if distances[index] > min_dist]
    for i, match0 in enumerate(matches):
        group = [match0]
        d0 = distances[i]
        for j in range(i + 1, len(matches)):
            match1 = matches[j]
            if match1.queryIdx == match0.trainIdx and match1.trainIdx == match0.queryIdx:
                continue
            if abs(d0 - distances[j]) > min_dist:
                continue
            a0 = np.array(keypoints[match0.queryIdx].pt)
            b0 = np.array(keypoints[match0.trainIdx].pt)
            a1 = np.array(keypoints[match1.queryIdx].pt)
            b1 = np.array(keypoints[match1.trainIdx].pt)
            aa = np.linalg.norm(a0 - a1)
            bb = np.linalg.norm(b0 - b1)
            ab = np.linalg.norm(a0 - b1)
            ba = np.linalg.norm(b0 - a1)
            if not (
                0 < aa < min_dist and 0 < bb < min_dist
                or 0 < ab < min_dist and 0 < ba < min_dist
            ):
                continue
            if any(g.queryIdx == match1.trainIdx and g.trainIdx == match1.queryIdx for g in group):
                continue
            group.append(match1)
        if len(group) >= cluster_size:
            clusters.append(group)

    output = np.copy(image)
    if show_keypoints:
        for keypoint in keypoints:
            cv.circle(output, (int(keypoint.pt[0]), int(keypoint.pt[1])), 2, (250, 227, 72), -1)
    angles = []
    hsv = np.zeros((1, 1, 3), dtype=np.uint8)
    for cluster in clusters:
        for match in cluster:
            ka = keypoints[match.queryIdx]
            kb = keypoints[match.trainIdx]
            pa = tuple(map(int, ka.pt))
            pb = tuple(map(int, kb.pt))
            angle = np.arctan2(pb[1] - pa[1], pb[0] - pa[0])
            if angle < 0:
                angle += np.pi
            angles.append(angle)
            hsv[0, 0, 0] = angle / np.pi * 180
            hsv[0, 0, 1] = 255
            hsv[0, 0, 2] = match.distance / matching_threshold * 255
            rgb = tuple(int(x) for x in cv.cvtColor(hsv, cv.COLOR_HSV2BGR)[0, 0])
            cv.circle(output, pa, int(np.round(ka.size)), rgb, 1, cv.LINE_AA)
            cv.circle(output, pb, int(np.round(kb.size)), rgb, 1, cv.LINE_AA)
            if not hide_lines:
                cv.line(output, pa, pb, rgb, 1, cv.LINE_AA)
    regions = 0
    if angles:
        angle_array = np.reshape(np.array(angles, dtype=np.float32), (len(angles), 1))
        if np.std(angle_array) < 0.1:
            regions = 1
        else:
            criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            compact = [
                cv.kmeans(angle_array, k, None, criteria, 10, cv.KMEANS_PP_CENTERS)[0]
                for k in range(1, 11)
            ]
            compact = cv.normalize(np.array(compact), None, 0, 1, cv.NORM_MINMAX)
            regions = int(np.argmax(compact < 0.005) + 1)
    return ServiceResult(
        data={
            "keypoints_total": total,
            "keypoints_filtered": len(keypoints),
            "matches": len(matches),
            "clusters": len(clusters),
            "regions": regions,
        },
        images={"result": output},
    )


def composite_splicing(image) -> ServiceResult:
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY).astype(np.float32) / 255
    qf = estimate_qf(image)
    noise = genNoiseprint(gray, qf, model_name="net")
    vmin, vmax, _, _ = cv.minMaxLoc(noise[34:-34, 34:-34])
    noise_view = norm_mat(noise.clip(vmin, vmax), to_bgr=True)
    mapp, valid, range0, range1, imgsize, _ = noiseprint_blind_post(noise, gray)
    if mapp is None:
        raise ValueError("Too many invalid blocks for splicing heatmap")
    heatmap = cv.applyColorMap(genMappUint8(mapp, valid, range0, range1, imgsize), cv.COLORMAP_JET)
    return ServiceResult(
        data={"estimated_jpeg_quality": int(qf)},
        images={"noise_print": noise_view, "splicing_heatmap": heatmap},
    )


def _build_matrices_3x3(process_part):
    rows, cols = process_part.shape
    total = (rows - 2) * (cols - 2)
    f_rows = total * 9
    f = np.zeros(f_rows)
    matrix = np.zeros((f_rows, 8))
    index = 0
    for y in range(1, rows - 1):
        for x in range(1, cols - 1):
            patch = process_part[y - 1 : y + 2, x - 1 : x + 2].reshape(-1)
            f[index * 9 : (index + 1) * 9] = patch
            matrix[index * 9 : (index + 1) * 9, 0] = process_part[y - 1, x - 1 : x + 2]
            matrix[index * 9 : (index + 1) * 9, 1] = process_part[y, x - 1 : x + 2]
            matrix[index * 9 : (index + 1) * 9, 2] = process_part[y + 1, x - 1 : x + 2]
            matrix[index * 9 : (index + 1) * 9, 3] = process_part[y - 1 : y + 2, x - 1]
            matrix[index * 9 : (index + 1) * 9, 4] = process_part[y - 1 : y + 2, x]
            matrix[index * 9 : (index + 1) * 9, 5] = process_part[y - 1 : y + 2, x + 1]
            matrix[index * 9 : (index + 1) * 9, 6] = 1
            matrix[index * 9 : (index + 1) * 9, 7] = process_part[y, x]
            index += 1
    return matrix, f


def _probability_map_3x3(process_part):
    coefficients = np.random.rand(8)
    coefficients /= coefficients.sum()
    sigma = 0.005
    damping = 0.1
    matrix, target = _build_matrices_3x3(process_part)
    weights = np.zeros(matrix.shape[0])
    for _ in range(100):
        sigma2 = 0.0
        index = 0
        for y in range(1, process_part.shape[0] - 1):
            for x in range(1, process_part.shape[1] - 1):
                patch = process_part[y - 1 : y + 2, x - 1 : x + 2].reshape(-1)
                residual = patch - matrix[index * 9 : (index + 1) * 9] @ coefficients
                g = np.exp(-(residual ** 2) / sigma)
                weights[index * 9 : (index + 1) * 9] = g / (g + damping)
                sigma2 += np.sum(weights[index * 9 : (index + 1) * 9] * residual ** 2)
                index += 1
        sigma = sigma2 / weights.sum()
        coefficients2 = np.linalg.pinv(matrix.T @ np.diag(weights) @ matrix) @ matrix.T @ (weights * target)
        if np.linalg.norm(coefficients - coefficients2) < 0.01:
            break
        coefficients = coefficients2
    return weights.reshape(process_part.shape[0] - 2, process_part.shape[1] - 2)


def image_resampling(file_path: str, filter_size: int = 3, max_dimension: int = 640) -> ServiceResult:
    gray = cv.imread(file_path, cv.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("Resampling analysis requires a decodable raster image")
    gray = gray.astype(np.float64)
    gray -= gray.min()
    if gray.max() > 0:
        gray /= gray.max()
    height, width = gray.shape
    scale = min(1.0, max_dimension / max(height, width))
    if scale < 1.0:
        gray = cv.resize(gray, None, fx=scale, fy=scale, interpolation=cv.INTER_AREA)
    probability = _probability_map_3x3(gray)
    probability = cv.normalize(probability, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)
    probability = cv.resize(probability, (width, height), interpolation=cv.INTER_NEAREST)
    return ServiceResult(
        data={"filter_size": filter_size, "analysis_scale": scale},
        images={"probability_map": cv.cvtColor(probability, cv.COLOR_GRAY2BGR)},
    )
