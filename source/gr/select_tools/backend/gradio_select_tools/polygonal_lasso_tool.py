"""PolygonalLassoTool Gradio custom component."""

from .select_tool import SelectTool


# Its module lies next to SelectTool's, so Gradio serves it the same frontend.
class PolygonalLassoTool(SelectTool):
    """
    Lets user draw a polygonal lasso, clicking vertices joined by straight
    segments, over the document displayed by a canvas, which hosts this tool,
    e.g. to mask a region to edit.

    Select tools of a canvas, e.g. a FreehandLassoTool and a PolygonalLassoTool,
    share one selection: their values follow each other.
    """

    MODE = "polygonal"
