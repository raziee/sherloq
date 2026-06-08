import math
import os
import shutil
import subprocess
import tempfile
from io import BytesIO

import cv2 as cv
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from joblib import load

from gui.sherloq_app.core.jpeg import (
    DCT_SIZE,
    TABLE_SIZE,
    ZIG_ZAG,
    compress_jpg,
    get_tables,
    loss_curve,
)
from gui.sherloq_app.core.headless import create_lut, desaturate, exiftool_exe
from gui.sherloq_app.paths import model_path
from gui.sherloq_app.services.results import ServiceResult

MRK = b"\xFF"
SOI = b"\xD8"
DQT = b"\xDB"
MSK = b"\x0F"
PAD = b"\x00"
MAX_TABLES = 2
LEN_OFFSET = 2
LUMA_IDX = 0
CHROMA_IDX = 1


def _find_next(file_obj, markers):
    while True:
        for marker in markers:
            byte = file_obj.read(1)
            if not byte:
                return False
            if byte != marker:
                break
        else:
            return True


def _parse_quant_tables(file_path: str) -> tuple[np.ndarray, np.ndarray]:
    exe = exiftool_exe()
    if not exe:
        raise RuntimeError("ExifTool is required for JPEG table extraction")
    luma = np.zeros((DCT_SIZE, DCT_SIZE), dtype=int)
    chroma = np.zeros((DCT_SIZE, DCT_SIZE), dtype=int)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        temp_path = tmp.name
    try:
        shutil.copyfile(file_path, temp_path)
        subprocess.run(
            [exe, "-all=", "-overwrite_original", temp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        found = False
        with open(temp_path, "rb") as handle:
            first = handle.read(1)
            if first not in [MRK, SOI]:
                raise ValueError("File is not a JPEG image")
            while True:
                if not _find_next(handle, [MRK, DQT, PAD]):
                    break
                length = handle.read(1)[0] - LEN_OFFSET
                if length <= 0 or length % (TABLE_SIZE + 1) != 0:
                    continue
                while length > 0:
                    mode = handle.read(1)
                    if not mode:
                        break
                    index = mode[0] & MSK[0]
                    if index >= MAX_TABLES:
                        break
                    length -= 1
                    for k in range(TABLE_SIZE):
                        value = handle.read(1)
                        if not value:
                            break
                        length -= 1
                        i, j = ZIG_ZAG[k]
                        if index == LUMA_IDX:
                            luma[i, j] = value[0]
                        elif index == CHROMA_IDX:
                            chroma[i, j] = value[0]
                    else:
                        found = True
        if not found:
            raise ValueError("Unable to find JPEG quantization tables")
        return luma, chroma
    finally:
        os.unlink(temp_path)


def quality_estimation(file_path: str, image) -> ServiceResult:
    qualities = list(range(1, 101))
    curve = loss_curve(image)
    tail = 5
    min_error_q = int(np.argmin(curve[:-tail]) + 1)
    if min_error_q == 100 - tail:
        min_error_q = 100
    result = ServiceResult(
        data={
            "compression_loss_curve": {
                "qualities": qualities,
                "errors_percent": (curve * 100).tolist(),
                "min_error_quality": min_error_q,
            }
        }
    )
    try:
        luma, chroma = _parse_quant_tables(file_path)
        levels = [(1 - (np.mean(table.ravel()[1:]) - 1) / 254) * 100 for table in (luma, chroma)]
        distance = np.zeros(101)
        for qm in range(101):
            lu, ch = cv.split(get_tables(qm))
            distance[qm] = (np.mean(cv.absdiff(luma, lu)) + 2 * np.mean(cv.absdiff(chroma, ch))) / 3
        closest = int(np.argmin(distance))
        deviation = float(distance[closest])
        if deviation == 0:
            quality = closest
            message = "standard tables"
        else:
            quality = max(1, int(np.round(closest - deviation)))
            message = f"deviation from standard tables ({deviation:.4f})"
        result.data["jpeg"] = {
            "format": "jpeg",
            "last_saved_quality": quality,
            "message": message,
            "luminance_table": luma.tolist(),
            "chrominance_table": chroma.tolist(),
            "luminance_level_percent": levels[0],
            "chrominance_level_percent": levels[1],
        }
    except ValueError:
        modelfile = model_path("jpeg_qf.mdl")
        model = load(modelfile)
        limit = model.best_ntree_limit if hasattr(model, "best_ntree_limit") else None
        qp = float(model.predict(np.reshape(curve, (1, len(curve))), ntree_limit=limit)[0])
        result.data["jpeg"] = {
            "format": "lossless_or_nonstandard",
            "estimated_last_saved_quality": qp,
            "uncompressed": qp >= 99.5,
        }
    return result


def ela(
    image,
    quality: int = 75,
    scale: int = 50,
    contrast: int = 20,
    linear: bool = False,
    grayscale: bool = False,
) -> ServiceResult:
    original = image.astype(np.float32) / 255
    compressed = compress_jpg(image, quality)
    if not linear:
        difference = cv.absdiff(original, compressed.astype(np.float32) / 255)
        output = cv.convertScaleAbs(cv.sqrt(difference) * 255, None, scale / 20)
    else:
        output = cv.convertScaleAbs(cv.subtract(compressed, image), None, scale)
    contrast_value = int(contrast / 100 * 128)
    output = cv.LUT(output, create_lut(contrast_value, contrast_value))
    if grayscale:
        output = desaturate(output)
    return ServiceResult(
        data={
            "quality": quality,
            "scale": scale,
            "contrast": contrast,
            "linear": linear,
            "grayscale": grayscale,
        },
        images={"ela": output},
    )


def multiple_compression(image) -> ServiceResult:
    qualities = list(range(0, 101))
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    losses = []
    for q in qualities:
        loss = cv.mean(cv.absdiff(compress_jpg(gray, q, color=False), gray))[0]
        losses.append(float(loss))
    return ServiceResult(
        data={
            "qualities": qualities,
            "losses": losses,
        }
    )


def ghost_maps(
    file_path: str,
    qmin: int = 50,
    qmax: int = 90,
    qstep: int = 5,
    shift_x: int = 0,
    shift_y: int = 0,
    include_original: bool = False,
    grayscale: bool = True,
) -> ServiceResult:
    original = np.double(cv.imread(file_path))
    if original is None:
        raise ValueError("Unable to read image for ghost map analysis")
    ydim, xdim, zdim = original.shape
    nq = int((qmax - qmin) / qstep) + 1
    ghostmap = np.zeros((ydim, xdim, nq))
    averaging_block = 16
    index = 0
    for quality in range(qmin, qmax + 1, qstep):
        shifted = np.roll(original, shift_x, axis=1)
        shifted = np.roll(shifted, shift_y, axis=0)
        encoded = cv.imencode(".jpg", shifted, [int(cv.IMWRITE_JPEG_QUALITY), quality])[1].tobytes()
        resaved = np.double(cv.imdecode(np.frombuffer(encoded, np.byte), cv.IMREAD_ANYCOLOR))
        for channel in range(zdim):
            ghostmap[:, :, index] += np.square(shifted[:, :, channel] - resaved[:, :, channel])
        ghostmap[:, :, index] /= zdim
        index += 1

    blk_e = np.zeros((int(ydim / averaging_block), int(xdim / averaging_block), nq))
    for c in range(nq):
        cy = 0
        for y in range(0, ydim - averaging_block, averaging_block):
            cx = 0
            for x in range(0, xdim - averaging_block, averaging_block):
                blk_e[cy, cx, c] = np.mean(
                    ghostmap[y : y + averaging_block, x : x + averaging_block, c]
                )
                cx += 1
            cy += 1
    minval = np.min(blk_e, axis=2)
    maxval = np.max(blk_e, axis=2)
    for c in range(nq):
        blk_e[:, :, c] = (blk_e[:, :, c] - minval) / np.maximum(maxval - minval, 1e-9)

    sp = math.ceil(math.sqrt(nq + (1 if include_original else 0)))
    fig = plt.figure(figsize=(12, 8))
    plot_index = 1
    if include_original:
        original_rgb = cv.cvtColor(cv.convertScaleAbs(original), cv.COLOR_BGR2RGB).astype(np.float32) / 255.0
        ax = fig.add_subplot(sp, sp, plot_index)
        ax.imshow(original_rgb)
        ax.set_title("Original")
        ax.axis("off")
        plot_index += 1
    for c in range(nq):
        ax = fig.add_subplot(sp, sp, plot_index)
        cmap = "gray" if grayscale else None
        ax.imshow(blk_e[:, :, c], cmap=cmap, vmin=0, vmax=1)
        ax.set_title(f"Quality {qmin + c * qstep}")
        ax.axis("off")
        plot_index += 1
    fig.suptitle(f"Ghost maps offset X={shift_x} Y={shift_y}")
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    array = np.frombuffer(buffer.getvalue(), dtype=np.uint8)
    plot_image = cv.imdecode(array, cv.IMREAD_COLOR)
    return ServiceResult(
        data={
            "qmin": qmin,
            "qmax": qmax,
            "qstep": qstep,
            "shift_x": shift_x,
            "shift_y": shift_y,
            "map_count": nq,
        },
        images={"ghost_plot": plot_image},
    )
