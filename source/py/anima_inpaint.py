"""Anima inpainting, assembled from the Diffusers Anima modular blocks.

Diffusers ships Anima as text-to-image and image-to-image only. Inpainting here
is image-to-image whose latents outside the mask are reset, after each step, to
the source image noised to the next step's level, as Diffusers does for Z-Image
and Qwen-Image. The transformer never sees the mask.
"""

from typing import Any

import torch
import torch.nn.functional as F
from diffusers.image_processor import VaeImageProcessor
from diffusers.modular_pipelines.anima.before_denoise import (
    AnimaImageInputStep,
    AnimaImg2ImgPrepareLatentsStep,
    AnimaImg2ImgSetTimestepsStep,
    AnimaTextConditioningStep,
    AnimaTextInputStep,
)
from diffusers.modular_pipelines.anima.denoise import (
    AnimaDenoiseLoopWrapper,
    AnimaLoopAfterDenoiser,
    AnimaLoopBeforeDenoiser,
    AnimaLoopDenoiser,
)
from diffusers.modular_pipelines.anima.encoders import (
    AnimaImg2ImgVaeEncoderStep,
    AnimaTextEncoderStep,
)
from diffusers.modular_pipelines.anima.modular_blocks_anima import AnimaDecodeStep
from diffusers.modular_pipelines.modular_pipeline import (
    BlockState,
    ModularPipeline,
    ModularPipelineBlocks,
    PipelineState,
    SequentialPipelineBlocks,
)
from diffusers.modular_pipelines.modular_pipeline_utils import InputParam, OutputParam
from diffusers.pipelines.pipeline_utils import DiffusionPipeline
from diffusers.utils.torch_utils import randn_tensor

# Block states below are typed `Any`: Diffusers sets their attributes at runtime,
# after the block's inputs and outputs, and types them as `dict`.


class AnimaInpaintPrepareMaskStep(ModularPipelineBlocks):
    """Bring the mask image down to the latent grid: 1 where to regenerate."""

    model_name = "anima"

    @property
    def description(self) -> str:
        return "Binarize the mask image and resize it to the Anima latent grid."

    @property
    def inputs(self) -> list[InputParam]:
        return [
            InputParam.template("mask_image"),
            InputParam.template("height", required=True),
            InputParam.template("width", required=True),
        ]

    @property
    def intermediate_outputs(self) -> list[OutputParam]:
        return [
            OutputParam(
                "mask",
                type_hint=torch.Tensor,
                description="Latent mask, 1 where to regenerate, 0 where to keep.",
            ),
        ]

    @torch.no_grad()
    def __call__(
        self, components: ModularPipeline, state: PipelineState
    ) -> tuple[ModularPipeline, PipelineState]:
        block_state: Any = self.get_block_state(state)
        vae_scale_factor = components.vae_scale_factor

        # Same processing as the Z-Image inpaint pipeline.
        mask_processor = VaeImageProcessor(
            vae_scale_factor=vae_scale_factor * 2,
            do_normalize=False,
            do_binarize=True,
            do_convert_grayscale=True,
        )
        mask = mask_processor.preprocess(
            block_state.mask_image, height=block_state.height, width=block_state.width
        )
        mask = F.interpolate(
            mask,
            size=(
                block_state.height // vae_scale_factor,
                block_state.width // vae_scale_factor,
            ),
            mode="nearest",
        )

        # Anima latents carry a frame axis: (B, C, F, H, W).
        block_state.mask = mask.unsqueeze(2).to(
            device=components._execution_device, dtype=torch.float32
        )

        self.set_block_state(state, block_state)
        return components, state


class AnimaInpaintPrepareNoiseStep(ModularPipelineBlocks):
    """Draw the noise up front, so the denoising loop can noise the source
    image with it again.

    The image-to-image latents step takes it as its `latents`, which it reads
    as noise, and draws the very same one itself otherwise.
    """

    model_name = "anima"

    @property
    def description(self) -> str:
        return "Draw the noise shared by the initial latents and the inpainting blend."

    @property
    def inputs(self) -> list[InputParam]:
        return [
            InputParam.template("image_latents"),
            InputParam.template("generator"),
        ]

    @property
    def intermediate_outputs(self) -> list[OutputParam]:
        return [
            OutputParam(
                "latents", type_hint=torch.Tensor, description="Noise to start from."
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

        block_state.initial_noise = randn_tensor(
            block_state.image_latents.shape,
            generator=block_state.generator,
            device=components._execution_device,
            dtype=torch.float32,
        )
        block_state.latents = block_state.initial_noise

        self.set_block_state(state, block_state)
        return components, state


class AnimaLoopAfterDenoiserInpaint(ModularPipelineBlocks):
    """Reset the latents outside the mask to the source image, noised to the
    level of the next step."""

    model_name = "anima"

    @property
    def description(self) -> str:
        return (
            "Step within the denoising loop that keeps Anima latents outside the mask."
        )

    @property
    def inputs(self) -> list[InputParam]:
        return [
            InputParam(
                "mask",
                required=True,
                type_hint=torch.Tensor,
                description="Latent mask, 1 where to regenerate, 0 where to keep.",
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

        mask = block_state.mask
        block_state.latents = (1 - mask) * kept + mask * block_state.latents

        return components, block_state


def create_anima_inpaint_blocks() -> SequentialPipelineBlocks:
    """Create the Anima image-to-image blocks, plus the mask."""
    # The loop keeps this dict as is: it takes instances, not classes.
    denoise = AnimaDenoiseLoopWrapper.from_blocks_dict(
        {
            "before_denoiser": AnimaLoopBeforeDenoiser(),
            "denoiser": AnimaLoopDenoiser(
                guider_input_fields={
                    "encoder_hidden_states": ("prompt_embeds", "negative_prompt_embeds")
                }
            ),
            "after_denoiser": AnimaLoopAfterDenoiser(),
            "inpaint": AnimaLoopAfterDenoiserInpaint(),
        }
    )

    return SequentialPipelineBlocks.from_blocks_dict(
        {
            "text_encoder": AnimaTextEncoderStep,
            "vae_encoder": AnimaImg2ImgVaeEncoderStep,
            "prepare_mask": AnimaInpaintPrepareMaskStep,
            "text_conditioning": AnimaTextConditioningStep,
            "input": AnimaTextInputStep,
            "image_input": AnimaImageInputStep,
            "set_timesteps": AnimaImg2ImgSetTimestepsStep,
            "prepare_noise": AnimaInpaintPrepareNoiseStep,
            "prepare_latents": AnimaImg2ImgPrepareLatentsStep,
            "denoise": denoise,
            "decode": AnimaDecodeStep,
        }
    )


def create_anima_inpaint_pipe(
    pipe: DiffusionPipeline | ModularPipeline,
) -> ModularPipeline:
    """Create the Anima inpaint pipeline from the loaded Anima pipeline.

    It shares the loaded components (LoRA and attention processors included),
    so no weights load twice.
    """
    inpaint_pipe = create_anima_inpaint_blocks().init_pipeline()
    inpaint_pipe.update_components(**pipe.components)

    return inpaint_pipe
