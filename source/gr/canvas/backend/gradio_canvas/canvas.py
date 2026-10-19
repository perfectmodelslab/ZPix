"""Canvas Gradio custom component."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, Self

from gradio import processing_utils
from gradio.components.base import Component
from gradio.data_classes import FileData, GradioModel
from gradio.events import EventData, Events
from PIL import Image

if TYPE_CHECKING:
    from gradio.blocks import Block
    from gradio.components import Timer


@dataclass
class Layer:
    """Layer of a document."""

    object: Image.Image
    """Served from its file if opened from one, e.g. with `Image.open`."""

    imported: bool = False
    """Whether it comes from outside the session, e.g. a dropped file,
    rather than from the app, e.g. generated."""

    source_file: Path | None = None
    """File the object comes from, if any, e.g. to move it later, since
    canvas serves a copy of this file. Kept as is by canvas."""


@dataclass
class Doc:
    """Document: a stack of layers, from the base one up."""

    layers: list[Layer]

    @property
    def image(self) -> Image.Image:
        """Object of the base layer."""
        return self.layers[0].object


type DocLike = Doc | Image.Image
"""Document, or image to make a single layer document of."""


def to_doc(doc: DocLike) -> Doc:
    return doc if isinstance(doc, Doc) else Doc([Layer(doc)])


@dataclass
class CanvasValue:
    """Documents of a canvas, and the one it displays.

    Methods change this value in place and return it, so a listener can
    return it as is, e.g. `btn.click(lambda c: c.select_next_doc(), c, c)`.
    """

    docs: list[Doc] = field(default_factory=list)
    index: int | None = None
    """Index of the displayed document, None only if there is none."""

    @property
    def doc(self) -> Doc | None:
        """Displayed document, if any."""
        return None if self.index is None else self.docs[self.index]

    @property
    def is_empty(self) -> bool:
        return not self.docs

    def add(self, *docs: DocLike, select: bool = True) -> Self:
        """Add documents, and display the last one, unless `select` is False."""
        first = len(self.docs)
        self.docs.extend(to_doc(doc) for doc in docs)

        if docs and (select or self.index is None):
            self.index = len(self.docs) - 1 if select else first

        return self

    def delete(self, index: int | None = None) -> Self:
        """Delete a document, the displayed one by default.

        The next document, else the previous one, takes the place of a
        displayed document deleted.
        """
        if index is None:
            index = self.index
        if index is None:
            return self

        index = range(len(self.docs))[index]
        del self.docs[index]

        if not self.docs:
            self.index = None
        elif self.index is not None and (
            index < self.index or self.index == len(self.docs)
        ):
            self.index -= 1

        return self

    def select_doc(self, index: int) -> Self:
        """Display a document. Negative indexes count from the end.

        Raises:
            IndexError: If there is no such document.
        """
        self.index = range(len(self.docs))[index]
        return self

    def select_next_doc(self) -> Self:
        """Display the next document, if any."""
        if self.index is not None and self.index + 1 < len(self.docs):
            self.index += 1
        return self

    def select_prev_doc(self) -> Self:
        """Display the previous document, if any."""
        if self.index:
            self.index -= 1
        return self


class LayerData(GradioModel):
    object: FileData
    imported: bool = False
    source_file: str | None = None


class DocData(GradioModel):
    layers: list[LayerData]
    caption: str | None = None


class CanvasData(GradioModel):
    docs: list[DocData]
    index: int | None


class Tool(Protocol):
    """Component a canvas hosts, e.g. LassoTool.

    A canvas tells its tools its ID, by which they find it in the frontend.
    """

    _id: int
    canvas_id: int | None


class DocEvent(EventData):
    """Data of a document event, e.g. `doc_deleted`."""

    def __init__(self, target: Block | None, data: Any):
        super().__init__(target, data)
        self.index: int = data["index"]
        """Index of the document, before deletion if deleted."""
        self.path: str = data["path"]
        """Path of the base layer file, in Gradio cache."""


class ToolEvent(EventData):
    """Data of the `tool_selected` event."""

    def __init__(self, target: Block | None, data: Any):
        super().__init__(target, data)
        tools = target.tools if isinstance(target, Canvas) else []
        self.tool: Tool | None = next(
            (tool for tool in chain(*tools) if tool._id == data["tool"]), None
        )
        """Tool selected, or None if user unselected the active one."""


class Canvas(Component):
    """
    Displays documents, one at a time, with thumbnails of all of them, and
    hosts tools to edit the displayed one, e.g. a LassoTool.
    User adds documents by dropping images onto the canvas.
    """

    EVENTS = [  # noqa: RUF012 (Gradio API)
        Events.change,
        Events.input,
        Events.select,
        "doc_added",
        "doc_deleted",
        "doc_dropped",
        "thumb_click",
        "tool_selected",
        "empty",
        "filled",
    ]

    data_model = CanvasData

    def __init__(
        self,
        docs: CanvasValue | Sequence[DocLike] | Callable | None = None,
        *,
        tools: Sequence[Sequence[Tool]] = (),
        buttons: Sequence[Literal["fullscreen"]] = ("fullscreen",),
        fullscreen_tooltip: str = "Go fullscreen (F)",
        exit_fullscreen_tooltip: str = "Exit fullscreen mode (F)",
        caption_key: str | None = None,
        placeholder: str | None = None,
        max_zoom_levels: int = 24,
        pan_tooltip: str = "Space+drag: pan",
        label: str | None = None,
        show_label: bool | None = None,
        height: int | str | None = None,
        every: Timer | float | None = None,
        inputs: Component | Sequence[Component] | set[Component] | None = None,
        container: bool = True,
        scale: int | None = None,
        min_width: int = 160,
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
            docs: documents, as a CanvasValue or as a list of documents or images, the last one displayed. If a function is provided, the function will be called each time the app loads to set the initial value of this component.
            tools: groups of tools to edit the displayed document with, e.g. [[free_lasso, poly_lasso]] for lasso tools. A separator sets groups apart in the toolbar. User selects one tool at a time, the first one at start.
            buttons: buttons shown at the top left of the canvas. "fullscreen" toggles fullscreen, as does the F key.
            fullscreen_tooltip: tooltip of the "fullscreen" button, while canvas isn't fullscreen.
            exit_fullscreen_tooltip: tooltip of the "fullscreen" button, while canvas is fullscreen.
            caption_key: if provided, the text of the base layer image info (e.g. a PNG text chunk) at this key is shown as tooltip of the document thumbnail.
            placeholder: text shown in the canvas while it has no document, e.g. to tell user how to add one.
            max_zoom_levels: how many levels the mouse wheel can zoom the displayed document in, from its size fitting the canvas, which is the smallest. Three levels double the size. 0 disables zoom.
            pan_tooltip: hint at how to pan the zoomed document, shown for a while as user zooms in. Empty to show none.
            label: the label for this component, displayed at the top left of the canvas.
            show_label: if True, will display label.
            height: the height of the canvas, in pixels if a number, or as a CSS size.
            every: Continuously calls `value` to recalculate it if `value` is a function (has no effect otherwise). Can provide a Timer whose tick resets `value`, or a float that provides the regular interval for the reset Timer.
            inputs: Components that are used as inputs to calculate `value` if `value` is a function (has no effect otherwise). `value` is recalculated any time the inputs change.
            container: If True, will place the component in a container - providing some extra padding around its border.
            scale: relative size compared to adjacent Components. For example if Components A and B are in a Row, and A has scale=2, and B has scale=1, A will be twice as wide as B. Should be an integer. scale applies in Rows, and to top-level Components in Blocks where fill_height=True.
            min_width: minimum pixel width, will wrap if not sufficient screen space to satisfy this value. If a certain scale value results in this Component being narrower than min_width, the min_width parameter will be respected first.
            interactive: if False, user can't drop images onto the canvas. If not provided, the component is interactive unless it's only used as an event output.
            visible: If False, component will be hidden. If "hidden", component will be visually hidden and not take up space in the layout but still exist in the DOM.
            elem_id: An optional string that is assigned as the id of this component in the HTML DOM.
            elem_classes: An optional list of strings that are assigned as the classes of this component in the HTML DOM.
            render: If False, component will not render be rendered in the Blocks context. Should be used if the intention is to assign event listeners now but render the component later.
            key: in a gr.render, Components with the same key across re-renders are treated as the same component, not a new component. Properties set in 'preserved_by_key' are not reset across a re-render.
            preserved_by_key: A list of parameters from this component's constructor. Inside a gr.render() function, if a component is re-rendered with the same key, these (and only these) parameters will be preserved in the UI (if they have been changed by the user or an event listener) instead of re-rendered based on the values provided during constructor.
        """
        self.tools = [list(group) for group in tools]
        self.buttons = list(buttons)
        self.fullscreen_tooltip = fullscreen_tooltip
        self.exit_fullscreen_tooltip = exit_fullscreen_tooltip
        self.caption_key = caption_key
        self.placeholder = placeholder
        self.max_zoom_levels = max_zoom_levels
        self.pan_tooltip = pan_tooltip
        self.height = height

        super().__init__(
            label=label,
            every=every,
            inputs=inputs,
            show_label=show_label,
            container=container,
            scale=scale,
            min_width=min_width,
            interactive=interactive,
            visible=visible,
            elem_id=elem_id,
            elem_classes=elem_classes,
            value=docs,
            render=render,
            key=key,
            preserved_by_key=preserved_by_key,
        )

        for tool in chain(*self.tools):
            tool.canvas_id = self._id

    def get_config(self, cls: type[Block] | None = None) -> dict[str, Any]:
        config = super().get_config(cls)
        # Gradio only passes constructor parameters, and `docs` is the value.
        config["value"] = self.value
        # Only tool IDs go to frontend, since Gradio would otherwise
        # serialize the whole tool configs.
        config["tools"] = [[tool._id for tool in group] for group in self.tools]
        return config

    def preprocess(self, payload: CanvasData | None) -> CanvasValue:
        """
        Parameters:
            payload: the documents, and the index of the displayed one.
        Returns:
            Passes the documents as a {CanvasValue}, each layer object as an image opened (lazily) from its file.
        """
        if payload is None:
            return CanvasValue()

        docs = [
            Doc(
                [
                    Layer(
                        Image.open(layer.object.path),
                        layer.imported,
                        Path(layer.source_file) if layer.source_file else None,
                    )
                    for layer in doc.layers
                ]
            )
            for doc in payload.docs
        ]

        return CanvasValue(docs, payload.index if docs else None)

    def postprocess(self, value: CanvasValue | Sequence[DocLike] | None) -> CanvasData:
        """
        Parameters:
            value: Expects a {CanvasValue}, or a {list} of documents or images, the last one displayed.
        Returns:
            The documents to display.
        """
        if value is None:
            return CanvasData(docs=[], index=None)

        if not isinstance(value, CanvasValue):
            value = CanvasValue().add(*value)

        return CanvasData(
            docs=[
                DocData(
                    layers=[
                        LayerData(
                            object=self._file(layer.object),
                            imported=layer.imported,
                            source_file=str(layer.source_file)
                            if layer.source_file
                            else None,
                        )
                        for layer in doc.layers
                    ],
                    caption=self._caption(doc.image),
                )
                for doc in value.docs
            ],
            index=value.index,
        )

    def _file(self, image: Image.Image) -> FileData:
        """File of an image, as is if opened from one, else saved to cache."""
        path = getattr(image, "filename", "") or processing_utils.save_pil_to_cache(
            image, cache_dir=self.GRADIO_CACHE, format="png"
        )

        return FileData(path=str(path), orig_name=Path(path).name)

    def _caption(self, image: Image.Image) -> str | None:
        if not self.caption_key:
            return None

        caption = image.info.get(self.caption_key)
        return caption if isinstance(caption, str) else None

    def example_payload(self) -> Any:
        return {"docs": [], "index": None}

    def example_value(self) -> Any:
        return CanvasValue()
