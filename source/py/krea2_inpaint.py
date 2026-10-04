"""Krea 2 inpainting, assembled from the Diffusers Krea 2 modular blocks.

Diffusers ships Krea 2 as text-to-image only. Inpainting here is image-to-image
whose latents outside the mask are reset, after each step, to the source image
noised to the next step's level, as Diffusers does for Qwen-Image, whose VAE
and latent packing Krea 2 shares. The transformer never sees the mask.
"""

from typing import Any

import torch
import torch.nn.functional as F
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
    Krea2DenoiseLoopWrapper,
    Krea2LoopAfterDenoiser,
    Krea2LoopBeforeDenoiser,
    Krea2LoopDenoiser,
    Krea2TurboLoopDenoiser,
)
from diffusers.modular_pipelines.krea2.encoders import (
    Krea2TextEncoderStep,
    Krea2TurboTextEncoderStep,
)
from diffusers.modular_pipelines.krea2.modular_pipeline import (
    Krea2TurboModularPipeline,
)
from diffusers.modular_pipelines.modular_pipeline import (
    BlockState,
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
from diffusers.pipelines.pipeline_utils import DiffusionPipeline

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


class Krea2InpaintPrepareImageStep(ModularPipelineBlocks):
    """Encode the source image and bring the mask image down to the latent
    tokens: 1 where to regenerate."""

    model_name = "krea2"

    @property
    def description(self) -> str:
        return "Encode the source image and pack it, with the mask, as Krea 2 tokens."

    @property
    def expected_components(self) -> list[ComponentSpec]:
        return [ComponentSpec("vae", AutoencoderKLQwenImage)]

    @property
    def inputs(self) -> list[InputParam]:
        return [
            InputParam.template("image"),
            InputParam.template("mask_image"),
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
            OutputParam(
                "mask",
                type_hint=torch.Tensor,
                description="Packed mask, 1 where to regenerate, 0 where to keep.",
            ),
        ]

    @torch.no_grad()
    def __call__(
        self, components: ModularPipeline, state: PipelineState
    ) -> tuple[ModularPipeline, PipelineState]:
        block_state: Any = self.get_block_state(state)
        vae = components.vae
        vae_scale_factor = components.vae_scale_factor
        patch_size = components.patch_size
        height, width = block_state.height, block_state.width

        image = VaeImageProcessor(
            vae_scale_factor=vae_scale_factor * patch_size
        ).preprocess(block_state.image, height=height, width=width)
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

        # Same processing as the Qwen-Image inpaint pipeline.
        mask_processor = VaeImageProcessor(
            vae_scale_factor=vae_scale_factor * patch_size,
            do_normalize=False,
            do_binarize=True,
            do_convert_grayscale=True,
        )
        mask = mask_processor.preprocess(
            block_state.mask_image, height=height, width=width
        )
        mask = F.interpolate(
            mask,
            size=(height // vae_scale_factor, width // vae_scale_factor),
            mode="nearest",
        )

        # Each token packs all channels: so must the mask.
        mask = mask.repeat(1, vae.config.z_dim, 1, 1)
        block_state.mask = pack_latents(mask, patch_size).to(
            device=components._execution_device, dtype=torch.float32
        )

        self.set_block_state(state, block_state)
        return components, state


class Krea2InpaintStrengthStep(ModularPipelineBlocks):
    """Skip the first steps, as much as strength spares, then noise the source
    image to the level of the first remaining one.

    The noise the latents step drew is kept, so the denoising loop can noise
    the source image with it again.
    """

    model_name = "krea2"

    @property
    def description(self) -> str:
        return "Truncate the Krea 2 schedule by strength and noise the source image."

    @property
    def inputs(self) -> list[InputParam]:
        return [
            InputParam.template("strength", default=0.9),
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


class Krea2LoopAfterDenoiserInpaint(ModularPipelineBlocks):
    """Reset the latents outside the mask to the source image, noised to the
    level of the next step."""

    model_name = "krea2"

    @property
    def description(self) -> str:
        return (
            "Step within the denoising loop that keeps Krea 2 latents outside the mask."
        )

    @property
    def inputs(self) -> list[InputParam]:
        return [
            InputParam(
                "mask",
                required=True,
                type_hint=torch.Tensor,
                description="Packed mask, 1 where to regenerate, 0 where to keep.",
            ),
            InputParam.template("image_latents"),
            InputParam(
                "initial_noise",
                required=True,
                type_hint=torch.Tensor,
                description="Noise to blend the source image latents with.",
            ),
        ]

    @property
    def intermediate_outputs(self) -> list[OutputParam]:
        return [OutputParam.template("latents")]

    @torch.no_grad()
    def __call__(
        self, components: ModularPipeline, block_state: Any, i: int, t: torch.Tensor
    ) -> tuple[ModularPipeline, BlockState]:
        kept = block_state.image_latents.to(block_state.latents)

        # Past the last step, latents are clean: so is the source image.
        if i < len(block_state.timesteps) - 1:
            kept = components.scheduler.scale_noise(
                kept,
                torch.tensor([block_state.timesteps[i + 1]]),
                block_state.initial_noise,
            )

        mask = block_state.mask.to(block_state.latents)
        block_state.latents = (1 - mask) * kept + mask * block_state.latents

        return components, block_state


def create_krea2_inpaint_blocks(turbo: bool) -> SequentialPipelineBlocks:
    """Create the Krea 2 text-to-image blocks, plus the source image and mask.

    Args:
        turbo: Whether to create them for the distilled checkpoint, which runs
            without classifier-free guidance.
    """
    # The loop keeps this dict as is: it takes instances, not classes.
    denoise = Krea2DenoiseLoopWrapper.from_blocks_dict(
        {
            "before_denoiser": Krea2LoopBeforeDenoiser(),
            "denoiser": Krea2TurboLoopDenoiser() if turbo else Krea2LoopDenoiser(),
            "after_denoiser": Krea2LoopAfterDenoiser(),
            "inpaint": Krea2LoopAfterDenoiserInpaint(),
        }
    )

    return SequentialPipelineBlocks.from_blocks_dict(
        {
            "text_encoder": (
                Krea2TurboTextEncoderStep if turbo else Krea2TextEncoderStep
            ),
            "input": Krea2TurboTextInputsStep if turbo else Krea2TextInputsStep,
            # Rounds height and width to what packing takes, before the source
            # image and mask are brought to them.
            "prepare_latents": Krea2PrepareLatentsStep,
            "prepare_image": Krea2InpaintPrepareImageStep,
            "set_timesteps": (
                Krea2TurboSetTimestepsStep if turbo else Krea2SetTimestepsStep
            ),
            "strength": Krea2InpaintStrengthStep,
            "prepare_position_ids": Krea2PreparePositionIdsStep,
            "denoise": denoise,
            "decode": Krea2DecodeStep,
        }
    )


def create_krea2_inpaint_pipe(
    pipe: DiffusionPipeline | ModularPipeline,
) -> ModularPipeline:
    """Create the Krea 2 inpaint pipeline from the loaded Krea 2 pipeline.

    It shares the loaded components (LoRA and attention processors included),
    so no weights load twice.
    """
    turbo = isinstance(pipe, Krea2TurboModularPipeline)
    inpaint_pipe = create_krea2_inpaint_blocks(turbo).init_pipeline()
    inpaint_pipe.update_components(**pipe.components)

    return inpaint_pipe
