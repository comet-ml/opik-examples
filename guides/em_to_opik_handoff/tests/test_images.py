import base64
import io

from PIL import Image

from roadwork_demo.images import draw_overlay, encode_image


def _decode(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def test_encode_downsizes_large_frame(tmp_path):
    p = tmp_path / "big.jpg"
    Image.new("RGB", (4032, 3024)).save(p)
    img = _decode(encode_image(p))
    assert max(img.size) == 1024 and img.format == "JPEG"


def test_encode_keeps_small_frame_size(tmp_path):
    p = tmp_path / "s.jpg"
    Image.new("RGB", (640, 480)).save(p)
    assert _decode(encode_image(p)).size == (640, 480)


def test_encode_converts_png_with_alpha_to_jpeg(tmp_path):
    p = tmp_path / "a.png"
    Image.new("RGBA", (100, 100)).save(p)
    assert _decode(encode_image(p)).format == "JPEG"


def test_draw_overlay_marks_box_and_downsizes(tmp_path):
    p = tmp_path / "f.jpg"
    Image.new("RGB", (2048, 1024), "white").save(p)
    out = draw_overlay(
        p,
        [{"label": "Cone", "confidence": 0.9, "box": [200, 200, 600, 600]}],
        tmp_path / "o.jpg",
    )
    img = Image.open(out)
    assert max(img.size) == 1024
    # box edge at x=200 in the original -> x=100 after 0.5 scaling; should no longer be white
    r, g, b = img.convert("RGB").getpixel((100, 200))
    assert (r, g, b) != (255, 255, 255)


def test_draw_overlay_with_no_detections_still_writes(tmp_path):
    p = tmp_path / "f.jpg"
    Image.new("RGB", (640, 480)).save(p)
    assert draw_overlay(p, [], tmp_path / "o.jpg").exists()
