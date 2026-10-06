"""LassoTool demo."""

import gradio as gr
from gradio_lasso_tool import LassoTool
from PIL import Image, ImageDraw


def make_image(width: int, height: int, color: str) -> Image.Image:
    """Make a test image with a 100px grid, to check lasso coordinates."""
    image = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(image)

    for x in range(0, width, 100):
        draw.line([(x, 0), (x, height)], fill="white")
        draw.text((x + 4, 4), str(x), fill="white")

    for y in range(0, height, 100):
        draw.line([(0, y), (width, y)], fill="white")
        draw.text((4, y + 4), str(y), fill="white")

    return image


images = [
    (make_image(1200, 800, "steelblue"), "Landscape 1200×800"),
    (make_image(600, 1000, "seagreen"), "Portrait 600×1000"),
    (make_image(512, 512, "indianred"), "Square 512×512"),
]

with gr.Blocks(analytics_enabled=False) as demo:
    gallery = gr.Gallery(
        value=images,
        selected_index=0,
        object_fit="contain",
        interactive=False,
        height=600,
    )
    lasso = LassoTool(
        gallery=gallery,
        draw_tooltip="Drag to draw a lasso",
        clear_tooltip="Click to clear the lasso",
    )

    with gr.Row():
        output = gr.JSON(label="Lasso")
        clear_btn = gr.Button("Clear")
        preset_btn = gr.Button("Set triangle 100, 400 · 300, 100 · 500, 400")

    lasso.change(lambda points: points, inputs=lasso, outputs=output)
    clear_btn.click(lambda: None, outputs=lasso)
    preset_btn.click(
        lambda: [(100, 400), (300, 100), (500, 400)],
        outputs=lasso,
    )


if __name__ == "__main__":
    demo.launch()
