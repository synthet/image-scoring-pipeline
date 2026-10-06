"""Generated thumbnails must have upright pixels even when the source uses EXIF rotation."""

from PIL import Image

from modules import thumbnails


def test_generate_jpeg_thumbnail_bakes_exif_orientation(tmp_path, monkeypatch):
    source = tmp_path / "portrait.jpg"
    thumbnail = tmp_path / "thumbnail.jpg"
    image = Image.new("RGB", (40, 20), "red")
    exif = Image.Exif()
    exif[274] = 8
    image.save(source, exif=exif)
    monkeypatch.setattr(thumbnails, "get_thumb_path", lambda _: str(thumbnail))

    result = thumbnails.generate_thumbnail(str(source))

    assert result == str(thumbnail)
    with Image.open(thumbnail) as generated:
        assert generated.size == (20, 40)
        assert generated.getexif().get(274) in (None, 1)
