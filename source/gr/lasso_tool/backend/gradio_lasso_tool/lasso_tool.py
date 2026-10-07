"""LassoTool Gradio custom component."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Literal

from gradio.components.base import Component
from gradio.data_classes import GradioRootModel
from gradio.events import Events
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from gradio.blocks import Block
    from gradio.components import Gallery, Timer


class Lasso(GradioRootModel):
    """Lasso vertices in pixels of the original image."""

    root: list[tuple[int, int]]


def lasso_to_mask(points: list[tuple[int, int]], size: tuple[int, int]) -> Image.Image:
    """Make the mask of a lasso, e.g. to inpaint its region.

    Args:
        points: Lasso vertices, as LassoTool passes them.
        size: Width and height of the image to mask.

    Returns:
        Grayscale image, white inside the lasso and black outside.
    """
    mask = Image.new("L", size, 0)
    # Closes the lasso from its last vertex to its first, as drawn.
    ImageDraw.Draw(mask).polygon(points, fill=255)

    return mask


class LassoTool(Component):
    """
    Lets user draw a freehand lasso over the image displayed by a gallery,
    e.g. to mask a region to edit.
    """

    EVENTS = [  # noqa: RUF012 (Gradio API)
        Events.change,
        Events.input,
        "drawn",
        "cleared",
    ]

    data_model = Lasso

    def __init__(
        self,
        value: list[tuple[int, int]] | Callable | None = None,
        *,
        gallery: Gallery | None = None,
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
            value: default lasso, as a list of `(x, y)` vertices in pixels of the original image. If a function is provided, the function will be called each time the app loads to set the initial value of this component.
            gallery: the gallery whose displayed (preview) image the lasso is drawn over. If it has no `elem_id`, one is assigned to find it in the DOM.
            draw_tooltip: shown over the image while no lasso is drawn, e.g. to tell user how to draw one.
            clear_tooltip: shown over the image once a lasso is drawn, e.g. to tell user how to clear it.
            marching_ants: if True, the outline of the drawn lasso is animated. If False, it stays still.
            smoothing: each vertex of the lasso is averaged with this many neighbors on each side, as it is drawn, to smooth the jitter of the hand. If 0, the lasso is kept as drawn.
            every: Continuously calls `value` to recalculate it if `value` is a function (has no effect otherwise). Can provide a Timer whose tick resets `value`, or a float that provides the regular interval for the reset Timer.
            inputs: Components that are used as inputs to calculate `value` if `value` is a function (has no effect otherwise). `value` is recalculated any time the inputs change.
            interactive: if False, the lasso can't be drawn or cleared. If not provided, the component is interactive unless it's only used as an event output.
            visible: If False, the lasso is not displayed.
            elem_id: An optional string that is assigned as the id of this component in the HTML DOM.
            elem_classes: An optional list of strings that are assigned as the classes of this component in the HTML DOM.
            render: If False, component will not render be rendered in the Blocks context. Should be used if the intention is to assign event listeners now but render the component later.
            key: in a gr.render, Components with the same key across re-renders are treated as the same component, not a new component. Properties set in 'preserved_by_key' are not reset across a re-render.
            preserved_by_key: A list of parameters from this component's constructor. Inside a gr.render() function, if a component is re-rendered with the same key, these (and only these) parameters will be preserved in the UI (if they have been changed by the user or an event listener) instead of re-rendered based on the values provided during constructor.
        """
        # Only the gallery DOM id goes to frontend, since Gradio would
        # otherwise serialize the whole gallery config (value included).
        self.gallery_elem_id = None

        if gallery is not None:
            if not gallery.elem_id:
                gallery.elem_id = f"gallery-{gallery._id}"
            self.gallery_elem_id = gallery.elem_id

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
        config["gallery_elem_id"] = self.gallery_elem_id
        return config

    def preprocess(self, payload: Lasso | None) -> list[tuple[int, int]] | None:
        """
        Parameters:
            payload: the lasso drawn by user, if any.
        Returns:
            Passes lasso as a {list} of `(x, y)` vertices (pixels of the original image), or None if there is no lasso.
        """
        return None if payload is None else payload.root

    def postprocess(self, value: list[tuple[int, int]] | None) -> Lasso | None:
        """
        Parameters:
            value: Expects a {list} of `(x, y)` vertices (pixels of the original image), or None to clear the lasso.
        Returns:
            The lasso to display.
        """
        if value is None or len(value) < 3:
            return None

        return Lasso([(round(x), round(y)) for x, y in value])

    def example_payload(self) -> Any:
        return [(64, 320), (192, 64), (320, 320)]

    def example_value(self) -> Any:
        return [(64, 320), (192, 64), (320, 320)]
