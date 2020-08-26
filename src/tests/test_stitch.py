import pytest

import numpy as np
import cv2 as cv
import rasterio
import rasterio.warp
import rasterio.transform
import skimage.metrics

from ..stitch import Stitcher


@pytest.fixture
def cache_dir(tmp_path):
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def stitcher(cache_dir):
    return Stitcher(scales=[0.9, 1],
                    crop={'top': 0, 'bottom': 1, 'left': 0.1, 'right': 1},
                    cache_dir=str(cache_dir))


@pytest.fixture
def raw_img(data_dir):
    img = cv.imread(str(data_dir / 'test_stitch_main.jpg'),
                    cv.IMREAD_GRAYSCALE)
    return img


def sub_img(transform, width, height, raw_img):
    sub_img = np.zeros((height, width), np.uint8)  # init output image
    rasterio.warp.reproject(
        source=raw_img,
        destination=sub_img,
        src_transform=rasterio.transform.Affine.identity(),
        src_crs={'init': 'EPSG:3857'},  # place holder, no meaning
        dst_transform=transform,
        dst_crs={'init': 'EPSG:3857'},  # place holder, no meaning
        resampling=rasterio.warp.Resampling.nearest)
    return sub_img


@pytest.mark.parametrize(
    'transforms,widths,heights,match,show_file',
    [
        pytest.param(
            (rasterio.transform.Affine(0.9, 0, 0, 0, 0.9, 50),
             rasterio.transform.Affine(1.1, -0.1, 200, 0.1, 1.1, 10)),
            (500, 400),
            (700, 800),
            True,
            'test_stitch_pair0'
        ),
        pytest.param(
            (rasterio.transform.Affine(0.9, 0, 0, 0, 0.9, 50),
             rasterio.transform.Affine(0.1, -1.1, 300, 1.1, 0.1, 700)),
            (500, 400),
            (300, 300),
            False,
            'test_stitch_pair1'
        ),
    ],
)
def test_estimate_affine(transforms, widths, heights, match, show_file,
                         stitcher, raw_img, data_dir, tmp_path):
    # this function is quite hard to test as it is non deterministic

    # collect images
    trans0, trans1 = transforms
    w0, w1 = widths
    h0, h1 = heights
    sub_img0 = sub_img(trans0, w0, h0, raw_img)
    sub_img1 = sub_img(trans1, w1, h1, raw_img)

    # 1. w/ verbose = False, show = True
    trans = stitcher.estimate_affine(
        sub_img0, sub_img1, show=True,
        # images generated by replacing tmp_path with data_dir
        show_file=str(tmp_path / show_file))

    # check output image stability: match
    img_match = cv.imread(str(tmp_path / (show_file + '_match.png')),
                          cv.IMREAD_GRAYSCALE)
    exp_match = cv.imread(str(data_dir / (show_file + '_match.png')),
                          cv.IMREAD_GRAYSCALE)
    assert skimage.metrics.structural_similarity(
        img_match, exp_match) > 0.95
    if match:
        # check output image stability: overlay
        assert trans == pytest.approx(~trans0 * trans1, rel=0.02)
        img_overlay = cv.imread(str(tmp_path / (show_file + '_overlay.png')),
                                cv.IMREAD_GRAYSCALE)
        exp_overlay = cv.imread(str(data_dir / (show_file + '_overlay.png')),
                                cv.IMREAD_GRAYSCALE)
        assert skimage.metrics.structural_similarity(
            img_overlay, exp_overlay) > 0.95
    else:
        assert trans is None

    # 2. w/ verbose = True, show = False
    trans, diag = stitcher.estimate_affine(sub_img0, sub_img1, verbose=True)
    if match:
        assert 'n_inlier' in diag.keys()
    assert 'n_match' in diag.keys()


@pytest.mark.parametrize(
    'transforms,widths,heights,match,scale',
    [
        pytest.param(
            (rasterio.transform.Affine(0.9, 0, 0, 0, 0.9, 50),
             rasterio.transform.Affine(1.1, -0.1, 200, 0.1, 1.1, 10)),
            (500, 400),
            (700, 800),
            True,
            0.9,
        ),
        pytest.param(
            (rasterio.transform.Affine(0.9, 0, 0, 0, 0.9, 50),
             rasterio.transform.Affine(0.1, -1.1, 300, 1.1, 0.1, 700)),
            (500, 400),
            (300, 300),
            False,
            1,
        ),
    ],
)
def test_stitch_pair(transforms, widths, heights, match, scale,
                     raw_img, tmp_path, stitcher):
    # this function is quite hard to test as it is non deterministic

    # collect images
    trans0, trans1 = transforms
    w0, w1 = widths
    h0, h1 = heights
    sub_img0 = sub_img(trans0, w0, h0, raw_img)
    sub_img1 = sub_img(trans1, w1, h1, raw_img)
    # save images
    f0 = str(tmp_path / 'test_stitch_img0.png')
    cv.imwrite(f0, sub_img0)
    f1 = str(tmp_path / 'test_stitch_img1.png')
    cv.imwrite(f1, sub_img1)

    # 1. w/ verbose = True
    trans, diag = stitcher.stitch_pair(f0, f1, verbose=True)
    assert scale == pytest.approx(diag['scale'])
    if match:
        assert 'n_inlier' in diag.keys()
    assert ({'n_match', 'img0', 'img1'}).issubset(list(diag.keys()))

    # 2. w/ verbose = False
    trans = stitcher.stitch_pair(f0, f1, verbose=False)
    if match:
        assert trans == pytest.approx(~trans0 * trans1, rel=0.02)
    else:
        assert trans is None
