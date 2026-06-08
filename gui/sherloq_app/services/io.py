import base64
import hashlib
import os
import tempfile
from pathlib import Path

import cv2 as cv
import numpy as np
import rawpy

RAW_EXTENSIONS = {
    "nef",
    "raf",
    "cr2",
    "dng",
    "arw",
    "dcr",
    "mrw",
    "pef",
    "crw",
    "sr2",
    "orf",
    "raw",
}


def load_image_from_path(path: str | Path) -> np.ndarray:
    path = Path(path)
    ext = path.suffix.lstrip(".").lower()
    if ext in RAW_EXTENSIONS:
        with rawpy.imread(str(path)) as raw:
            image = cv.cvtColor(
                raw.postprocess(no_auto_bright=True, use_camera_wb=True),
                cv.COLOR_RGB2BGR,
            )
    elif ext == "gif":
        capture = cv.VideoCapture(str(path))
        result, image = capture.read()
        capture.release()
        if not result:
            raise ValueError("Unable to decode GIF")
        if len(image.shape) == 2:
            image = cv.cvtColor(image, cv.COLOR_GRAY2BGR)
    else:
        image = cv.imread(str(path), cv.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unable to load image: {path}")
    if image.ndim == 3 and image.shape[2] > 3:
        image = cv.cvtColor(image, cv.COLOR_BGRA2BGR)
    return image


def load_image_from_bytes(data: bytes, filename: str = "upload.jpg") -> np.ndarray:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext in RAW_EXTENSIONS:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            return load_image_from_path(tmp_path)
        finally:
            os.unlink(tmp_path)
    array = np.frombuffer(data, dtype=np.uint8)
    image = cv.imdecode(array, cv.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unable to decode uploaded image")
    if image.ndim == 3 and image.shape[2] > 3:
        image = cv.cvtColor(image, cv.COLOR_BGRA2BGR)
    return image


def save_upload(data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix or ".jpg"
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="sherloq_")
    os.close(fd)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def encode_image_png(image: np.ndarray) -> str:
    success, buffer = cv.imencode(".png", image)
    if not success:
        raise ValueError("Failed to encode image as PNG")
    return base64.b64encode(buffer).decode("ascii")


def encode_image_jpeg(image: np.ndarray, quality: int = 90) -> str:
    success, buffer = cv.imencode(".jpg", image, [cv.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise ValueError("Failed to encode image as JPEG")
    return base64.b64encode(buffer).decode("ascii")


def file_hashes(data: bytes) -> dict[str, str]:
    return {
        "md5": hashlib.md5(data).hexdigest(),
        "sha1": hashlib.sha1(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sha512": hashlib.sha512(data).hexdigest(),
    }


def image_info(image: np.ndarray) -> dict:
    rows, cols = image.shape[:2]
    channels = 1 if image.ndim == 2 else image.shape[2]
    return {
        "width": cols,
        "height": rows,
        "channels": channels,
        "dtype": str(image.dtype),
    }
