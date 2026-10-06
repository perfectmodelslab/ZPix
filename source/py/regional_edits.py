"""Regional Edits: regenerate the region of an image drawn with LassoTool."""

import gradio as gr
from diffusers.modular_pipelines.modular_pipeline import ModularPipeline
from diffusers.pipelines.flux2.pipeline_flux2_klein_inpaint import (
    Flux2KleinInpaintPipeline,
)
from diffusers.pipelines.pipeline_utils import DiffusionPipeline
from diffusers.pipelines.z_image.pipeline_z_image_inpaint import ZImageInpaintPipeline
from PIL import Image

from source.py.anima_inpaint import create_anima_inpaint_pipe
from source.py.image_model import ImageModel
from source.py.krea2_inpaint import create_krea2_inpaint_pipe
from source.py.qwen21_inpaint import create_qwen21_inpaint_pipe

INPAINT_PIPELINES: dict[str, tuple[type[DiffusionPipeline], int]] = {
    "Z-Image": (ZImageInpaintPipeline, 0),
    # Appends the source image to the stream, as a reference.
    "FLUX.2": (Flux2KleinInpaintPipeline, 1),
}
"""Inpaint pipeline of each family whose models support inpainting, except
Anima, Krea 2 and Qwen-Image 2.1, which Diffusers ships no inpaint pipeline for,
and the references it appends to the denoised stream."""


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
    lasso: list[tuple[int, int]] | None,
    gallery_images: list[tuple] | None,
    selected_image_index: int | None,
) -> Image.Image | None:
    """Get the image displayed in gallery, if user drew a region to edit there
    and model can inpaint it."""
    if (
        not lasso
        or not model.supports_inpainting()
        or not gallery_images
        or selected_image_index is None
    ):
        return None

    image_path, _caption = gallery_images[selected_image_index]

    return Image.open(image_path).convert("RGB")


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
    names = ("scheduler", "vae", "text_encoder", "tokenizer", "transformer")

    return pipeline_class(**{name: pipe.components[name] for name in names}), references


def get_inpaint_kwargs(
    inpaint_source: Image.Image, mask: Image.Image, strength: float
) -> dict[str, object]:
    """Get the inpaint pipeline arguments to regenerate the region in mask.

    Model gets the whole image, at its size, so the region fits in it.
    """
    return {
        "image": inpaint_source,
        "mask_image": mask,
        "width": inpaint_source.width,
        "height": inpaint_source.height,
        # At 1, region is regenerated from scratch, guided by its context.
        "strength": strength,
    }
