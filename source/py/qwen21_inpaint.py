"""Qwen-Image 2.1 inpainting, on top of the Diffusers Qwen-Image 2.1 pipeline.

Diffusers ships Qwen-Image 2.1 as text-to-image and edit only. Inpainting here
is text-to-image started from the source image, noised as much as strength
spares, whose latents outside the mask are reset, after each step, to the
source image noised to the next step's level, as Diffusers does for Qwen-Image.
The transformer never sees the mask, nor the source image as a condition.
"""

from collections.abc import Callable
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from diffusers.image_processor import VaeImageProcessor
from diffusers.modular_pipelines.modular_pipeline import ModularPipeline
from diffusers.pipelines.pipeline_utils import DiffusionPipeline
from diffusers.pipelines.qwenimage21.pipeline_qwenimage21 import (
    QwenImage21Pipeline,
    calculate_shift,
    retrieve_timesteps,
)
from PIL import Image


class QwenImage21InpaintPipeline(QwenImage21Pipeline):
    """Qwen-Image 2.1 pipeline regenerating the masked region of an image."""

    def prepare_inpaint_latents(
        self,
        image: Image.Image,
        mask_image: Image.Image,
        batch_size: int,
        height: int,
        width: int,
        generator: torch.Generator | list[torch.Generator] | None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Encode the source image, draw the noise and bring the mask image down
        to the latent tokens.

        Returns:
            Packed source image latents, noise and mask: 1 where to regenerate.
        """
        device = self._execution_device
        latent_height = height // self.vae_scale_factor
        latent_width = width // self.vae_scale_factor

        # The VAE reads four channels, as the stock pipeline feeds it.
        pixels = self.image_processor.preprocess(
            image.convert("RGBA"), height=height, width=width
        ).unsqueeze(2)
        # Typed for one generator, though it takes a list as well.
        image_latents = self._encode_vae_image(
            pixels.to(device=device, dtype=self.vae.dtype),
            generator,  # ty: ignore[invalid-argument-type]
        )
        image_latents = self._pack_latents(
            image_latents, 1, self.latent_channels, latent_height, latent_width
        )
        image_latents = image_latents.to(torch.float32).repeat(batch_size, 1, 1)

        noise, _ = self.prepare_latents(
            None,
            batch_size,
            self.transformer.config.in_channels,
            height,
            width,
            torch.float32,
            device,
            generator,
        )

        # Same processing as the Qwen-Image inpaint pipeline.
        mask_processor = VaeImageProcessor(
            vae_scale_factor=self.vae_scale_factor,
            do_normalize=False,
            do_binarize=True,
            do_convert_grayscale=True,
        )
        mask = mask_processor.preprocess(mask_image, height=height, width=width)
        mask = F.interpolate(mask, size=(latent_height, latent_width), mode="nearest")

        # 2.1 packs latents as a plain spatial flatten, one token per position:
        # (1, 1, H, W) -> (1, H * W, 1), broadcast over the channels.
        mask = mask.flatten(2).transpose(1, 2).to(device=device, dtype=torch.float32)

        return image_latents, noise, mask

    @torch.no_grad()
    def __call__(
        self,
        prompt: str | list[str] | None = None,
        image: Image.Image | None = None,
        mask_image: Image.Image | None = None,
        strength: float = 0.6,
        true_cfg_scale: float = 1.0,
        height: int | None = None,
        width: int | None = None,
        num_inference_steps: int = 40,
        sigmas: list[float] | None = None,
        num_images_per_prompt: int = 1,
        generator: torch.Generator | list[torch.Generator] | None = None,
        callback_on_step_end: Callable[..., dict] | None = None,
        callback_on_step_end_tensor_inputs: list[str] | None = None,
        **kwargs: Any,
    ):
        """Regenerate the masked region of an image.

        Args:
            image: Source image.
            mask_image: Mask image, white where to regenerate.
            strength: How much of the masked region to regenerate. At 1, it is
                regenerated from scratch, guided by its context.

        Other arguments are those of `QwenImage21Pipeline.__call__`, which see.
        """
        if image is None or mask_image is None:
            raise ValueError("Pass both `image` and `mask_image` to inpaint.")

        # Rounded as the stock pipeline will, so the source image and mask fit
        # the latents it denoises.
        multiple_of = self.vae_scale_factor * 2
        width = (width or image.width) // multiple_of * multiple_of
        height = (height or image.height) // multiple_of * multiple_of

        if isinstance(prompt, str):
            batch_size = 1
        elif prompt is not None:
            batch_size = len(prompt)
        else:
            batch_size = kwargs["prompt_embeds"].shape[0]

        image_latents, noise, mask = self.prepare_inpaint_latents(
            image,
            mask_image,
            batch_size * num_images_per_prompt,
            height,
            width,
            generator,
        )

        # Skip the first steps, as much as strength spares. The scheduler shifts
        # the remaining sigmas as it would the whole schedule.
        schedule = (
            np.linspace(1.0, 1 / num_inference_steps, num_inference_steps)
            if sigmas is None
            else np.array(sigmas)
        )
        steps = len(schedule)
        start = int(max(steps - min(steps * strength, steps), 0))
        sigmas = schedule[start:].tolist()

        if not sigmas:
            raise ValueError(f"Strength {strength} leaves no step to inpaint with.")

        # Set as the stock pipeline will, so the source image is noised to the
        # level of its first step.
        scheduler = self.scheduler
        mu = calculate_shift(
            noise.shape[1],
            scheduler.config.get("base_image_seq_len", 256),
            scheduler.config.get("max_image_seq_len", 4096),
            scheduler.config.get("base_shift", 0.5),
            scheduler.config.get("max_shift", 1.15),
        )
        timesteps, _ = retrieve_timesteps(
            scheduler, None, self._execution_device, sigmas=sigmas, mu=mu
        )
        latents = scheduler.scale_noise(
            image_latents, timesteps[:1].repeat(noise.shape[0]), noise
        )

        def keep_unmasked(
            pipe: QwenImage21Pipeline, i: int, t: torch.Tensor, step: dict
        ) -> dict:
            """Reset the latents outside the mask to the source image, noised
            to the level of the next step."""
            kept = image_latents

            # Past the last step, latents are clean: so is the source image.
            if i < len(pipe.scheduler.timesteps) - 1:
                kept = pipe.scheduler.scale_noise(
                    kept, pipe.scheduler.timesteps[i + 1 : i + 2], noise
                )

            denoised = step["latents"]
            step["latents"] = ((1 - mask) * kept + mask * denoised).to(denoised.dtype)

            if callback_on_step_end is not None:
                step.update(callback_on_step_end(pipe, i, t, step))

            return step

        tensor_inputs = callback_on_step_end_tensor_inputs or ["latents"]

        return super().__call__(
            prompt=prompt,
            true_cfg_scale=true_cfg_scale,
            height=height,
            width=width,
            num_inference_steps=len(sigmas),
            sigmas=sigmas,
            num_images_per_prompt=num_images_per_prompt,
            generator=generator,
            latents=latents,
            callback_on_step_end=keep_unmasked,
            callback_on_step_end_tensor_inputs=list(
                dict.fromkeys(["latents", *tensor_inputs])
            ),
            **kwargs,
        )


def create_qwen21_inpaint_pipe(
    pipe: DiffusionPipeline | ModularPipeline,
) -> QwenImage21InpaintPipeline:
    """Create the Qwen-Image 2.1 inpaint pipeline from the loaded Qwen-Image 2.1
    pipeline.

    It shares the loaded components (LoRA and attention processors included),
    so no weights load twice.
    """
    return QwenImage21InpaintPipeline(**pipe.components)
