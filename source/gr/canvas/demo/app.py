"""Canvas demo."""

import gradio as gr
from gradio_canvas import Canvas, CanvasValue, DocEvent, ToolEvent
from gradio_lasso_tools import FreehandLassoTool
from PIL import Image

images = [Image.new("RGB", (1200, 800), color) for color in ("steelblue", "tomato")]

# Kept server side: listeners run concurrently, so each would override the
# others' lines if they got the log as input.
events: list[str] = []


def log(line: str) -> str:
    events.insert(0, line)
    return "\n".join(events)


with gr.Blocks(analytics_enabled=False) as demo:
    lasso = FreehandLassoTool(
        enable_tooltip="Enable lasso (L)",
        disable_tooltip="Disable lasso",
        draw_tooltip="Drag to draw a lasso",
    )
    canvas = Canvas(
        images,
        tools=[
            [lasso],
        ],
        placeholder="Drop an image",
        height="80vh",
        interactive=True,
    )

    with gr.Row():
        prev_btn = gr.Button("Previous")
        next_btn = gr.Button("Next")
        add_btn = gr.Button("Add")
        delete_btn = gr.Button("Delete")

    log_box = gr.Textbox(label="Events", lines=8, interactive=False)

    prev_btn.click(lambda c: c.select_prev_doc(), canvas, canvas)
    next_btn.click(lambda c: c.select_next_doc(), canvas, canvas)
    add_btn.click(lambda c: c.add(Image.new("RGB", (800, 800), "gold")), canvas, canvas)
    delete_btn.click(lambda c: c.delete(), canvas, canvas)

    def doc_logger(name: str):
        def log_doc_event(canvas: CanvasValue, event: DocEvent) -> str:
            return log(f"{name} #{event.index} ({len(canvas.docs)} docs)")

        return log_doc_event

    for listener, name in [
        (canvas.doc_added, "doc_added"),
        (canvas.doc_deleted, "doc_deleted"),
        (canvas.doc_dropped, "doc_dropped"),
        (canvas.select, "select"),
        (canvas.thumb_click, "thumb_click"),
    ]:
        listener(doc_logger(name), canvas, log_box)

    canvas.empty(lambda: log("empty"), None, log_box)
    canvas.filled(lambda: log("filled"), None, log_box)

    def log_tool(event: ToolEvent) -> str:
        return log(f"tool_selected {'lasso' if event.tool is lasso else None}")

    canvas.tool_selected(log_tool, None, log_box)


if __name__ == "__main__":
    demo.launch()
