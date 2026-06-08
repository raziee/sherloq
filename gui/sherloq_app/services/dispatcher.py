import json
import time
from typing import Any

from gui.sherloq_app.services import colors, detail, general, inspection, jpeg_tools, metadata, noise_tools, tampering, various
from gui.sherloq_app.services.io import encode_image_jpeg, encode_image_png, image_info, load_image_from_bytes, save_upload
from gui.sherloq_app.services.registry import TOOL_REGISTRY, ToolSpec
from gui.sherloq_app.services.results import ServiceResult


def _tool(
    tool_id: str,
    name: str,
    group: str,
    description: str,
    handler,
    *,
    requires_file: bool = False,
    async_default: bool = False,
    parameters: dict[str, Any] | None = None,
):
    TOOL_REGISTRY.append(
        ToolSpec(
            id=tool_id,
            name=name,
            group=group,
            description=description,
            handler=handler,
            requires_file=requires_file,
            async_default=async_default,
            parameters=parameters,
        )
    )


def _register_tools():
    if TOOL_REGISTRY:
        return

    # General
    _tool("digest", "File Digest", "general", "Physical file info, crypto and perceptual hashes", general.digest, requires_file=True)
    _tool("original", "Original Image", "general", "Return the reference image and dimensions", general.original_preview)

    # Metadata
    _tool("exif", "EXIF Full Dump", "metadata", "Extract all available metadata tags", metadata.exif_dump, requires_file=True)
    _tool("header", "Header Structure", "metadata", "HTML dump of file header structure", metadata.header_structure, requires_file=True)
    _tool("thumbnail", "Thumbnail Analysis", "metadata", "Compare embedded thumbnail with the main image", metadata.thumbnail_analysis, requires_file=True)
    _tool("geolocation", "Geolocation Data", "metadata", "Read GPS coordinates when available", metadata.geolocation, requires_file=True)

    # Inspection
    _tool("adjustments", "Global Adjustments", "inspection", "Brightness, hue, saturation and tone controls", inspection.global_adjustments)
    _tool("histogram", "Channel Histogram", "inspection", "Per-channel histogram statistics", inspection.channel_histogram)
    _tool("magnifier", "Enhancing Magnifier", "inspection", "Localized enhancement around a point of interest", inspection.enhancing_magnifier)
    _tool("comparison", "Reference Comparison", "inspection", "Compare two images and return difference metrics", inspection.reference_comparison, parameters={"requires_second_image": True})

    # Detail
    _tool("luminance_gradient", "Luminance Gradient", "detail", "Horizontal and vertical brightness variations", detail.luminance_gradient)
    _tool("echo_edge", "Echo Edge Filter", "detail", "Derivative-based edge emphasis", detail.echo_edge)
    _tool("wavelet_threshold", "Wavelet Threshold", "detail", "Wavelet reconstruction with coefficient thresholding", detail.wavelet_threshold)
    _tool("frequency_split", "Frequency Split", "detail", "Split luminance into low and high frequency components", detail.frequency_split)

    # Colors
    _tool("space_conversion", "Space Conversion", "colors", "Convert and visualize color-space channels", colors.space_conversion)
    _tool("pca_projection", "PCA Projection", "colors", "Project pixels onto principal color components", colors.pca_projection)
    _tool("pixel_statistics", "Pixel Statistics", "colors", "Highlight min/avg/max RGB relationships", colors.pixel_statistics)
    _tool("rgb_hsv_plots", "RGB/HSV Plots", "colors", "Histogram data for RGB and HSV channels", colors.rgb_hsv_histogram)

    # Noise
    _tool("noise_separation", "Signal Separation", "noise", "Estimate and visualize image noise", noise_tools.noise_separation)
    _tool("minmax_deviation", "Min/Max Deviation", "noise", "Highlight pixels deviating from block min/max stats", noise_tools.minmax_deviation, async_default=True)
    _tool("bit_planes", "Bit Plane Values", "noise", "Visualize individual bit planes", noise_tools.bit_planes)
    _tool("wavelet_blocking", "Wavelet Blocking", "noise", "Noise map from wavelet coefficients", noise_tools.wavelet_blocking, requires_file=True)

    # JPEG
    _tool("jpeg_quality", "Quality Estimation", "jpeg", "Estimate last saved JPEG quality", jpeg_tools.quality_estimation, requires_file=True)
    _tool("ela", "Error Level Analysis", "jpeg", "Pixel-wise compression difference map", jpeg_tools.ela)
    _tool("multiple_compression", "Multiple Compression", "jpeg", "Compression loss curve across qualities", jpeg_tools.multiple_compression)
    _tool("ghost_maps", "JPEG Ghost Maps", "jpeg", "Highlight traces of different JPEG compressions", jpeg_tools.ghost_maps, requires_file=True, async_default=True)

    # Tampering
    _tool("contrast_enhancement", "Contrast Enhancement", "tampering", "Detect contrast enhancement traces", tampering.contrast_enhancement, async_default=True)
    _tool("copy_move", "Copy-Move Forgery", "tampering", "Detect cloned regions with feature matching", tampering.copy_move_forgery, async_default=True)
    _tool("composite_splicing", "Composite Splicing", "tampering", "Noiseprint-based splicing heatmap", tampering.composite_splicing, async_default=True)
    _tool("image_resampling", "Image Resampling", "tampering", "Estimate resampling probability map", tampering.image_resampling, requires_file=True, async_default=True)

    # AI
    _tool("trufor", "TruFor", "ai", "AI forgery detection and localization", various.trufor_analysis, requires_file=True, async_default=True)

    # Various
    _tool("median_filtering", "Median Filtering", "various", "Detect traces of median filtering", various.median_filtering, async_default=True)
    _tool("stereogram_decoder", "Stereogram Decoder", "various", "Decode hidden stereogram content", various.stereogram_decoder)


_register_tools()


def list_tools() -> list[dict[str, Any]]:
    _register_tools()
    return [
        {
            "id": tool.id,
            "name": tool.name,
            "group": tool.group,
            "description": tool.description,
            "requires_file": tool.requires_file,
            "async_default": tool.async_default,
            "parameters": tool.parameters or {},
        }
        for tool in TOOL_REGISTRY
    ]


def get_tool(tool_id: str) -> ToolSpec:
    _register_tools()
    for tool in TOOL_REGISTRY:
        if tool.id == tool_id:
            return tool
    raise KeyError(f"Unknown tool: {tool_id}")


def _parse_params(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("params must be a JSON object")
    return data


def analyze(
    tool_id: str,
    file_bytes: bytes,
    filename: str,
    *,
    params: str | None = None,
    second_file_bytes: bytes | None = None,
    second_filename: str | None = None,
    image_format: str = "png",
) -> dict[str, Any]:
    tool = get_tool(tool_id)
    options = _parse_params(params)
    started = time.time()
    image = load_image_from_bytes(file_bytes, filename)
    file_path = None
    if tool.requires_file:
        file_path = save_upload(file_bytes, filename)
    try:
        if tool.id == "digest":
            result = tool.handler(file_path, image, file_bytes)
        elif tool.id in {"exif", "header", "geolocation"}:
            result = tool.handler(file_path)
        elif tool.id in {"thumbnail", "jpeg_quality"}:
            result = tool.handler(file_path, image, **options)
        elif tool.id == "wavelet_blocking":
            result = tool.handler(file_path, image, **options)
        elif tool.id in {"ghost_maps", "image_resampling"}:
            result = tool.handler(file_path, **options)
        elif tool.id == "trufor":
            result = tool.handler(file_path, **options)
        elif tool.id == "comparison":
            if second_file_bytes is None:
                raise ValueError("comparison requires a second uploaded image (reference)")
            reference = load_image_from_bytes(second_file_bytes, second_filename or "reference.jpg")
            result = tool.handler(image, reference, **options)
        else:
            result = tool.handler(image, **options)
    finally:
        if file_path:
            try:
                import os

                os.unlink(file_path)
            except OSError:
                pass

    if not isinstance(result, ServiceResult):
        raise TypeError("Service handler must return ServiceResult")
    encoder = encode_image_png if image_format == "png" else encode_image_jpeg
    encoded_images = {name: encoder(array) for name, array in result.images.items()}
    return {
        "tool": tool.id,
        "group": tool.group,
        "elapsed_ms": int((time.time() - started) * 1000),
        "image": image_info(image),
        "data": result.data,
        "images": encoded_images,
    }
