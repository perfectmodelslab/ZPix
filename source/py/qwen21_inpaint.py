"""Qwen-Image 2.1 inpainting, assembled from the Diffusers Qwen-Image 2.1 modular
blocks.

Diffusers ships Qwen-Image 2.1 as text-to-image and edit only. Inpainting here
is an edit conditioned on the source image, so the model sees the region's
context clean, started from the source image, noised as much as strength
spares, whose latents outside the mask are reset, after each step, to the
source image noised to the next step's level, as Diffusers does for Qwen-Image.
The transformer never sees the mask.
"""

from typing import Any

import torch
import torch.nn.functional as F
from diffusers.image_processor import VaeImageProcessor
from diffusers.modular_pipelines.modular_pipeline import (
    BlockState,
    ModularPipeline,
    ModularPipelineBlocks,
    PipelineState,
    SequentialPipelineBlocks,
)
from diffusers.modular_pipelines.modular_pipeline_utils import InputParam, OutputParam
from diffusers.modular_pipelines.qwenimage.before_denoise import get_timesteps
from diffusers.modular_pipelines.qwenimage21.before_denoise import (
    QwenImage21ImageConditionedRoPEInputsStep,
    QwenImage21PrepareLatentsStep,
    QwenImage21SetTimestepsStep,
    QwenImage21TurboSetTimestepsStep,
)
from diffusers.modular_pipelines.qwenimage21.decoders import (
    QwenImage21DecodeStep,
    QwenImage21UnpackLatentsStep,
)
from diffusers.modular_pipelines.qwenimage21.denoise import (
    QwenImage21DenoiseLoopWrapper,
    QwenImage21ImageConditionedLoopBeforeDenoiser,
    QwenImage21LoopAfterDenoiser,
    QwenImage21LoopDenoiser,
    QwenImage21TurboLoopDenoiser,
)
from diffusers.modular_pipelines.qwenimage21.encoders import encode_vae_image
from diffusers.modular_pipelines.qwenimage21.inputs import (
    QwenImage21AdditionalInputsStep,
    QwenImage21TextInputsStep,
    QwenImage21TurboTextInputsStep,
    pack_latents,
)
from diffusers.modular_pipelines.qwenimage21.modular_blocks_qwenimage21 import (
    QwenImage21VaeEncoderSequentialStep,
    QwenImage21VLEncoderStep,
)
from diffusers.modular_pipelines.qwenimage21.modular_blocks_qwenimage21_turbo import (
    QwenImage21TurboVaeEncoderSequentialStep,
    QwenImage21TurboVLEncoderStep,
)
from diffusers.modular_pipelines.qwenimage21.modular_pipeline import (
    QwenImage21TurboModularPipeline,
)
from diffusers.pipelines.pipeline_utils import DiffusionPipeline

# Block states below are typed `Any`: Diffusers sets their attributes at runtime,
# after the block's inputs and outputs, and types them as `dict`.


class QwenImage21InpaintPrepareLatentsStep(ModularPipelineBlocks):
    """Encode the source image at the generated image size, bring the mask image
    down to the latent tokens, then skip the first steps, as much as strength
    spares, and noise the source image to the level of the first remaining one.

    Its latents are named apart from the image latents, which hold the condition
    image, at its own size.
    """

    model_name = "qwenimage21"

    @property
    def description(self) -> str:
        return (
            "Encode the source image and mask as Qwen-Image 2.1 tokens, truncate"
            " the schedule by strength and noise the source image."
        )

    @property
    def inputs(self) -> list[InputParam]:
        return [
            InputParam.template("image"),
            InputParam.template("mask_image"),
            InputParam.template("height", required=True),
            InputParam.template("width", required=True),
            InputParam.template("generator"),
            InputParam.template("strength"),
            InputParam.template("num_inference_steps", required=True),
            InputParam("timesteps", required=True, type_hint=torch.Tensor),
            InputParam("latents", required=True, type_hint=torch.Tensor),
        ]

    @property
    def intermediate_outputs(self) -> list[OutputParam]:
        return [
            OutputParam(
                "source_latents",
                type_hint=torch.Tensor,
                description="Packed latents of the source image.",
            ),
            OutputParam(
                "mask",
                type_hint=torch.Tensor,
                description="Packed mask, 1 where to regenerate, 0 where to keep.",
            ),
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
        vae = components.vae
        vae_scale_factor = components.vae_scale_factor
        height, width = block_state.height, block_state.width
        noise = block_state.latents

        # The VAE reads four channels, as the condition image steps feed it.
        image = components.image_processor.preprocess(
            block_state.image.convert("RGBA"), height=height, width=width
        )
        source_latents = encode_vae_image(
            image=image,
            vae=vae,
            generator=block_state.generator,
            device=components._execution_device,
            dtype=vae.dtype,
            latent_channels=vae.config.z_dim,
        )
        block_state.source_latents = (
            pack_latents(source_latents).to(noise).repeat(noise.shape[0], 1, 1)
        )

        # Same processing as the Qwen-Image inpaint pipeline.
        mask_processor = VaeImageProcessor(
            vae_scale_factor=vae_scale_factor,
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

        # One token per position, broadcast over the channels:
        # (1, 1, H, W) -> (1, H * W, 1).
        block_state.mask = mask.flatten(2).transpose(1, 2).to(noise)

        block_state.timesteps, block_state.num_inference_steps = get_timesteps(
            components.scheduler, block_state.num_inference_steps, block_state.strength
        )
        block_state.initial_noise = noise
        block_state.latents = components.scheduler.scale_noise(
            block_state.source_latents,
            block_state.timesteps[:1].repeat(noise.shape[0]),
            noise,
        )

        self.set_block_state(state, block_state)
        return components, state


class QwenImage21LoopAfterDenoiserInpaint(ModularPipelineBlocks):
    """Reset the latents outside the mask to the source image, noised to the
    level of the next step."""

    model_name = "qwenimage21"

    @property
    def description(self) -> str:
        return (
            "Step within the denoising loop that keeps Qwen-Image 2.1 latents"
            " outside the mask."
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
            InputParam(
                "source_latents",
                required=True,
                type_hint=torch.Tensor,
                description="Packed latents of the source image.",
            ),
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
        kept = block_state.source_latents

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


def create_qwen21_inpaint_blocks(turbo: bool) -> SequentialPipelineBlocks:
    """Create the Qwen-Image 2.1 edit blocks, plus the mask.

    Args:
        turbo: Whether to create them for the distilled checkpoint, which runs
            without classifier-free guidance.
    """
    # The loop keeps this dict as is: it takes instances, not classes.
    denoise = QwenImage21DenoiseLoopWrapper.from_blocks_dict(
        {
            "before_denoiser": QwenImage21ImageConditionedLoopBeforeDenoiser(),
            "denoiser": (
                QwenImage21TurboLoopDenoiser() if turbo else QwenImage21LoopDenoiser()
            ),
            "after_denoiser": QwenImage21LoopAfterDenoiser(),
            "inpaint": QwenImage21LoopAfterDenoiserInpaint(),
        }
    )

    return SequentialPipelineBlocks.from_blocks_dict(
        {
            "text_encoder": (
                QwenImage21TurboVLEncoderStep if turbo else QwenImage21VLEncoderStep
            ),
            "vae_encoder": (
                QwenImage21TurboVaeEncoderSequentialStep
                if turbo
                else QwenImage21VaeEncoderSequentialStep
            ),
            "input": (
                QwenImage21TurboTextInputsStep if turbo else QwenImage21TextInputsStep
            ),
            "additional_inputs": QwenImage21AdditionalInputsStep,
            # Rounds height and width to what the transformer takes, before the
            # source image and mask are brought to them.
            "prepare_latents": QwenImage21PrepareLatentsStep,
            "set_timesteps": (
                QwenImage21TurboSetTimestepsStep
                if turbo
                else QwenImage21SetTimestepsStep
            ),
            "prepare_inpaint_latents": QwenImage21InpaintPrepareLatentsStep,
            "prepare_rope_inputs": QwenImage21ImageConditionedRoPEInputsStep,
            "denoise": denoise,
            "unpack_latents": QwenImage21UnpackLatentsStep,
            "decode": QwenImage21DecodeStep,
        }
    )


def create_qwen21_inpaint_pipe(
    pipe: DiffusionPipeline | ModularPipeline,
) -> ModularPipeline:
    """Create the Qwen-Image 2.1 inpaint pipeline from the loaded Qwen-Image 2.1
    pipeline.

    It shares the loaded components (LoRA and attention processors included),
    so no weights load twice.
    """
    turbo = isinstance(pipe, QwenImage21TurboModularPipeline)
    inpaint_pipe = create_qwen21_inpaint_blocks(turbo).init_pipeline()
    inpaint_pipe.update_components(**pipe.components)

    # Distilled models only fully denoise along the sigmas their author
    # configured: the loaded pipeline read them from the checkpoint, this one
    # doesn't.
    if turbo:
        inpaint_pipe.update_components(sample_sigmas=pipe.config["sample_sigmas"])

    return inpaint_pipe
