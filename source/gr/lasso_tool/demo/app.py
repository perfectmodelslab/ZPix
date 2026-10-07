"""LassoTool demo."""

import gradio as gr
from gradio_lasso_tool import LassoTool, lasso_to_mask
from PIL import Image

image = Image.new("RGB", (1200, 800), "steelblue")

with gr.Blocks(analytics_enabled=False) as demo:
    with gr.Row():
        gallery = gr.Gallery(
            value=[image],
            selected_index=0,
            object_fit="contain",
            interactive=False,
        )
        mask = gr.Image(label="Mask", interactive=False)

    lasso = LassoTool(
        gallery=gallery,
        draw_tooltip="Drag to draw a lasso",
        clear_tooltip="Hold Shift to enlarge selection\nHold Alt to reduce selection\nClick to clear the lasso",
    )

    lasso.change(
        lambda points: points and lasso_to_mask(points, image.size),
        inputs=lasso,
        outputs=mask,
    )


if __name__ == "__main__":
    demo.launch()
