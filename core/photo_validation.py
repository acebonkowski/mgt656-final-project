from io import BytesIO
import warnings

from django.core.exceptions import ValidationError

from core.photo_storage import MAX_PHOTO_BYTES, StorageUnavailable


def validate_photo(upload):
    if upload.size > MAX_PHOTO_BYTES:
        raise ValidationError("Choose a photo no larger than 5 MB.")
    if upload.content_type not in ("image/jpeg", "image/png"):
        raise ValidationError("Choose a JPEG or PNG photo.")
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise StorageUnavailable("Photo validation is not installed on the server.") from exc
    raw = upload.read(MAX_PHOTO_BYTES + 1)
    if len(raw) > MAX_PHOTO_BYTES:
        raise ValidationError("Choose a photo no larger than 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as img:
                image_format = img.format
                if image_format not in ("JPEG", "PNG"):
                    raise ValidationError("Choose a JPEG or PNG photo.")
                if img.width * img.height > 25_000_000:
                    raise ValidationError("Choose a photo with no more than 25 million pixels.")
                img.verify()
            with Image.open(BytesIO(raw)) as img:
                img.load()
                img = ImageOps.exif_transpose(img)
                img.thumbnail((1024, 1024))
                # Re-encode pixels to remove metadata and embedded non-image content.
                mode = "RGB" if image_format == "JPEG" else "RGBA"
                clean = Image.frombytes(mode, img.size, img.convert(mode).tobytes())
                output = BytesIO()
                clean.save(output, format=image_format)
        if output.tell() > MAX_PHOTO_BYTES:
            raise ValidationError("Choose a smaller photo.")
        return output.getvalue(), "image/jpeg" if image_format == "JPEG" else "image/png"
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValidationError("That file is not a valid JPEG or PNG photo.") from exc


def validate_event_photo(upload):
    if upload.size > MAX_PHOTO_BYTES:
        raise ValidationError("Choose a photo no larger than 5 MB.")
    if upload.content_type not in ("image/jpeg", "image/png", "image/heic", "image/heif"):
        raise ValidationError("Choose a PNG, JPEG or HEIC photo.")
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError as exc:
        raise StorageUnavailable("HEIC photo validation is not installed on the server.") from exc

    raw = upload.read(MAX_PHOTO_BYTES + 1)
    if len(raw) > MAX_PHOTO_BYTES:
        raise ValidationError("Choose a photo no larger than 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as img:
                img_format = img.format
                if img_format not in ("JPEG", "PNG", "HEIF"):
                    raise ValidationError("Choose a PNG, JPEG or HEIC photo.")
                if img.width * img.height > 25_000_000:
                    raise ValidationError("Choose a photo with no more than 25 million pixels.")
                img.verify()
            with Image.open(BytesIO(raw)) as img:
                img.load()
                img = ImageOps.exif_transpose(img)
                img.thumbnail((1024, 1024))
                output = BytesIO()
                if img_format == "HEIF":
                    clean = img.convert("RGB")
                    clean.save(output, format="JPEG", quality=90)
                    content_type = "image/jpeg"
                elif img_format == "JPEG":
                    clean = img.convert("RGB")
                    clean.save(output, format="JPEG", quality=90)
                    content_type = "image/jpeg"
                else:
                    clean = img.convert("RGBA")
                    clean.save(output, format="PNG")
                    content_type = "image/png"
        if output.tell() > MAX_PHOTO_BYTES:
            raise ValidationError("Choose a smaller photo.")
        return output.getvalue(), content_type
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValidationError("That file is not a valid PNG, JPEG or HEIC photo.") from exc
