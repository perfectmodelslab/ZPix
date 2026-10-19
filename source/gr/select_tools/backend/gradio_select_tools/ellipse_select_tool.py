"""EllipseSelectTool Gradio custom component."""

from .select_tool import SelectTool


# Its module lies next to SelectTool's, so Gradio serves it the same frontend.
class EllipseSelectTool(SelectTool):
    """
    Lets user select an ellipse, dragging the pointer, over the document
    displayed by a canvas, which hosts this tool, e.g. to mask a region to edit.

    Select tools of a canvas, e.g. a RectangleSelectTool and an
    EllipseSelectTool, share one selection: their values follow each other.
    """

    MODE = "ellipse"
