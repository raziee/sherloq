import subprocess
import tempfile
from pathlib import Path

import cv2 as cv

from gui.pyexiftool import exiftool
from gui.sherloq_app.core.headless import exiftool_exe
from gui.sherloq_app.services.results import ServiceResult

IGNORE_TAGS = {
    "SourceFile",
    "ExifTool:ExifTool",
    "File:FileName",
    "File:Directory",
    "File:FileSize",
    "File:FileModifyDate",
    "File:FileInodeChangeDate",
    "File:FileAccessDate",
    "File:FileType",
    "File:FilePermissions",
    "File:FileTypeExtension",
    "File:MIMEType",
}


def exif_dump(file_path: str) -> ServiceResult:
    rows = []
    with exiftool.ExifTool(exiftool_exe()) as et:
        metadata = et.get_metadata(file_path)
        for tag, value in metadata.items():
            if not value or any(part in tag for part in IGNORE_TAGS):
                continue
            value = str(value).replace(", use -b option to extract", "")
            value = value.replace("Binary data ", "Binary data: ")
            group, desc = tag.split(":", 1)
            rows.append({"group": group, "description": desc, "value": value})
    return ServiceResult(data={"tags": rows, "count": len(rows)})


def header_structure(file_path: str) -> ServiceResult:
    exe = exiftool_exe()
    if not exe:
        raise RuntimeError("ExifTool binary is not available on this platform")
    result = subprocess.run([exe, "-htmldump0", file_path], capture_output=True, check=True)
    html = result.stdout.decode("utf-8", errors="replace")
    return ServiceResult(data={"html": html})


def thumbnail_analysis(file_path: str, image) -> ServiceResult:
    exe = exiftool_exe()
    if not exe:
        raise RuntimeError("ExifTool binary is not available on this platform")
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        output = subprocess.check_output([exe, "-b", "-ThumbnailImage", file_path])
        if not output:
            return ServiceResult(data={"error": "Thumbnail image not found"})
        with open(tmp_path, "wb") as handle:
            handle.write(output)
        thumb = cv.imread(tmp_path, cv.IMREAD_COLOR)
        if thumb is None:
            return ServiceResult(data={"error": "Thumbnail image not found"})
        resized = cv.resize(thumb, image.shape[1::-1], interpolation=cv.INTER_LANCZOS4)
        diff = cv.absdiff(image, resized)
        return ServiceResult(
            data={
                "thumbnail_size": {"width": thumb.shape[1], "height": thumb.shape[0]},
                "main_size": {"width": image.shape[1], "height": image.shape[0]},
            },
            images={"thumbnail_resized": resized, "difference": diff},
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def geolocation(file_path: str) -> ServiceResult:
    with exiftool.ExifTool(exiftool_exe()) as et:
        metadata = et.get_metadata(file_path)
        try:
            lat = metadata["Composite:GPSLatitude"]
            lon = metadata["Composite:GPSLongitude"]
        except KeyError:
            return ServiceResult(data={"found": False, "error": "Geolocation data not found"})
    maps_url = (
        f"https://www.google.com/maps/place/{lat},{lon}/@{lat},{lon},17z/"
        f"data=!4m5!3m4!1s0x0:0x0!8m2!3d{lat}!4d{lon}"
    )
    return ServiceResult(
        data={
            "found": True,
            "latitude": float(lat),
            "longitude": float(lon),
            "maps_url": maps_url,
        }
    )
