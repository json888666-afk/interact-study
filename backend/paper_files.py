import base64
import io
import math
import posixpath
import re
import threading
import zipfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import PurePath
from xml.etree import ElementTree

import pypdfium2 as pdfium
from PIL import Image, ImageOps

MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 16
MAX_PIXELS = 25_000_000
PDF_LOCK = threading.Lock()
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DRAW = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
MATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


@dataclass
class Page:
    file: str
    page: int
    text: str = ""
    images: tuple[str, ...] = ()
    regions: tuple[tuple[tuple[int, int, int, int], str], ...] = ()


def encode_image(image):
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((1800, 2200))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def image_data(data):
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > MAX_PIXELS:
            raise ValueError("仅支持 PNG、JPEG、WebP 图片，且不得超过 2500 万像素。")
        return encode_image(image)


def photo_page(filename, data):
    with Image.open(io.BytesIO(data)) as source:
        if source.format not in {"PNG", "JPEG", "WEBP"} or source.width * source.height > MAX_PIXELS:
            raise ValueError("仅支持 PNG、JPEG、WebP 图片，且不得超过 2500 万像素。")
        image = ImageOps.exif_transpose(source).convert("RGB")
    width, height = image.size
    overview = encode_image(image)
    boxes = []
    if height >= 600 or width >= 650:
        rows = min(5, max(2, math.ceil(height / min(1400, max(650, width)))))
        # Read strips across the gutter too, so a single-column question isn't cut in half.
        for start in range(rows):
            overlap = 0.18 / rows
            top = max(0, start / rows - overlap)
            bottom = min(1, (start + 1) / rows + overlap)
            boxes.append((0, top, 1, bottom))
        if width >= 650:
            for left, right in ((0, 0.56), (0.44, 1)):
                for start in range(rows):
                    overlap = 0.18 / rows
                    boxes.append((left, max(0, start / rows - overlap), right, min(1, (start + 1) / rows + overlap)))
    regions = tuple(
        ((round(l * 1000), round(t * 1000), round(r * 1000), round(b * 1000)),
         encode_image(image.crop((round(l * width), round(t * height), round(r * width), round(b * height)))))
        for l, t, r, b in boxes
    )
    return Page(filename, 1, images=(overview,), regions=regions)


def read_pdf(filename, data):
    if not data.startswith(b"%PDF-"):
        raise ValueError("PDF 文件格式无效。")
    pages = []
    # PDFium calls must be serialized, even when imports run on worker threads.
    with PDF_LOCK, pdfium.PdfDocument(data) as document:
        if not 0 < len(document) <= MAX_PAGES:
            raise ValueError(f"每次最多导入 {MAX_PAGES} 页。")
        for i in range(len(document)):
            with closing(document[i]) as page:
                with closing(page.get_textpage()) as textpage:
                    text = textpage.get_text_bounded().strip()
                if len(re.sub(r"\s+", "", text)) >= 80 and "\ufffd" not in text:
                    pages.append(Page(filename, i + 1, text[:12000]))
                    continue
                dimension = max(page.get_size())
                if not math.isfinite(dimension) or dimension <= 0:
                    raise ValueError("PDF 中有尺寸无效的页面。")
                scale = min(3, 1950 / dimension)
                with closing(page.render(scale=scale)) as bitmap:
                    pages.append(Page(filename, i + 1, images=(encode_image(bitmap.to_pil()),)))
    return pages


def xml_part(archive, name):
    value = archive.read(name)
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)", value, re.I):
        raise ValueError("Word 文件包含不受支持的 XML 声明。")
    return ElementTree.fromstring(value)


def read_docx(filename, data):
    pages = []
    paragraphs = []
    images = []
    chars = 0
    image_count = 0

    def flush():
        nonlocal chars
        if paragraphs or images:
            pages.append(Page(filename, len(pages) + 1, "\n".join(paragraphs), tuple(images)))
            paragraphs.clear()
            images.clear()
            chars = 0

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        parts = archive.infolist()
        if (len(parts) > 350 or sum(part.file_size for part in parts) > 40 * 1024 * 1024
                or any(part.file_size > MAX_BYTES or part.flag_bits & 1 for part in parts)):
            raise ValueError("Word 文件解包后过大或受密码保护。")
        document = xml_part(archive, "word/document.xml")
        relations = {}
        if "word/_rels/document.xml.rels" in archive.namelist():
            for relation in xml_part(archive, "word/_rels/document.xml.rels"):
                target = posixpath.normpath(posixpath.join("word", relation.get("Target", "")))
                if target.startswith("word/media/") and relation.get("TargetMode") != "External":
                    relations[relation.get("Id")] = target
        for paragraph in document.iter(WORD + "p"):
            text = "".join(node.text or "" for node in paragraph.iter() if node.tag in {WORD + "t", MATH + "t"})
            # Native Office equations can have a layout that the flattened text cannot preserve.
            if any(node.tag == MATH + "oMath" for node in paragraph.iter()):
                text = "[公式原格式不可核验] " + text
            names = [relations.get(node.get(REL + "embed")) for node in paragraph.iter(DRAW + "blip")]
            names = [name for name in names if name in archive.namelist()]
            image_count += len(names)
            if image_count > MAX_PAGES or len(text) > 12000:
                raise ValueError("Word 文件的图片过多或有段落过长。")
            if chars + len(text) > 5200 or len(images) + len(names) > 3:
                flush()
            if text.strip():
                paragraphs.append(text)
                chars += len(text)
            for name in names:
                try:
                    images.append(image_data(archive.read(name)))
                except (OSError, ValueError):
                    paragraphs.append("[插图格式无法读取]")
            if len(pages) >= MAX_PAGES:
                raise ValueError(f"每次最多导入 {MAX_PAGES} 页。")
        flush()
    return pages


def read_files(files):
    pages = []
    for filename, data in files:
        suffix = PurePath(filename).suffix.lower()
        try:
            if suffix == ".pdf":
                pages.extend(read_pdf(filename, data))
            elif suffix == ".docx":
                pages.extend(read_docx(filename, data))
            elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                pages.append(photo_page(filename, data))
            else:
                raise ValueError("请使用 PDF、Word（.docx）、JPG、PNG 或 WebP。")
        except (OSError, KeyError, Image.DecompressionBombError, pdfium.PdfiumError,
                zipfile.BadZipFile, ElementTree.ParseError) as error:
            raise ValueError(f"{filename} 无法读取，请检查文件格式或密码。") from error
        if len(pages) > MAX_PAGES or sum(len(page.images) for page in pages) > MAX_PAGES:
            raise ValueError(f"每次最多导入 {MAX_PAGES} 页或张图片。")
    if not pages:
        raise ValueError("没有读到可解析的页面。")
    return pages
