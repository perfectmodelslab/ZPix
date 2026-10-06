"""High-Res Fix: denoise a region a second time, at a higher resolution."""

from collections.abc import Callable
from math import ceil

from PIL import Image, ImageFilter

HIGH_RES_FIX_FACTORS = (1.5, 2.0)
"""Upscale factors offered: beyond, the region drifts from the first pass."""

HIGH_RES_FIX_STRENGTH = 0.4
"""Enough to add details, not enough to recompose the region."""

HIGH_RES_FIX_MIN_STEPS = 4
"""Denoising steps run at least: fewer leave noise in the region."""

CONTEXT_MARGIN = 64
"""Pixels kept around the region, so the model sees what it blends into."""

SIZE_MULTIPLE = 32
"""What every family can split into latent patches."""


def high_res_fix_steps(steps: int, strength: float = HIGH_RES_FIX_STRENGTH) -> int:
    """Get the inference steps to ask for, pipelines running only strength of them."""
    return max(steps, ceil(HIGH_RES_FIX_MIN_STEPS / strength))


def high_res_fix(
    image: Image.Image,
    mask: Image.Image,
    factor: float,
    denoise: Callable[[Image.Image, Image.Image], Image.Image],
) -> Image.Image:
    """Upscale the region in mask, denoise it a second time, then paste it back.

    Only the region and its context are denoised, not the whole image: faster.

    Args:
        image: Image to fix.
        mask: Grayscale image, white over the region to fix.
        factor: How much to upscale the region before denoising it a second time.
        denoise: Denoises an image at its size, where its mask is white.

    Returns:
        Image whose region was fixed, at the same size.
    """
    left, top, right, bottom = mask.getbbox() or (0, 0, *image.size)
    box = (
        max(left - CONTEXT_MARGIN, 0),
        max(top - CONTEXT_MARGIN, 0),
        min(right + CONTEXT_MARGIN, image.width),
        min(bottom + CONTEXT_MARGIN, image.height),
    )
    region = image.crop(box)
    region_mask = mask.crop(box)
    high_res_size = (
        max(round(region.width * factor / SIZE_MULTIPLE), 1) * SIZE_MULTIPLE,
        max(round(region.height * factor / SIZE_MULTIPLE), 1) * SIZE_MULTIPLE,
    )

    fixed_region = denoise(
        region.resize(high_res_size, Image.Resampling.LANCZOS),
        region_mask.resize(high_res_size, Image.Resampling.LANCZOS),
    ).resize(region.size, Image.Resampling.LANCZOS)

    # Feathered, so no seam shows along the region.
    fixed_image = image.copy()
    fixed_image.paste(
        fixed_region, box[:2], region_mask.filter(ImageFilter.GaussianBlur(2))
    )

    return fixed_image
