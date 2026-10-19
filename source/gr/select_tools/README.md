# Gradio Select Tools

Custom components to select regions of the document displayed by a [Canvas](../canvas/README.md), which hosts them as tools, e.g. to mask a region to edit: `FreehandLassoTool` draws a lasso freehand, `PolygonalLassoTool` with straight segments, `RectangleSelectTool` drags a rectangle, and `EllipseSelectTool` an ellipse. All derive from `SelectTool`, which can't be instantiated itself, but tells select tools apart, e.g. with `isinstance`.

```python
from gradio_canvas import Canvas
from gradio_select_tools import (
    EllipseSelectTool,
    FreehandLassoTool,
    PolygonalLassoTool,
    RectangleSelectTool,
    selection_to_mask,
)

free_lasso = FreehandLassoTool(
    enable_tooltip="Enable lasso (L)",
    disable_tooltip="Disable lasso",
    draw_tooltip="...",
    clear_tooltip="...",
)
poly_lasso = PolygonalLassoTool(
    enable_tooltip="Enable polygonal lasso (L)",
    disable_tooltip="Disable polygonal lasso",
    draw_tooltip="...",
    clear_tooltip="...",
)
rect_select = RectangleSelectTool(
    enable_tooltip="Enable rectangular selection (M)",
    disable_tooltip="Disable rectangular selection",
    draw_tooltip="...",
    clear_tooltip="...",
)
ellipse_select = EllipseSelectTool(
    enable_tooltip="Enable elliptical selection (M)",
    disable_tooltip="Disable elliptical selection",
    draw_tooltip="...",
    clear_tooltip="...",
)
canvas = Canvas(tools=[[free_lasso, poly_lasso], [rect_select, ellipse_select]])

# Later, e.g. in an event listener:
mask = selection_to_mask(outlines, image.size)
```

Value is a list of outlines, each a list of `(x, y)` vertices in pixels of the base layer image, or `None` when nothing is selected. A point is selected if it lies inside an odd number of outlines, so an outline inside another one is a hole. A rectangle is 4 vertices, and an ellipse as many as needed to stay within a quarter of a pixel of it.

## Select tools of a canvas

Select tools of a canvas share one selection: whichever draws it, their values follow each other, so an app may only read one of them. The selection persists when the canvas displays another document, scaled to its resolution if it differs.

Each tool button, with `enable_tooltip` as tooltip (`disable_tooltip` while selected), goes to the canvas toolbar. User selects only while a select tool is selected, and its `interactive` is not False. The selection shows while any select tool is visible.

| Shortcut | Action |
|---|---|
| <kbd>L</kbd> | Select the lasso tool selected last, the first one at start, or the next one, in `tools` order, while a lasso tool is selected. Only its button deselects it. |
| <kbd>M</kbd> | Same for the rectangle and ellipse tools. |
| <kbd>Ctrl</kbd>+<kbd>D</kbd> | Clear the selection. |
| <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>D</kbd> | Select back the last selection cleared. |
| <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>I</kbd> | Invert the selection: the whole image if nothing is selected. |

<kbd>Ctrl</kbd> is <kbd>Cmd</kbd> on macOS. Selection shortcuts work while a select tool is selected. No shortcut works while user types text with the pointer away from the canvas.

Over the image, as user starts a new outline:

- it replaces the selection at once,
- with <kbd>Shift</kbd> held, it rather adds the region it encloses to the selection, even apart from the regions already selected, with <kbd>Alt</kbd> held, subtracts it, which may cut a region in two or leave a hole, and with both held, intersects it. The cursor shows a plus, minus or times sign while these are held. The selection stays as is if nothing is left,
- <kbd>Esc</kbd> cancels the outline being drawn, which brings the selection back,
- a drag leaving the canvas, before any segment is done, rather drops the image onto another element that accepts drops, e.g. a prompt left of the canvas, as its URL (`text/uri-list`).

The outline closes from its last vertex back to its first one, then it marches (pass `marching_ants=False` to keep it still). An outline enclosing nothing clears the selection.

### FreehandLassoTool

- A drag draws a line following the pointer, and release closes it. Each vertex is averaged with its neighbor on each side, which smooths the jitter of the hand as user draws (pass `smoothing=0` to keep the lasso as drawn, or more neighbors to smooth it more),
- releasing with <kbd>Alt</kbd> held rather goes on with straight segments: clicks with <kbd>Alt</kbd> held add vertices, and releasing <kbd>Alt</kbd> while dragging goes freehand again. Releasing <kbd>Alt</kbd> otherwise closes the lasso, as does a click without it,
- <kbd>Alt</kbd>+<kbd>Delete</kbd> (or <kbd>Backspace</kbd>) removes the last segment,
- a click clears the selection, unless <kbd>Shift</kbd> or <kbd>Alt</kbd> is held.

### PolygonalLassoTool

- A click sets the first vertex, then each click the end of a straight segment, which follows the pointer meanwhile, even over the bands around the image. <kbd>Shift</kbd> snaps it to a multiple of 45°,
- a drag with <kbd>Alt</kbd> held draws freehand, smoothed as FreehandLassoTool does, until release,
- <kbd>Delete</kbd> (or <kbd>Backspace</kbd>) removes the last segment, and so on, the lasso itself once none is left,
- a click on the first vertex closes the lasso: the cursor shows a circle there. So do a double-click, and a click with <kbd>Ctrl</kbd> (<kbd>Cmd</kbd> on macOS) held, which adds a vertex first,
- selecting another tool closes the lasso too.

### RectangleSelectTool and EllipseSelectTool

- A drag selects the rectangle, or the ellipse, from the press to the pointer, and release applies it. It's clipped to the image,
- <kbd>Shift</kbd> held while dragging constrains it to a square, or a circle, in any direction,
- <kbd>Alt</kbd> held while dragging draws it from its center, the press,
- as in Photoshop, while something is selected, <kbd>Shift</kbd> or <kbd>Alt</kbd> held at the press rather adds or subtracts: release it and press it again while dragging to constrain or draw from center,
- a drag from inside the selection, without <kbd>Shift</kbd> or <kbd>Alt</kbd>, moves it: the cursor shows a move icon there,
- a click clears the selection, unless <kbd>Shift</kbd> or <kbd>Alt</kbd> is held.

## Credits

The outline drawn follows the `--select-tool-color` CSS variable, the Gradio accent color by default. The cursors and button icons are the [Lucide](https://lucide.dev) lasso icon and its polygonal variant, the square dashed icon, with less rounded corners and square caps, and the circle dashed and move icons (ISC License). Selections are combined with [polygon-clipping](https://github.com/mfogel/polygon-clipping) (MIT License). Their notices are in `NOTICE.txt`, which the wheel includes.

## Development

Requires Node.js 24.

All tools share the frontend: Gradio serves the one next to a component module. They only set `MODE`, which tells it how user draws: the rest is in `SelectTool`.

- `build.ps1 -Target grc` (at project root) builds the wheel ZPix installs from `wheels` directory. Rebuild after any component change.
- The hot reload demo runs from project root, in PowerShell:

  ```powershell
  $env:GRADIO_ANALYTICS_ENABLED = "False"
  .venv\Scripts\gradio.exe cc dev source\gr\select_tools\demo\app.py --component-directory source\gr\select_tools
  ```

On Gradio update, pin `svelte` in `frontend/package.json` to the version Gradio's frontend uses, then rebuild the wheel.
