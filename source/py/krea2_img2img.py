"""Krea 2 image-to-image, assembled from the Diffusers Krea 2 modular blocks.

Diffusers ships Krea 2 as text-to-image only. Image-to-image here starts the
denoising loop from the source image, noised to the level strength spares, as
Diffusers does for Qwen-Image, whose VAE and latent packing Krea 2 shares.
"""

from typing import Any

import torch
from diffusers.image_processor import VaeImageProcessor
from diffusers.models import AutoencoderKLQwenImage
from diffusers.modular_pipelines.krea2.before_denoise import (
    Krea2PrepareLatentsStep,
    Krea2PreparePositionIdsStep,
    Krea2SetTimestepsStep,
    Krea2TextInputsStep,
    Krea2TurboSetTimestepsStep,
    Krea2TurboTextInputsStep,
)
from diffusers.modular_pipelines.krea2.decoders import Krea2DecodeStep
from diffusers.modular_pipelines.krea2.denoise import (
    Krea2DenoiseStep,
    Krea2TurboDenoiseStep,
)
from diffusers.modular_pipelines.krea2.encoders import (
    Krea2TextEncoderStep,
    Krea2TurboTextEncoderStep,
)
from diffusers.modular_pipelines.krea2.modular_blocks_krea2 import (
    Krea2CoreDenoiseStep,
)
from diffusers.modular_pipelines.krea2.modular_blocks_krea2_turbo import (
    Krea2TurboCoreDenoiseStep,
)
from diffusers.modular_pipelines.krea2.modular_pipeline import (
    Krea2TurboModularPipeline,
)
from diffusers.modular_pipelines.modular_pipeline import (
    AutoPipelineBlocks,
    ModularPipeline,
    ModularPipelineBlocks,
    PipelineState,
    SequentialPipelineBlocks,
)
from diffusers.modular_pipelines.modular_pipeline_utils import (
    ComponentSpec,
    InputParam,
    OutputParam,
)
from diffusers.modular_pipelines.qwenimage.before_denoise import get_timesteps
from diffusers.modular_pipelines.qwenimage.encoders import encode_vae_image

# Block states below are typed `Any`: Diffusers sets their attributes at runtime,
# after the block's inputs and outputs, and types them as `dict`.


def pack_latents(latents: torch.Tensor, patch_size: int) -> torch.Tensor:
    """Pack latents (B, C, H, W) into tokens (B, H/p * W/p, C * p * p), as the
    Krea 2 latents step does."""
    batch, channels, height, width = latents.shape
    p = patch_size

    latents = latents.view(batch, channels, height // p, p, width // p, p)
    latents = latents.permute(0, 2, 4, 1, 3, 5)

    return latents.reshape(batch, (height // p) * (width // p), channels * p * p)


class Krea2Img2ImgVaeEncoderStep(ModularPipelineBlocks):
    """Encode the source image, at the generated image size, into Krea 2
    tokens."""

    model_name = "krea2"

    @property
    def description(self) -> str:
        return "Encode the source image and pack it as Krea 2 tokens."

    @property
    def expected_components(self) -> list[ComponentSpec]:
        return [ComponentSpec("vae", AutoencoderKLQwenImage)]

    @property
    def inputs(self) -> list[InputParam]:
        return [
            InputParam.template("image"),
            InputParam.template("height", required=True),
            InputParam.template("width", required=True),
            InputParam.template("generator"),
            InputParam("batch_size", required=True, type_hint=int),
        ]

    @property
    def intermediate_outputs(self) -> list[OutputParam]:
        return [
            OutputParam(
                "image_latents",
                type_hint=torch.Tensor,
                description="Packed latents of the source image.",
            ),
        ]

    @torch.no_grad()
    def __call__(
        self, components: ModularPipeline, state: PipelineState
    ) -> tuple[ModularPipeline, PipelineState]:
        block_state: Any = self.get_block_state(state)
        vae = components.vae
        patch_size = components.patch_size

        image = VaeImageProcessor(
            vae_scale_factor=components.vae_scale_factor * patch_size
        ).preprocess(
            block_state.image, height=block_state.height, width=block_state.width
        )
        image_latents = encode_vae_image(
            image=image,
            vae=vae,
            generator=block_state.generator,
            device=components._execution_device,
            dtype=vae.dtype,
            latent_channels=vae.config.z_dim,
        )

        # Krea 2 latents carry no frame axis, unlike the VAE's: (B, C, 1, H, W).
        image_latents = pack_latents(image_latents[:, :, 0], patch_size)
        block_state.image_latents = image_latents.repeat(block_state.batch_size, 1, 1)

        self.set_block_state(state, block_state)
        return components, state


class Krea2Img2ImgStrengthStep(ModularPipelineBlocks):
    """Skip the first steps, as much as strength spares, then noise the source
    image to the level of the first remaining one.

    The noise the latents step drew is kept, so inpainting can noise the source
    image with it again.
    """

    model_name = "krea2"

    @property
    def description(self) -> str:
        return "Truncate the Krea 2 schedule by strength and noise the source image."

    @property
    def inputs(self) -> list[InputParam]:
        return [
            InputParam.template("strength"),
            InputParam.template("num_inference_steps", required=True),
            InputParam("timesteps", required=True, type_hint=torch.Tensor),
            InputParam("latents", required=True, type_hint=torch.Tensor),
            InputParam.template("image_latents"),
        ]

    @property
    def intermediate_outputs(self) -> list[OutputParam]:
        return [
            OutputParam("timesteps", type_hint=torch.Tensor),
            OutputParam("num_inference_steps", type_hint=int),
            OutputParam(
                "latents",
                type_hint=torch.Tensor,
                description="Source image latents, noised to start from.",
            ),
            OutputParam(
                "initial_noise",
                type_hint=torch.Tensor,
                description="Noise to blend the source image latents with.",
            ),
        ]

    @torch.no_grad()
    def __call__(
        self, components: ModularPipeline, state: PipelineState
    ) -> tuple[ModularPipeline, PipelineState]:
        block_state: Any = self.get_block_state(state)
        scheduler = components.scheduler

        block_state.timesteps, block_state.num_inference_steps = get_timesteps(
            scheduler, block_state.num_inference_steps, block_state.strength
        )

        noise = block_state.latents
        block_state.initial_noise = noise
        block_state.latents = scheduler.scale_noise(
            block_state.image_latents.to(noise),
            block_state.timesteps[:1].repeat(noise.shape[0]),
            noise,
        )

        self.set_block_state(state, block_state)
        return components, state


class Krea2AutoCoreDenoiseStep(AutoPipelineBlocks):
    """Denoise from the source image when one is given, from noise otherwise.

    Args:
        turbo: Whether to create it for the distilled checkpoint, which runs
            without classifier-free guidance.
    """

    def __init__(self, turbo: bool) -> None:
        img2img = SequentialPipelineBlocks.from_blocks_dict(
            {
                "input": Krea2TurboTextInputsStep if turbo else Krea2TextInputsStep,
                # Rounds height and width to what packing takes, before the
                # source image is brought to them.
                "prepare_latents": Krea2PrepareLatentsStep,
                "vae_encoder": Krea2Img2ImgVaeEncoderStep,
                "set_timesteps": (
                    Krea2TurboSetTimestepsStep if turbo else Krea2SetTimestepsStep
                ),
                "strength": Krea2Img2ImgStrengthStep,
                "prepare_position_ids": Krea2PreparePositionIdsStep,
                "denoise": Krea2TurboDenoiseStep if turbo else Krea2DenoiseStep,
            }
        )
        text2image = Krea2TurboCoreDenoiseStep if turbo else Krea2CoreDenoiseStep

        self.block_classes = [img2img, text2image]
        self.block_names = ["img2img", "text2image"]
        self.block_trigger_inputs = ["image", None]
        super().__init__()

    @property
    def description(self) -> str:
        return (
            "Denoise step that runs Krea 2 image-to-image when an image is given,"
            " text-to-image otherwise."
        )


def create_krea2_img2img_blocks(turbo: bool) -> SequentialPipelineBlocks:
    """Create the Krea 2 text-to-image blocks, plus image-to-image.

    Args:
        turbo: Whether to create them for the distilled checkpoint, which runs
            without classifier-free guidance.
    """
    return SequentialPipelineBlocks.from_blocks_dict(
        {
            "text_encoder": (
                Krea2TurboTextEncoderStep if turbo else Krea2TextEncoderStep
            ),
            "denoise": Krea2AutoCoreDenoiseStep(turbo),
            "decode": Krea2DecodeStep,
        }
    )


def create_krea2_img2img_pipe(pipe: ModularPipeline) -> ModularPipeline:
    """Create the Krea 2 image-to-image pipeline from the loaded Krea 2 pipeline.

    It shares the loaded components, so no weights load twice. It keeps the
    pipeline class too, which inpainting tells the distilled checkpoint by:
    `init_pipeline()` would build the non-distilled one.
    """
    turbo = isinstance(pipe, Krea2TurboModularPipeline)
    img2img_pipe = type(pipe)(blocks=create_krea2_img2img_blocks(turbo))
    img2img_pipe.update_components(**pipe.components)

    return img2img_pipe
