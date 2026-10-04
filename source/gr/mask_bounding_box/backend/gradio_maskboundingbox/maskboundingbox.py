"""MaskBoundingBox Gradio custom component."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Literal

from gradio.components.base import Component
from gradio.data_classes import GradioModel
from gradio.events import Events
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from gradio.blocks import Block
    from gradio.components import Gallery, Timer


class BoundingBox(GradioModel):
    """Bounding box in pixels of the original image."""

    x: int
    y: int
    width: int
    height: int


def mask_bbox_to_image(bbox: dict[str, int], size: tuple[int, int]) -> Image.Image:
    """Make the mask of a bounding box, e.g. to inpaint its region.

    Args:
        bbox: Bounding box, as MaskBoundingBox passes it.
        size: Width and height of the image to mask.

    Returns:
        Grayscale image, white inside the bounding box and black outside.
    """
    mask = Image.new("L", size, 0)
    right = bbox["x"] + bbox["width"] - 1
    bottom = bbox["y"] + bbox["height"] - 1
    ImageDraw.Draw(mask).rectangle((bbox["x"], bbox["y"], right, bottom), fill=255)

    return mask


class MaskBoundingBox(Component):
    """
    Lets user draw, move and resize a bounding box over the image displayed
    by a gallery, e.g. to mask a region to edit.
    """

    EVENTS = [  # noqa: RUF012 (Gradio API)
        Events.change,
        Events.input,
        "drawn",
        "cleared",
    ]

    data_model = BoundingBox

    def __init__(
        self,
        value: dict[str, int] | Callable | None = None,
        *,
        gallery: Gallery | None = None,
        draw_tooltip: str | None = None,
        clear_tooltip: str | None = None,
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
            value: default bounding box, as a dict with `x`, `y`, `width` and `height` keys in pixels of the original image. If a function is provided, the function will be called each time the app loads to set the initial value of this component.
            gallery: the gallery whose displayed (preview) image the bounding box is drawn over. If it has no `elem_id`, one is assigned to find it in the DOM.
            draw_tooltip: shown over the image while no bounding box is drawn, e.g. to tell user how to draw one.
            clear_tooltip: shown over the image, outside the bounding box once drawn, e.g. to tell user how to clear it.
            every: Continuously calls `value` to recalculate it if `value` is a function (has no effect otherwise). Can provide a Timer whose tick resets `value`, or a float that provides the regular interval for the reset Timer.
            inputs: Components that are used as inputs to calculate `value` if `value` is a function (has no effect otherwise). `value` is recalculated any time the inputs change.
            interactive: if False, the bounding box can't be drawn, moved or resized. If not provided, the component is interactive unless it's only used as an event output.
            visible: If False, the bounding box is not displayed.
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

    def preprocess(self, payload: BoundingBox | None) -> dict[str, int] | None:
        """
        Parameters:
            payload: the bounding box drawn by user, if any.
        Returns:
            Passes bounding box as a {dict} with `x`, `y`, `width` and `height` keys (pixels of the original image), or None if there is no bounding box.
        """
        return None if payload is None else payload.model_dump()

    def postprocess(self, value: dict[str, int] | None) -> BoundingBox | None:
        """
        Parameters:
            value: Expects a {dict} with `x`, `y`, `width` and `height` keys (pixels of the original image), or None to clear the bounding box.
        Returns:
            The bounding box to display.
        """
        if value is None:
            return None

        box = BoundingBox(
            x=max(0, round(value["x"])),
            y=max(0, round(value["y"])),
            width=round(value["width"]),
            height=round(value["height"]),
        )

        return box if box.width > 0 and box.height > 0 else None

    def example_payload(self) -> Any:
        return {"x": 64, "y": 64, "width": 256, "height": 256}

    def example_value(self) -> Any:
        return {"x": 64, "y": 64, "width": 256, "height": 256}
