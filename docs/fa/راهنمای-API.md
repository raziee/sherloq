# راهنمای API — Sherloq

این سند راهنمای استفاده از **API تحلیل جنایی تصویر** پروژه Sherloq است. Sherloq دو رابط برنامه‌نویسی ارائه می‌دهد:

1. **REST API** — سرور HTTP مبتنی بر FastAPI برای یکپارچه‌سازی با وب، موبایل یا سرویس‌های دیگر
2. **Python API** — ماژول `gui.sherloq_app.services` برای فراخوانی مستقیم در اسکریپت‌ها و خط لوله‌های پردازش

> **توجه:** API نتیجه قطعی «جعلی / اصیل» برنمی‌گرداند. خروجی‌ها برای تحلیل و آزمایش علمی هستند و نیازمند تفسیر انسانی‌اند.

---

## فهرست

- [راه‌اندازی سرور وب](#راه‌اندازی-سرور-وب)
- [نمای کلی REST API](#نمای-کلی-rest-api)
- [نقاط پایانی](#نقاط-پایانی)
- [فرمت درخواست و پاسخ](#فرمت-درخواست-و-پاسخ)
- [اجرای ناهمزمان (Jobs)](#اجرای-ناهمزمان-jobs)
- [فهرست ابزارها و پارامترها](#فهرست-ابزارها-و-پارامترها)
- [مثال‌های عملی](#مثال‌های-عملی)
- [کدهای خطا](#کدهای-خطا)
- [Python API (بدون HTTP)](#python-api-بدون-http)
- [رابط وب](#رابط-وب)

---

## راه‌اندازی سرور وب

### پیش‌نیازها

ابتدا وابستگی‌های اصلی و سپس وابستگی‌های وب را نصب کنید (از **ریشه مخزن**):

```bash
uv venv --python 3.11
source .venv/bin/activate

uv pip install -r gui/requirements.txt
uv pip install -r requirements-web.txt
```

برای ابزار **TruFor** (اختیاری):

```bash
uv pip install -r gui/requirements_ai_solutions.txt
```

### اجرا

```bash
python sherloq_web.py
```

سرور روی `http://0.0.0.0:8000` بالا می‌آید.

| آدرس | توضیح |
|------|-------|
| `http://localhost:8000/` | رابط وب فارسی (در صورت وجود `web/static`) |
| `http://localhost:8000/docs` | مستندات تعاملی Swagger (OpenAPI) |
| `http://localhost:8000/redoc` | مستندات ReDoc |
| `http://localhost:8000/health` | بررسی سلامت سرویس |

---

## نمای کلی REST API

- **پیشوند:** `/api/v1`
- **نسخه:** `0.1.0`
- **CORS:** همه مبدأها مجاز (`*`)
- **فرمت آپلود:** `multipart/form-data`
- **فرمت تصاویر خروجی:** Base64 (PNG یا JPEG)

```
┌─────────────┐     POST /analyze/{tool_id}      ┌──────────────────┐
│   کلاینت    │ ───────────────────────────────► │  Sherloq API     │
│  (وب/اسکریپت)│ ◄─────────────────────────────── │  (FastAPI)       │
└─────────────┘     JSON + تصاویر Base64         └────────┬─────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────────┐
                                                  │ services/        │
                                                  │ dispatcher.py    │
                                                  └──────────────────┘
```

---

## نقاط پایانی

### `GET /health`

بررسی سلامت سرویس.

**پاسخ:**

```json
{"status": "ok"}
```

---

### `GET /api/v1/tools`

فهرست تمام ابزارهای تحلیل موجود.

**پاسخ:**

```json
{
  "tools": [
    {
      "id": "ela",
      "name": "Error Level Analysis",
      "group": "jpeg",
      "description": "Pixel-wise compression difference map",
      "requires_file": false,
      "async_default": false,
      "parameters": {}
    }
  ],
  "count": 33
}
```

| فیلد | معنی |
|------|------|
| `id` | شناسه ابزار — در URL تحلیل استفاده می‌شود |
| `requires_file` | آیا به فایل روی دیسک نیاز دارد (مثلاً EXIF، JPEG quality) |
| `async_default` | آیا به‌طور پیش‌فرض در پس‌زمینه اجرا شود |
| `parameters` | پارامترهای اضافی ثابت (مثلاً `comparison` نیاز به تصویر دوم دارد) |

---

### `POST /api/v1/analyze/{tool_id}`

اجرای یک ابزار تحلیل روی تصویر آپلودشده.

**پارامتر مسیر:**

| نام | نوع | توضیح |
|-----|-----|-------|
| `tool_id` | string | شناسه ابزار (مثلاً `ela`، `exif`، `copy_move`) |

**فیلدهای فرم (`multipart/form-data`):**

| فیلد | نوع | الزامی | پیش‌فرض | توضیح |
|------|-----|--------|---------|-------|
| `image` | فایل | بله | — | تصویر ورودی |
| `reference` | فایل | خیر | — | تصویر مرجع (فقط برای `comparison`) |
| `params` | string | خیر | — | پارامترهای ابزار به‌صورت JSON |
| `image_format` | string | خیر | `png` | فرمت خروجی تصاویر: `png` یا `jpeg` |
| `async_mode` | string | خیر | مقدار `async_default` ابزار | `true`/`false` — اجرای پس‌زمینه |

**پاسخ همزمان (مستقیم):**

```json
{
  "tool": "ela",
  "group": "jpeg",
  "elapsed_ms": 842,
  "image": {
    "width": 1920,
    "height": 1080,
    "channels": 3,
    "dtype": "uint8"
  },
  "data": {
    "quality": 75,
    "scale": 50,
    "contrast": 20
  },
  "images": {
    "ela": "iVBORw0KGgoAAAANSUhEUgAA..."
  }
}
```

**پاسخ ناهمزمان (وقتی `async_mode=true` یا ابزار `async_default` دارد):**

```json
{
  "job_id": "a1b2c3d4e5f6...",
  "status": "running",
  "tool": "copy_move",
  "poll_url": "/api/v1/jobs/a1b2c3d4e5f6..."
}
```

---

### `GET /api/v1/jobs/{job_id}`

پیگیری وضعیت یک کار پس‌زمینه.

**پاسخ (در حال اجرا):**

```json
{
  "job_id": "a1b2c3d4e5f6...",
  "tool": "copy_move",
  "status": "running"
}
```

**پاسخ (موفق):**

```json
{
  "job_id": "a1b2c3d4e5f6...",
  "tool": "copy_move",
  "status": "completed",
  "result": {
    "tool": "copy_move",
    "group": "tampering",
    "elapsed_ms": 12450,
    "image": { "width": 800, "height": 600, "channels": 3, "dtype": "uint8" },
    "data": { "keypoints_total": 1523, "clusters": 4 },
    "images": { "result": "..." }
  }
}
```

**پاسخ (ناموفق):**

```json
{
  "job_id": "a1b2c3d4e5f6...",
  "tool": "trufor",
  "status": "failed",
  "error": "TruFor weights not found..."
}
```

وضعیت‌های ممکن: `queued`، `running`، `completed`، `failed`

---

## فرمت درخواست و پاسخ

### فیلد `params`

رشته JSON شامل پارامترهای اختیاری ابزار. مثال:

```json
{"quality": 80, "scale": 60, "grayscale": true}
```

اگر JSON نامعتبر باشد، پاسخ `400` برمی‌گردد.

### فیلد `images` در پاسخ

هر کلید یک نام لایه خروجی است و مقدار آن **رشته Base64** تصویر است. برای نمایش در HTML:

```html
<img src="data:image/png;base64,{مقدار}" />
```

### فیلد `data` در پاسخ

داده‌های ساختاریافته غیرتصویری: متادیتا، آمار، منحنی‌ها، امتیازها و غیره. ساختار بسته به ابزار متفاوت است.

---

## اجرای ناهمزمان (Jobs)

برخی ابزارها سنگین‌اند و به‌طور پیش‌فرض در پس‌زمینه اجرا می‌شوند:

| شناسه ابزار | `async_default` |
|-------------|-----------------|
| `minmax_deviation` | بله |
| `ghost_maps` | بله |
| `contrast_enhancement` | بله |
| `copy_move` | بله |
| `composite_splicing` | بله |
| `image_resampling` | بله |
| `trufor` | بله |
| `median_filtering` | بله |

**گردش کار:**

1. `POST /api/v1/analyze/{tool_id}` → دریافت `job_id`
2. حلقه `GET /api/v1/jobs/{job_id}` تا `status` برابر `completed` یا `failed` شود
3. خواندن `result` از پاسخ نهایی

حداکثر **۲ کار** همزمان در صف اجرا می‌شوند (`ThreadPoolExecutor`).

---

## فهرست ابزارها و پارامترها

### عمومی (`general`)

#### `digest` — خلاصه فایل
- **نیاز به فایل:** بله
- **پارامتر:** ندارد
- **خروجی `data`:** اطلاعات فایل، هش‌های MD5/SHA، هش‌های ادراکی OpenCV

#### `original` — پیش‌نمایش تصویر
- **پارامتر:** ندارد
- **خروجی `images`:** `original`

---

### متادیتا (`metadata`)

#### `exif` — خروجی EXIF
- **نیاز به فایل:** بله
- **خروجی `data`:** `tags` (آرایه‌ای از `{group, description, value}`)

#### `header` — ساختار هدر
- **نیاز به فایل:** بله
- **خروجی `data`:** `html` (خروجی ExifTool)

#### `thumbnail` — تحلیل بندانگشتی
- **نیاز به فایل:** بله
- **خروجی `images`:** `thumbnail_resized`، `difference`

#### `geolocation` — موقعیت GPS
- **نیاز به فایل:** بله
- **خروجی `data`:** `latitude`، `longitude`، `maps_url`

---

### بازرسی (`inspection`)

#### `adjustments` — تنظیمات سراسری

| پارامتر | نوع | پیش‌فرض | توضیح |
|---------|-----|---------|-------|
| `brightness` | int | 0 | روشنایی |
| `saturation` | int | 0 | اشباع |
| `hue` | int | 0 | رنگ |
| `gamma` | float | 1.0 | گاما |
| `shadows` | int | 0 | سایه‌ها (درصد) |
| `highlights` | int | 0 | نقاط روشن (درصد) |
| `sweep` | int | 127 | مرکز بازه tonal |
| `width` | int | 255 | عرض بازه tonal |
| `threshold` | int | 255 | آستانه (۰ = Otsu) |
| `sharpen` | int | 0 | تیزی |
| `equalize` | int | 0 | هیستوگرام (۱=معمولی، ۲–۵=CLAHE) |
| `invert` | bool | false | معکوس |

- **خروجی `images`:** `adjusted`

#### `histogram` — هیستوگرام کانال
- **خروجی `data`:** `histograms` (red/green/blue/value)، `unique_colors`

#### `magnifier` — ذره‌بین تقویتی

| پارامتر | نوع | پیش‌فرض |
|---------|-----|---------|
| `center_x` | int | — (الزامی) |
| `center_y` | int | — (الزامی) |
| `radius` | int | 64 |
| `gain` | float | 2.0 |

- **خروجی `images`:** `magnifier`

#### `comparison` — مقایسه با مرجع
- **نیاز به `reference`:** بله (فیلد فرم دوم)
- **خروجی `data`:** `mse`، `psnr`
- **خروجی `images`:** `difference`، `reference`

---

### جزئیات (`detail`)

#### `luminance_gradient` — گرادیان روشنایی

| پارامتر | پیش‌فرض | مقادیر |
|---------|---------|--------|
| `intensity` | 95 | ۰–۱۰۰ |
| `blue_mode` | `"abs"` | `none`، `flat`، `abs`، `norm` |
| `invert` | false | |
| `equalize` | false | |

#### `echo_edge` — فیلتر لبه Echo

| پارامتر | پیش‌فرض |
|---------|---------|
| `radius` | 2 |
| `contrast` | 85 |
| `grayscale` | false |

#### `wavelet_threshold` — آستانه موجک

| پارامتر | پیش‌فرض |
|---------|---------|
| `family` | `"daubechies"` |
| `wavelet` | `"db4"` |
| `threshold` | 0 |
| `mode` | `"soft"` |
| `level` | null (خودکار) |

#### `frequency_split` — تفکیک فرکانس

| پارامتر | پیش‌فرض |
|---------|---------|
| `separation` | 15 |
| `smooth` | 25 |
| `threshold` | 0 |
| `filter_radius` | 0 |

- **خروجی `images`:** `low_frequency`، `high_frequency`، `dft_magnitude`، `dft_phase`

---

### رنگ (`colors`)

#### `space_conversion` — تبدیل فضای رنگ

| پارامتر | پیش‌فرض | مقادیر `space` |
|---------|---------|----------------|
| `space` | `"hsv"` | `rgb`، `hsv`، `hls`، `ycrcb`، `xyz`، `lab`، `luv`، `gray`، `cmyk` |
| `channel` | `"hue"` | `red`، `green`، `blue`، `hue`، `saturation`، `value`، ... |

#### `pca_projection` — تصویرسازی PCA

| پارامتر | پیش‌فرض |
|---------|---------|
| `component` | 0 |
| `mode` | `"distance"` (`projection`، `cross_product`) |
| `invert` | false |
| `equalize` | false |

#### `pixel_statistics` — آمار پیکسل

| پارامتر | پیش‌فرض |
|---------|---------|
| `mode` | `"minimum"` (`maximum`، `average`) |
| `inclusive` | false |

#### `rgb_hsv_plots` — هیستوگرام RGB/HSV
- **خروجی `data`:** `histograms` برای شش کانال

---

### نویز (`noise`)

#### `noise_separation` — تفکیک نویز

| پارامتر | پیش‌فرض |
|---------|---------|
| `mode` | `"median"` (`gaussian`، `box`، `bilateral`، `nlm`) |
| `radius` | 1 |
| `sigma` | 3 |
| `levels` | 32 |
| `grayscale` | false |
| `show_denoised` | false |

#### `minmax_deviation` — انحراف Min/Max

| پارامتر | پیش‌فرض |
|---------|---------|
| `channel` | `"luminance"` |
| `minimum_color` | `"green"` |
| `maximum_color` | `"red"` |
| `filter_radius` | 0 |

#### `bit_planes` — صفحات بیت

| پارامتر | پیش‌فرض |
|---------|---------|
| `channel` | `"luminance"` |
| `plane` | 0 (۰–۷) |
| `filter_mode` | `"disabled"` (`median`، `gaussian`) |

- **خروجی `images`:** `plane`، `bit_0` … `bit_7`

#### `wavelet_blocking` — بلوک‌بندی موجک

| پارامتر | پیش‌فرض |
|---------|---------|
| `blocksize` | 8 |

- **نیاز به فایل:** بله

---

### JPEG (`jpeg`)

#### `jpeg_quality` — تخمین کیفیت
- **نیاز به فایل:** بله
- **خروجی `data`:** `compression_loss_curve`، `jpeg` (کیفیت، جداول کوانتیزاسیون)

#### `ela` — تحلیل سطح خطا

| پارامتر | پیش‌فرض |
|---------|---------|
| `quality` | 75 |
| `scale` | 50 |
| `contrast` | 20 |
| `linear` | false |
| `grayscale` | false |

#### `multiple_compression` — فشرده‌سازی چندگانه
- **خروجی `data`:** `qualities`، `losses` (منحنی خطا)

#### `ghost_maps` — نقشه Ghost

| پارامتر | پیش‌فرض |
|---------|---------|
| `qmin` | 50 |
| `qmax` | 90 |
| `qstep` | 5 |
| `shift_x` | 0 |
| `shift_y` | 0 |
| `include_original` | false |
| `grayscale` | true |

- **نیاز به فایل:** بله
- **خروجی `images`:** `ghost_plot`

---

### دستکاری (`tampering`)

#### `contrast_enhancement` — تقویت کنتراست

| پارامتر | پیش‌فرض |
|---------|---------|
| `algorithm` | `"joint"` (`histogram_error`، `channel_similarity`) |
| `block_size` | 64 |

#### `copy_move` — جعل Copy-Move

| پارامتر | پیش‌فرض |
|---------|---------|
| `detector` | `"brisk"` (`orb`، `akaze`) |
| `response_percent` | 90 |
| `matching_percent` | 20 |
| `distance_percent` | 15 |
| `cluster_size` | 5 |
| `show_keypoints` | false |
| `hide_lines` | false |

#### `composite_splicing` — الحاق ترکیبی (Noiseprint)
- **خروجی `images`:** `noise_print`، `splicing_heatmap`

#### `image_resampling` — نمونه‌برداری مجدد

| پارامتر | پیش‌فرض |
|---------|---------|
| `filter_size` | 3 |
| `max_dimension` | 640 |

- **نیاز به فایل:** بله

---

### هوش مصنوعی (`ai`)

#### `trufor` — تشخیص جعل با TruFor

| پارامتر | پیش‌فرض | توضیح |
|---------|---------|-------|
| `gpu` | -1 | شماره GPU (-1 = CPU) |

- **نیاز به فایل:** بله
- **نیاز به:** `gui/requirements_ai_solutions.txt` و وزن‌های `gui/TruFor_main/test_docker/weights/trufor.pth.tar`
- **خروجی `data`:** `detection_score`
- **خروجی `images`:** `forgery_map`

---

### متفرقه (`various`)

#### `median_filtering` — فیلتر میانه

| پارامتر | پیش‌فرض |
|---------|---------|
| `min_variance` | 5 |
| `threshold` | 0.4 |
| `show_probability` | true |
| `speckle_filter` | true |
| `block_size` | 64 |

#### `stereogram_decoder` — رمزگشای استریوگرام

| پارامتر | پیش‌فرض |
|---------|---------|
| `mode` | `"pattern"` (`silhouette`، `depth`، `shaded`) |

---

## مثال‌های عملی

### cURL — فهرست ابزارها

```bash
curl -s http://localhost:8000/api/v1/tools | python -m json.tool
```

### cURL — تحلیل ELA

```bash
curl -X POST "http://localhost:8000/api/v1/analyze/ela" \
  -F "image=@sample.jpg" \
  -F 'params={"quality": 75, "scale": 50}' \
  -F "image_format=png"
```

### cURL — EXIF

```bash
curl -X POST "http://localhost:8000/api/v1/analyze/exif" \
  -F "image=@sample.jpg"
```

### cURL — مقایسه دو تصویر

```bash
curl -X POST "http://localhost:8000/api/v1/analyze/comparison" \
  -F "image=@edited.jpg" \
  -F "reference=@original.jpg"
```

### cURL — اجرای ناهمزمان Copy-Move

```bash
# ارسال درخواست
RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/analyze/copy_move" \
  -F "image=@sample.jpg" \
  -F "async_mode=true")

JOB_ID=$(echo "$RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# پیگیری تا اتمام
curl -s "http://localhost:8000/api/v1/jobs/$JOB_ID" | python -m json.tool
```

### Python — REST با `requests`

```python
import requests

with open("sample.jpg", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/analyze/ela",
        files={"image": ("sample.jpg", f, "image/jpeg")},
        data={"params": '{"quality": 80}', "image_format": "png"},
    )

result = response.json()
print(result["data"])
# ذخیره تصویر خروجی
import base64
with open("ela_output.png", "wb") as out:
    out.write(base64.b64decode(result["images"]["ela"]))
```

### JavaScript — Fetch API

```javascript
const form = new FormData();
form.append("image", fileInput.files[0]);
form.append("params", JSON.stringify({ quality: 75 }));

const response = await fetch("/api/v1/analyze/ela", {
  method: "POST",
  body: form,
});
const payload = await response.json();
```

---

## کدهای خطا

| کد HTTP | علت |
|---------|-----|
| `400` | تصویر خالی، JSON نامعتبر در `params`، پارامترهای ناقص (مثلاً `comparison` بدون `reference`) |
| `404` | `tool_id` یا `job_id` نامعتبر |
| `500` | خطای داخلی پردازش |
| `503` | سرویس وابست غیرفعال (مثلاً ExifTool روی پلتفرم فعلی) |

---

## Python API (بدون HTTP)

برای اسکریپت‌ها و خط لوله‌های محلی می‌توانید مستقیماً از ماژول سرویس استفاده کنید:

```python
from pathlib import Path

from gui.sherloq_app.services import analyze, list_tools

# فهرست ابزارها
for tool in list_tools():
    print(tool["id"], tool["name"])

# تحلیل فایل
image_bytes = Path("sample.jpg").read_bytes()
result = analyze(
    "ela",
    image_bytes,
    "sample.jpg",
    params='{"quality": 75, "scale": 50}',
    image_format="png",
)

print(result["elapsed_ms"], "ms")
print(result["data"])
# result["images"] — دیکشنری نام → Base64
```

### ساختار `ServiceResult` (داخلی)

Handlerهای سرویس شیء `ServiceResult` برمی‌گردانند:

```python
from gui.sherloq_app.services.results import ServiceResult

@dataclass
class ServiceResult:
    data: dict[str, Any] = {}      # داده‌های ساختاریافته
    images: dict[str, np.ndarray] = {}  # آرایه‌های OpenCV BGR
```

تابع `analyze()` در `dispatcher.py` این ساختار را به JSON قابل ارسال (با Base64) تبدیل می‌کند.

### بارگذاری تصویر

```python
from gui.sherloq_app.services.io import load_image_from_path, load_image_from_bytes

image = load_image_from_path("/path/to/photo.jpg")
image = load_image_from_bytes(file_bytes, "photo.png")
```

فرمت‌های RAW پشتیبانی‌شده: NEF، RAF، CR2، DNG، ARW و سایر پسوندهای `rawpy`.

### ثبت ابزار جدید (توسعه‌دهندگان)

1. Handler را در `gui/sherloq_app/services/` پیاده‌سازی کنید (بازگشت `ServiceResult`)
2. ابزار را در `_register_tools()` داخل `dispatcher.py` ثبت کنید
3. (اختیاری) ویجت Qt متناظر در `gui/sherloq_app/tools/` برای رابط دسکتاپ

---

## رابط وب

پس از اجرای `sherloq_web.py`، رابط وب فارسی در آدرس اصلی در دسترس است:

- انتخاب ابزار از لیست دسته‌بندی‌شده
- آپلود تصویر (و تصویر مرجع برای `comparison`)
- ویرایش پارامترها به‌صورت JSON
- گزینه اجرای پس‌زمینه برای ابزارهای سنگین
- نمایش JSON خروجی و تصاویر نتیجه

فایل‌های رابط: `web/static/index.html`، `app.js`، `styles.css`

---

## پیوندهای مرتبط

- [معرفی پروژه](معرفی.md)
- [راهنمای نصب و استفاده (GUI)](راهنما.md)
- [ساختار پروژه](../project-structure.md)
- [مستندات تعاملی OpenAPI](http://localhost:8000/docs) (پس از اجرای سرور)
