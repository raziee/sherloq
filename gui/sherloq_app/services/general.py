import os
import re
from datetime import datetime
from pathlib import Path

import cv2 as cv
import magic

from gui.sherloq_app.core.headless import human_size
from gui.sherloq_app.services.io import file_hashes, image_info
from gui.sherloq_app.services.results import ServiceResult


def ballistics(filename: str) -> str:
    table = [
        (r"^DSCN[0-9]{4}\.JPG$", "Nikon Coolpix camera"),
        (r"^DSC_[0-9]{4}\.JPG$", "Nikon digital camera"),
        (r"^FUJI[0-9]{4}\.JPG$", "Fujifilm digital camera"),
        (r"^IMG_[0-9]{4}\.JPG$", "Canon DSLR or iPhone camera"),
        (r"^PIC[0-9]{5}\.JPG$", "Olympus D-600L camera"),
    ]
    for pattern, source in table:
        if re.match(pattern, filename, re.IGNORECASE):
            return source
    return "Unknown source or manually renamed"


def digest(file_path: str, image, file_bytes: bytes) -> ServiceResult:
    path = Path(file_path)
    stat = path.stat()
    hashes = file_hashes(file_bytes)
    perceptual = {
        "average_hash": str(cv.img_hash.averageHash(image)[0]),
        "block_mean_hash": str(cv.img_hash.blockMeanHash(image)[0]),
        "color_moment_hash": str(cv.img_hash.colorMomentHash(image)[0]),
        "marr_hildreth_hash": str(cv.img_hash.marrHildrethHash(image)[0]),
        "perceptual_hash": str(cv.img_hash.pHash(image)[0]),
        "radial_variance_hash": str(cv.img_hash.radialVarianceHash(image)[0]),
    }
    return ServiceResult(
        data={
            "file": {
                "name": path.name,
                "parent_folder": str(path.parent.resolve()),
                "mime_type": magic.from_file(str(path), mime=True),
                "size_bytes": stat.st_size,
                "size_human": human_size(stat.st_size),
                "permissions": oct(stat.st_mode)[-3:],
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
                "name_ballistics": ballistics(path.name),
            },
            "crypto_hashes": hashes,
            "perceptual_hashes": perceptual,
            "image": image_info(image),
        }
    )


def original_preview(image) -> ServiceResult:
    return ServiceResult(
        data={"image": image_info(image)},
        images={"original": image},
    )
