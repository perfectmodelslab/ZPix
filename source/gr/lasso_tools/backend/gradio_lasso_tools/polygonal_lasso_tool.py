"""PolygonalLassoTool Gradio custom component."""

from .lasso_tool import LassoTool


# Its module lies next to LassoTool's, so Gradio serves it the same frontend.
class PolygonalLassoTool(LassoTool):
    """
    Lets user draw a polygonal lasso, clicking vertices joined by straight
    segments, over the document displayed by a canvas, which hosts this tool,
    e.g. to mask a region to edit.

    Lasso tools of a canvas, e.g. a FreehandLassoTool and a PolygonalLassoTool,
    share one selection: their values follow each other.
    """

    POLYGONAL = True
