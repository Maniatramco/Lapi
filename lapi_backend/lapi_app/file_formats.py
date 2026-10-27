"""Supported document types, and a check that a PDF, DOCX or image file really is one
before it is stored or indexed.

A file's extension says nothing about its contents: a saved web link, a web page or a
renamed archive can arrive named .pdf. A file that holds plain text is indexed as that
text (plain_text); anything else that is not the named format is refused with what the
file actually is.
"""
import io
import zipfile

IMAGES = ('png', 'jpg', 'jpeg', 'webp')  # Read with OCR; one image is one page.
SUPPORTED = ('pdf', 'docx', 'txt', 'json') + IMAGES
SUPPORTED_LABEL = 'PDF, DOCX, UTF-8 TXT, JSON and image (PNG, JPG, WEBP)'
OLE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'  # Legacy Office (.doc, .xls) compound file


def extension(name):
    return name.rsplit('.', 1)[-1].lower() if '.' in name else ''


def supported(name):
    return extension(name) in SUPPORTED


def image_kind(raw):
    """The image format named by the file's signature, or None."""
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if raw.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'webp'
    return None


def _text(raw):
    """The file as text when it is plain text, otherwise None."""
    try:
        text = raw[:4096].decode('utf-8-sig')
    except UnicodeDecodeError:
        return None
    return text if all(c.isprintable() or c.isspace() for c in text) else None


def plain_text(name, raw):
    """The whole file as text when a .pdf, .docx or image file actually holds plain text,
    such as a saved web link. Lapi indexes and extracts that text as it is; it never
    follows links found in it."""
    if extension(name) not in ('pdf', 'docx', *IMAGES) or problem(name, raw) is None:
        return None
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return None
    return text if text.strip() and all(c.isprintable() or c.isspace() for c in text) else None


def _actually(raw):
    """A short description of what the contents are, when recognisable."""
    head = raw[:1024].lstrip()
    if raw[:1024].find(b'%PDF-') >= 0:
        return 'a PDF file'
    if raw.startswith(b'PK\x03\x04'):
        return 'a ZIP archive'
    if raw.startswith(OLE):
        return 'an older Microsoft Office file (such as .doc)'
    if image_kind(raw):
        return 'a ' + image_kind(raw).upper() + ' image'
    text = _text(raw)
    if text is None:
        return None
    stripped = text.strip()
    if stripped.lower().startswith(('http://', 'https://')) and len(stripped.split()) == 1:
        return 'only a web link'
    if head[:1].lower() == b'<' and b'<html' in raw[:2048].lower():
        return 'a web page'
    return 'plain text'


def problem(name, raw):
    """Why a .pdf, .docx or image file is not that format, or None when it looks right."""
    ext = name.rsplit('.', 1)[-1].lower()
    if ext in IMAGES:
        kind = image_kind(raw)
        if kind == ('jpg' if ext == 'jpeg' else ext):
            return None
        if kind:
            return f'"{name}" is a {kind.upper()} image with a .{ext} name. Rename it to .{kind} and upload it again.'
        found = _actually(raw)
        if found == 'only a web link':
            return f'"{name}" is not a real image: it only contains a web link. Open the link, download the actual image and upload that instead.'
        if found == 'a PDF file':
            return f'"{name}" is a PDF file with an image name. Rename it to .pdf and upload it again.'
        if found:
            return f'"{name}" is not a real {ext.upper()} image: it is {found}. Upload the original image instead.'
        return f'"{name}" is not a real {ext.upper()} image: its contents are not in an image format. Upload the original image instead.'
    if ext == 'pdf':
        # The PDF header may follow a few bytes of junk; readers search the first 1 KB.
        if raw[:1024].find(b'%PDF-') >= 0:
            return None
        found = _actually(raw)
        if image_kind(raw):
            return f'"{name}" is {found} with a .pdf name. Rename it to .{image_kind(raw)} and upload it again.'
        if found == 'only a web link':
            return f'"{name}" is not a real PDF: it only contains a web link. Open the link, download the actual PDF and upload that instead.'
        if found == 'a web page':
            return f'"{name}" is not a real PDF: it is a web page saved with a .pdf name. Download the actual PDF and upload that instead.'
        if found == 'a ZIP archive':
            return f'"{name}" is not a real PDF: it is a ZIP or Word (DOCX) file renamed to .pdf. Give it its correct extension, or export it as PDF.'
        if found:
            return f'"{name}" is not a real PDF: it is {found}. Upload the original PDF instead.'
        return f'"{name}" is not a real PDF: its contents are not in PDF format. Upload the original PDF instead.'
    if ext == 'docx':
        if raw.startswith(b'PK\x03\x04'):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    names = set(archive.namelist())
            except zipfile.BadZipFile:
                return f'"{name}" is damaged and cannot be opened as a Word (DOCX) document. Download or export it again.'
            if 'word/document.xml' in names and '[Content_Types].xml' in names:
                return None
            return f'"{name}" is not a Word (DOCX) document: it is a different kind of ZIP archive. Export it from Word as DOCX or PDF.'
        found = _actually(raw)
        if image_kind(raw):
            return f'"{name}" is {found} with a .docx name. Rename it to .{image_kind(raw)} and upload it again.'
        if found == 'a PDF file':
            return f'"{name}" is a PDF file with a .docx name. Rename it to .pdf and upload it again.'
        if found == 'an older Microsoft Office file (such as .doc)':
            return f'"{name}" is an older Word (.doc) file renamed to .docx. Open it in Word and save it as DOCX or PDF.'
        if found == 'only a web link':
            return f'"{name}" is not a real Word (DOCX) document: it only contains a web link. Open the link, download the actual document and upload that instead.'
        if found:
            return f'"{name}" is not a real Word (DOCX) document: it is {found}. Upload the original DOCX instead.'
        return f'"{name}" is not a real Word (DOCX) document: its contents are not in DOCX format. Upload the original DOCX instead.'
    return None


def check(name, raw):
    message = problem(name, raw)
    if message:
        raise ValueError(message)
