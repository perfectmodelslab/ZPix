"""Regional Edits: regenerate the region of an image drawn with MaskBoundingBox."""

import gradio as gr
from diffusers.image_processor import VaeImageProcessor
from diffusers.modular_pipelines.modular_pipeline import ModularPipeline
from diffusers.pipelines.flux2.pipeline_flux2_klein_inpaint import (
    Flux2KleinInpaintPipeline,
)
from diffusers.pipelines.pipeline_utils import DiffusionPipeline
from diffusers.pipelines.z_image.pipeline_z_image_inpaint import ZImageInpaintPipeline
from gradio_maskboundingbox import mask_bbox_to_image
from PIL import Image, ImageDraw

from source.py.anima_inpaint import create_anima_inpaint_pipe
from source.py.image_model import ImageModel
from source.py.krea2_inpaint import create_krea2_inpaint_pipe
from source.py.qwen21_inpaint import create_qwen21_inpaint_pipe

INPAINT_PIPELINES: dict[str, type[DiffusionPipeline]] = {
    "Z-Image": ZImageInpaintPipeline,
    "FLUX.2": Flux2KleinInpaintPipeline,
}
"""Inpaint pipeline of each family whose models support inpainting, except
Anima, Krea 2 and Qwen-Image 2.1, which Diffusers ships no inpaint pipeline for."""

INPAINT_MARGIN = 64
"""Context kept around the region to edit, in pixels of the image."""

BLEND_WIDTH = 48
"""Width of the gradient blending the regenerated region into the image,
in pixels of the image. Region is regenerated this much beyond the drawn box,
so the box itself is fully edited."""


def sync_ui_to_inpainting_mode(
    model: ImageModel, *, mask_bbox_drawn: bool
) -> tuple[dict, dict, dict, dict]:
    """Synchronize UI to inpainting mode.

    Returns:
        Reference images column, inpainting strength row, aspect ratio and
        resolution updates.
    """
    inpainting_mode = mask_bbox_drawn and model.supports_inpainting()

    # A row hidden on startup is not mounted by Gradio, hence the "hidden" class.
    return (
        gr.update(elem_classes=["hidden"] if inpainting_mode else []),
        gr.update(elem_classes=[] if inpainting_mode else ["hidden"]),
        gr.update(interactive=not inpainting_mode),
        gr.update(interactive=not inpainting_mode),
    )


def get_inpaint_source(
    model: ImageModel,
    mask_bbox: dict[str, int] | None,
    gallery_images: list[tuple] | None,
    selected_image_index: int | None,
) -> Image.Image | None:
    """Get the image displayed in gallery, if user drew a region to edit there
    and model can inpaint it."""
    if (
        not mask_bbox
        or not model.supports_inpainting()
        or not gallery_images
        or selected_image_index is None
    ):
        return None

    image_path, _caption = gallery_images[selected_image_index]

    return Image.open(image_path).convert("RGB")


def create_inpaint_pipe(
    pipe: DiffusionPipeline | ModularPipeline, family: str
) -> DiffusionPipeline | ModularPipeline:
    """Create the inpaint pipeline of a family from the loaded pipeline.

    It shares the loaded components (LoRA included), so no weights load twice.
    """
    if family == "Anima":
        return create_anima_inpaint_pipe(pipe)

    if family == "Krea 2":
        return create_krea2_inpaint_pipe(pipe)

    if family == "Qwen-Image 2.1":
        return create_qwen21_inpaint_pipe(pipe)

    names = ("scheduler", "vae", "text_encoder", "tokenizer", "transformer")

    return INPAINT_PIPELINES[family](**{name: pipe.components[name] for name in names})


def grow_bbox(mask_bbox: dict[str, int], by: int) -> dict[str, int]:
    """Grow a bounding box by some pixels on each side."""
    return {
        "x": mask_bbox["x"] - by,
        "y": mask_bbox["y"] - by,
        "width": mask_bbox["width"] + 2 * by,
        "height": mask_bbox["height"] + 2 * by,
    }


def get_regen_mask(
    inpaint_source: Image.Image, mask_bbox: dict[str, int]
) -> Image.Image:
    """Get the mask of the region to regenerate: drawn box and blend band."""
    return mask_bbox_to_image(grow_bbox(mask_bbox, BLEND_WIDTH), inpaint_source.size)


def get_blend_mask(
    inpaint_source: Image.Image, mask_bbox: dict[str, int]
) -> Image.Image:
    """Get the mask pasting the regenerated region: opaque in drawn box,
    fading to transparent across blend band."""
    mask = Image.new("L", inpaint_source.size, 0)
    draw = ImageDraw.Draw(mask)

    # From outermost to innermost, each rectangle a step more opaque.
    for by in range(BLEND_WIDTH, -1, -1):
        bbox = grow_bbox(mask_bbox, by)
        right = bbox["x"] + bbox["width"] - 1
        bottom = bbox["y"] + bbox["height"] - 1
        # Smoothstep: a linear fade starts and stops abruptly, which the eye
        # sees as lines at both edges of the band.
        progress = (BLEND_WIDTH - by) / BLEND_WIDTH
        opacity = round(255 * progress * progress * (3 - 2 * progress))
        draw.rectangle((bbox["x"], bbox["y"], right, bottom), fill=opacity)

    return mask


def get_crop_box(
    inpaint_source: Image.Image, mask_bbox: dict[str, int]
) -> tuple[int, int, int, int]:
    """Get the region to regenerate with some context around, at image aspect
    ratio."""
    mask = get_regen_mask(inpaint_source, mask_bbox)

    return VaeImageProcessor.get_crop_region(
        mask, *inpaint_source.size, pad=INPAINT_MARGIN
    )


def get_inpaint_kwargs(
    inpaint_source: Image.Image, mask_bbox: dict[str, int], strength: float
) -> dict[str, object]:
    """Get the inpaint pipeline arguments to regenerate the drawn region.

    Region and its context are cropped then upscaled to image resolution,
    so a small region (e.g. a distant face) gets as many pixels as the model
    can detail.
    """
    crop_box = get_crop_box(inpaint_source, mask_bbox)
    mask = get_regen_mask(inpaint_source, mask_bbox)

    return {
        "image": inpaint_source.crop(crop_box).resize(
            inpaint_source.size, Image.Resampling.LANCZOS
        ),
        "mask_image": mask.crop(crop_box).resize(
            inpaint_source.size, Image.Resampling.NEAREST
        ),
        # At 1, region is regenerated from scratch, guided by its context.
        "strength": strength,
    }


def paste_inpainted(
    inpaint_source: Image.Image, mask_bbox: dict[str, int], inpainted: Image.Image
) -> Image.Image:
    """Paste the regenerated region back into the image, which stays as is
    outside it, blending them across blend band."""
    crop_box = get_crop_box(inpaint_source, mask_bbox)
    left, top, right, bottom = crop_box
    region = inpainted.resize((right - left, bottom - top), Image.Resampling.LANCZOS)

    mask = get_blend_mask(inpaint_source, mask_bbox).crop(crop_box)

    result = inpaint_source.copy()
    result.paste(region, (left, top), mask)

    return result
