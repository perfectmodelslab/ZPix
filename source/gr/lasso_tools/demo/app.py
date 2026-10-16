"""FreehandLassoTool and PolygonalLassoTool demo."""

import gradio as gr
from gradio_canvas import Canvas
from gradio_lasso_tools import FreehandLassoTool, PolygonalLassoTool, lasso_to_mask
from PIL import Image

image = Image.new("RGB", (1200, 800), "steelblue")
selection_tooltip = "Shift: add to selection\nAlt: subtract from selection\nShift+Alt: intersect with selection"

with gr.Blocks(analytics_enabled=False) as demo:
    free_lasso = FreehandLassoTool(
        enable_tooltip="Enable lasso (L)",
        disable_tooltip="Disable lasso",
        draw_tooltip="Drag to draw a lasso",
        clear_tooltip=f"{selection_tooltip}\nClick: clear selection",
    )
    # Shares its selection with `free_lasso`, whose value follows it.
    poly_lasso = PolygonalLassoTool(
        enable_tooltip="Enable polygonal lasso (L)",
        disable_tooltip="Disable polygonal lasso",
        draw_tooltip="Click to draw a polygonal lasso",
        clear_tooltip=f"{selection_tooltip}\nCtrl+D: clear selection",
    )

    with gr.Row():
        Canvas([image], tools=[[free_lasso, poly_lasso]], interactive=False)
        mask = gr.Image(label="Mask", interactive=False)

    free_lasso.change(
        lambda outlines: outlines and lasso_to_mask(outlines, image.size),
        inputs=free_lasso,
        outputs=mask,
    )


if __name__ == "__main__":
    demo.launch()
