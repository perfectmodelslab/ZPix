"""Regional Edits: regenerate the region of an image drawn with a lasso tool."""

from inspect import signature
from math import ceil

import gradio as gr
from diffusers.modular_pipelines.modular_pipeline import ModularPipeline
from diffusers.pipelines.flux.pipeline_flux_inpaint import FluxInpaintPipeline
from diffusers.pipelines.flux2.pipeline_flux2_klein_inpaint import (
    Flux2KleinInpaintPipeline,
)
from diffusers.pipelines.pipeline_utils import DiffusionPipeline
from diffusers.pipelines.z_image.pipeline_z_image_inpaint import ZImageInpaintPipeline
from gradio_canvas import Doc
from gradio_lasso_tools import lasso_to_mask
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from source.py.anima_inpaint import create_anima_inpaint_pipe
from source.py.image_model import ImageModel
from source.py.image_utilities import to_rgb
from source.py.krea2_inpaint import create_krea2_inpaint_pipe
from source.py.qwen21_inpaint import create_qwen21_inpaint_pipe

INPAINT_PIPELINES: dict[str, tuple[type[DiffusionPipeline], int]] = {
    "Z-Image": (ZImageInpaintPipeline, 0),
    "FLUX": (FluxInpaintPipeline, 0),
    # Appends the source image to the stream, as a reference.
    "FLUX.2": (Flux2KleinInpaintPipeline, 1),
}
"""Inpaint pipeline of each family whose models support inpainting, except
Anima, Krea 2 and Qwen-Image 2.1, which Diffusers ships no inpaint pipeline for,
and the references it appends to the denoised stream."""

LATENT_CELL = 16
"""Pixels per latent cell, at most: the region regenerated is the cells the
lasso covers, so it can spill that far out of the lasso."""

INPAINT_MAX_PIXELS: dict[str, int] = {"FLUX.2": 1024 * 1024}
"""Pixels the inpaint pipeline of a family scales the source image down to, at
most, whatever size it is asked for."""

FEATHER_RADIUS = 4
"""Blur of the edge the source image is pasted back along, so no seam shows."""


def get_inpaint_steps(strength: float, steps: int) -> int:
    """Get the steps an inpaint pipeline denoises at strength, out of steps:
    strength of them, rounded up.
    """
    # The slack absorbs float error, which can land a hair past a whole step.
    return min(max(ceil(strength * steps - 1e-6), 1), steps)


def sync_inpaint_steps(model: ImageModel, steps: int) -> dict:
    """Synchronize inpainting steps slider to steps, at model's strength."""
    steps = int(steps)

    return gr.update(
        # Gradio refuses a minimum equal to the maximum: with one step, slider
        # goes down to 0, which denoises one step anyway.
        minimum=min(1, steps - 1),
        maximum=steps,
        value=get_inpaint_steps(model.default.inpaint_strength_ratio, steps),
    )


def sync_ui_to_inpainting_mode(
    model: ImageModel, *, lasso_drawn: bool
) -> tuple[dict, dict, dict, dict]:
    """Synchronize UI to inpainting mode.

    Returns:
        Reference images column, inpainting settings row, aspect ratio and
        resolution updates.
    """
    inpainting_mode = lasso_drawn and model.supports_inpainting()

    # A row hidden on startup is not mounted by Gradio, hence the "hidden" class.
    return (
        gr.update(elem_classes=["hidden"] if inpainting_mode else []),
        gr.update(elem_classes=[] if inpainting_mode else ["hidden"]),
        gr.update(visible="hidden" if inpainting_mode else True),
        gr.update(visible="hidden" if inpainting_mode else True),
    )


def get_inpaint_source(
    model: ImageModel,
    lasso: list[list[tuple[int, int]]] | None,
    doc: Doc | None,
) -> Image.Image | None:
    """Get the image of the document displayed in canvas, if user drew a region
    to edit there and model can inpaint it."""
    if not lasso or not model.supports_inpainting() or doc is None:
        return None

    # Upright, as browser displays it, e.g. a photo dropped onto the canvas.
    return to_rgb(ImageOps.exif_transpose(doc.image))


def create_inpaint_pipe(
    pipe: DiffusionPipeline | ModularPipeline, family: str
) -> tuple[DiffusionPipeline | ModularPipeline, int]:
    """Create the inpaint pipeline of a family from the loaded pipeline.

    It shares the loaded components (LoRA included), so no weights load twice.

    Returns:
        Inpaint pipeline, and the references it appends to the denoised stream:
        some read the source image there, rather than only starting from it.
    """
    # These only start from the source image.
    if family == "Anima":
        return create_anima_inpaint_pipe(pipe), 0

    if family == "Krea 2":
        return create_krea2_inpaint_pipe(pipe), 0

    if family == "Qwen-Image 2.1":
        return create_qwen21_inpaint_pipe(pipe), 0

    pipeline_class, references = INPAINT_PIPELINES[family]
    # Only those the pipeline takes: a modular one holds others, e.g. a guider.
    accepted = signature(pipeline_class.__init__).parameters
    components = {
        name: component
        for name, component in pipe.components.items()
        if name in accepted
    }

    return pipeline_class(**components), references


def get_inpaint_size(inpaint_source: Image.Image, family: str) -> tuple[int, int]:
    """Get the size the inpaint pipeline of a family generates at, from the
    source image: the one to fit memory to, rather than the source image's.

    Floored to whole latent cells, as pipelines refuse or floor other sizes, and
    scaled down to what the pipeline caps it at, if it does.
    """
    width, height = inpaint_source.size
    max_pixels = INPAINT_MAX_PIXELS.get(family)

    if max_pixels and width * height > max_pixels:
        scale = (max_pixels / (width * height)) ** 0.5
        width, height = width * scale, height * scale

    return (
        max(int(width) // LATENT_CELL, 1) * LATENT_CELL,
        max(int(height) // LATENT_CELL, 1) * LATENT_CELL,
    )


def get_inpaint_kwargs(
    inpaint_source: Image.Image,
    mask: Image.Image,
    size: tuple[int, int],
    inpaint_steps: int,
    steps: int,
) -> dict[str, object]:
    """Get the inpaint pipeline arguments to regenerate the region in mask.

    Model gets the whole image, so the region fits in it, at the size given by
    get_inpaint_size, so the pipeline generates at the size memory fits.
    """
    if inpaint_source.size != size:
        inpaint_source = inpaint_source.resize(size, Image.Resampling.LANCZOS)
        mask = mask.resize(size, Image.Resampling.LANCZOS)

    return {
        "image": inpaint_source,
        "mask_image": mask,
        "width": size[0],
        "height": size[1],
        # Pipelines denoise strength times steps, rounded up: aim half a step
        # below inpaint steps, as float error can push exactly them to one more.
        # At all steps, region is regenerated from scratch, guided by its context.
        "strength": (max(inpaint_steps, 1) - 0.5) / steps,
    }


def keep_outside_region(
    inpaint_source: Image.Image,
    image: Image.Image,
    lasso: list[list[tuple[int, int]]],
) -> Image.Image:
    """Paste the source image back outside the region regenerated in image.

    The whole image goes through the VAE, so its pixels drift even outside the
    region: pasted back, they match the source image, edit after edit.
    """
    # Generated at the size given by get_inpaint_size.
    if image.size != inpaint_source.size:
        image = image.resize(inpaint_source.size, Image.Resampling.LANCZOS)

    region_mask = lasso_to_mask(lasso, inpaint_source.size)
    # Grown past what spilled out of the lasso, so the feather lies where both
    # images only differ by drift. Goes on to the second vertex, else the first
    # one is the only joint not rounded.
    for outline in lasso:
        ImageDraw.Draw(region_mask).line(
            [*outline, *outline[:2]],
            fill=255,
            width=2 * (LATENT_CELL + 2 * FEATHER_RADIUS) + 1,
            joint="curve",
        )

    kept_image = inpaint_source.copy()
    kept_image.paste(
        image, mask=region_mask.filter(ImageFilter.GaussianBlur(FEATHER_RADIUS))
    )

    return kept_image
