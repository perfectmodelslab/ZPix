import gradio as gr
from gradio_canvas import CanvasValue


def sync_used_prompt(canvas: CanvasValue) -> dict:
    """Sync "Used prompt" value and visibility
    according to document displayed in canvas.
    """
    # Prompt is embedded in image file, see OutputImage()
    prompt = canvas.doc and canvas.doc.image.info.get("prompt")

    if not isinstance(prompt, str):
        return gr.update(value=None, visible=False)

    return gr.update(value=prompt, visible=bool(prompt))
