"""SelectTool: ancestor of select tool Gradio custom components."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from gradio.components.base import Component
from gradio.data_classes import GradioRootModel
from gradio.events import Events
from PIL import Image, ImageChops, ImageDraw

if TYPE_CHECKING:
    from gradio.blocks import Block
    from gradio.components import Timer


class Selection(GradioRootModel):
    """Selection outlines, each a list of vertices in pixels of the base layer image.

    A point is selected if it lies inside an odd number of outlines, so an
    outline inside another one is a hole.
    """

    root: list[list[tuple[int, int]]]


def selection_to_mask(
    outlines: list[list[tuple[int, int]]], size: tuple[int, int]
) -> Image.Image:
    """Make the mask of a selection, e.g. to inpaint its regions.

    Args:
        outlines: Selection outlines, as SelectTool passes them.
        size: Width and height of the image to mask.

    Returns:
        Grayscale image, white inside the selection and black outside.
    """
    mask = Image.new("1", size, 0)

    for outline in outlines:
        outline_mask = Image.new("1", size, 0)
        # Closes the outline from its last vertex to its first, as drawn.
        ImageDraw.Draw(outline_mask).polygon(outline, fill=1)
        # Selected inside an odd number of outlines.
        mask = ImageChops.logical_xor(mask, outline_mask)

    return mask.convert("L")


class SelectTool(Component):
    """
    Lets user select a region of the document displayed by a canvas, which
    hosts this tool, e.g. to mask a region to edit.

    Ancestor of FreehandLassoTool, PolygonalLassoTool, RectangleSelectTool and
    EllipseSelectTool, which differ only in how user draws, so it can't be
    instantiated itself. Select tools of a canvas share one selection: their
    values follow each other.
    """

    EVENTS = [  # noqa: RUF012 (Gradio API)
        Events.change,
        Events.input,
        "drawn",
        "cleared",
    ]

    data_model = Selection

    MODE: ClassVar[Literal["freehand", "polygonal", "rectangle", "ellipse"]]
    """How user draws: dragging a lasso, clicking vertices joined by straight
    segments, or dragging a rectangle or an ellipse."""

    def __init__(
        self,
        value: list[list[tuple[int, int]]] | Callable | None = None,
        *,
        enable_tooltip: str | None = None,
        disable_tooltip: str | None = None,
        draw_tooltip: str | None = None,
        clear_tooltip: str | None = None,
        marching_ants: bool = True,
        smoothing: int = 1,
        every: Timer | float | None = None,
        inputs: Component | Sequence[Component] | set[Component] | None = None,
        interactive: bool | None = None,
        visible: bool | Literal["hidden"] = True,
        elem_id: str | None = None,
        elem_classes: list[str] | str | None = None,
        render: bool = True,
        key: int | str | tuple[int | str, ...] | None = None,
        preserved_by_key: list[str] | str | None = "value",
    ):
        """
        Parameters:
            value: default selection, as a list of outlines, each a list of `(x, y)` vertices in pixels of the base layer image. A point is selected if it lies inside an odd number of outlines, so an outline inside another one is a hole. If a function is provided, the function will be called each time the app loads to set the initial value of this component.
            enable_tooltip: tooltip of the tool button, in the canvas toolbar, while this tool isn't selected.
            disable_tooltip: tooltip of the tool button, in the canvas toolbar, while this tool is selected.
            draw_tooltip: shown over the image while nothing is selected, e.g. to tell user how to select.
            clear_tooltip: shown over the image once something is selected, e.g. to tell user how to add to the selection, subtract from it or clear it.
            marching_ants: if True, the outline of the selection is animated. If False, it stays still.
            smoothing: lasso tools only: each vertex of freehand segments is averaged with this many neighbors on each side, as it is drawn, to smooth the jitter of the hand. If 0, the lasso is kept as drawn.
            every: Continuously calls `value` to recalculate it if `value` is a function (has no effect otherwise). Can provide a Timer whose tick resets `value`, or a float that provides the regular interval for the reset Timer.
            inputs: Components that are used as inputs to calculate `value` if `value` is a function (has no effect otherwise). `value` is recalculated any time the inputs change.
            interactive: if False, nothing can be selected or cleared with this tool. If not provided, the component is interactive unless it's only used as an event output.
            visible: If False, the tool button is hidden, and so is the selection, unless another select tool of the canvas is visible.
            elem_id: An optional string that is assigned as the id of this component in the HTML DOM.
            elem_classes: An optional list of strings that are assigned as the classes of this component in the HTML DOM.
            render: If False, component will not render be rendered in the Blocks context. Should be used if the intention is to assign event listeners now but render the component later.
            key: in a gr.render, Components with the same key across re-renders are treated as the same component, not a new component. Properties set in 'preserved_by_key' are not reset across a re-render.
            preserved_by_key: A list of parameters from this component's constructor. Inside a gr.render() function, if a component is re-rendered with the same key, these (and only these) parameters will be preserved in the UI (if they have been changed by the user or an event listener) instead of re-rendered based on the values provided during constructor.
        """
        if type(self) is SelectTool:
            raise TypeError(
                "SelectTool is abstract: use FreehandLassoTool, PolygonalLassoTool, "
                "RectangleSelectTool or EllipseSelectTool."
            )

        # Set by the canvas hosting this tool, e.g. Canvas(tools=[[free_lasso]]).
        self.canvas_id: int | None = None

        self.enable_tooltip = enable_tooltip
        self.disable_tooltip = disable_tooltip
        self.draw_tooltip = draw_tooltip
        self.clear_tooltip = clear_tooltip
        self.marching_ants = marching_ants
        self.smoothing = smoothing

        super().__init__(
            every=every,
            inputs=inputs,
            show_label=False,
            container=False,
            interactive=interactive,
            visible=visible,
            elem_id=elem_id,
            elem_classes=elem_classes,
            value=value,
            render=render,
            key=key,
            preserved_by_key=preserved_by_key,
        )

    def get_config(self, cls: type[Block] | None = None) -> dict[str, Any]:
        config = super().get_config(cls)
        config["canvas_id"] = self.canvas_id
        config["mode"] = self.MODE
        return config

    def preprocess(
        self, payload: Selection | None
    ) -> list[list[tuple[int, int]]] | None:
        """
        Parameters:
            payload: the selection made by user, if any.
        Returns:
            Passes selection as a {list} of outlines, each a {list} of `(x, y)` vertices (pixels of the base layer image), or None if nothing is selected.
        """
        return None if payload is None else payload.root

    def postprocess(
        self, value: list[list[tuple[int, int]]] | None
    ) -> Selection | None:
        """
        Parameters:
            value: Expects a {list} of outlines, each a {list} of `(x, y)` vertices (pixels of the base layer image), or None to clear the selection.
        Returns:
            The selection to display.
        """
        # An outline needs 3 vertices to enclose a region.
        outlines = [
            [(round(x), round(y)) for x, y in outline]
            for outline in value or []
            if len(outline) >= 3
        ]

        return Selection(outlines) if outlines else None

    def example_payload(self) -> Any:
        return [[(64, 320), (192, 64), (320, 320)]]

    def example_value(self) -> Any:
        return [[(64, 320), (192, 64), (320, 320)]]
