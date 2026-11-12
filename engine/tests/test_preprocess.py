import numpy as np
import pytest
from PIL import Image

from synth import KWITANSI, document, save
from vouchocr.preprocess import ImageLoadError, flatten_shadows, load_image, needs_flattening, prepare


def gray(im):
    return np.asarray(im.convert("L"))


def test_box_maps_back_to_original():
    im = np.asarray(document(KWITANSI, size=(4000, 2800), font_size=90))[:, :, ::-1].copy()
    prep = prepare(im)
    assert prep.scale < 1 and max(prep.image.shape[:2]) == 3000
    pts = np.array([[100.0, 200.0], [1500.0, 900.0]])
    fwd = pts @ prep.matrix[:, :2].T + prep.matrix[:, 2]
    back = np.array(prep.to_original(fwd))
    assert np.allclose(back, pts, atol=0.2)


def test_shadow_detected_and_flattened():
    shaded = gray(document(KWITANSI, shadow=True))
    assert needs_flattening(shaded)
    assert not needs_flattening(gray(document(KWITANSI)))
    flat = flatten_shadows(shaded)
    # Latar di pojok gelap jadi hampir seterang pojok terang
    assert abs(int(np.median(flat[-60:, -60:])) - int(np.median(flat[:60, :60]))) < 25


def test_load_applies_exif_orientation(tmp_path):
    im = document(["ABC"], size=(400, 200))
    exif = Image.Exif(); exif[0x0112] = 6  # diputar 90 derajat
    p = tmp_path / "r.jpg"; im.save(p, exif=exif)
    loaded = load_image(p)
    assert loaded.size == (200, 400)


def test_load_hashes_file_bytes(tmp_path):
    import hashlib
    p = save(document(["X"]), tmp_path / "a.jpg")
    assert load_image(p).sha256 == hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.parametrize("content, word", [(b"", "kosong"), (b"bukan gambar", "bukan foto"),
                                           (None, "tidak ditemukan")])
def test_load_errors_explain(tmp_path, content, word):
    p = tmp_path / "x.jpg"
    if content is not None:
        p.write_bytes(content)
    with pytest.raises(ImageLoadError, match=word):
        load_image(p)


def test_truncated_jpeg(tmp_path):
    p = save(document(KWITANSI), tmp_path / "t.jpg")
    p.write_bytes(p.read_bytes()[:2000])
    with pytest.raises(ImageLoadError):
        load_image(p)


def test_blur_detected():
    from vouchocr.preprocess import BLUR_THRESHOLD, blur_score
    assert blur_score(gray(document(KWITANSI))) > BLUR_THRESHOLD
    assert blur_score(gray(document(KWITANSI, blur=3))) < BLUR_THRESHOLD


def test_flattened_variant_keeps_geometry():
    im = np.asarray(document(KWITANSI, shadow=True))[:, :, ::-1].copy()
    prep = prepare(im)
    assert prep.has_shadow and prep.flattened().shape == prep.image.shape
