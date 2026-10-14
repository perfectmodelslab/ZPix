"""LassoTool demo."""

import gradio as gr
from gradio_canvas import Canvas
from gradio_lasso_tool import LassoTool, lasso_to_mask
from PIL import Image

image = Image.new("RGB", (1200, 800), "steelblue")

with gr.Blocks(analytics_enabled=False) as demo:
    lasso = LassoTool(
        enable_tooltip="Enable lasso (L)",
        disable_tooltip="Disable lasso",
        draw_tooltip="Drag to draw a lasso",
        clear_tooltip="Shift: add to selection\nAlt: subtract from selection\nClick: clear selection",
    )

    with gr.Row():
        Canvas([image], tools=[lasso], interactive=False)
        mask = gr.Image(label="Mask", interactive=False)

    lasso.change(
        lambda outlines: outlines and lasso_to_mask(outlines, image.size),
        inputs=lasso,
        outputs=mask,
    )


if __name__ == "__main__":
    demo.launch()
