# Gradio Canvas

A custom component displaying documents one at a time, with thumbnails of all of them, and hosting tools to edit the displayed one, e.g. a [LassoTool](../lasso_tool/README.md).

```python
from gradio_canvas import Canvas, CanvasValue, DocEvent

canvas = Canvas(
    [image],  # PIL images or documents
    tools=[lasso],
    caption_key="prompt",
    placeholder="Drop an image",
    height="80vh",
)

next_btn.click(lambda c: c.select_next_doc(), canvas, canvas)
canvas.doc_deleted(lambda e: print(f"Deleted {e.path}"), None, None)
```

## Value

A document (`Doc`) is a stack of layers (`Layer`), from the base one up. For now, a layer object is a PIL image, served from its file if opened from one (e.g. with `Image.open`), else saved to the Gradio cache as PNG.

Listeners get a `CanvasValue`, holding the documents (`docs`) and the index of the displayed one (`index`, `None` only if there is none). Each layer object is an image opened (lazily) from its file in the Gradio cache, so its PNG text chunks are in its `info`. Listeners may return a `CanvasValue`, or a list of documents or images, the last one displayed.

`CanvasValue` methods change it in place and return it:

| Member | |
|---|---|
| `doc` | Displayed document, if any. `doc.image` is its base layer object. |
| `is_empty` | Whether there is no document. |
| `add(*docs, select=True)` | Add documents or images, and display the last one, unless `select` is False. |
| `delete(index=None)` | Delete a document, the displayed one by default. The next one, else the previous one, takes its place. |
| `select_doc(index)` | Display a document. Negative indexes count from the end. |
| `select_next_doc()`, `select_prev_doc()` | Display the next or previous document, if any. |

## Events

Events of a document pass a `DocEvent` to a listener argument annotated with it: `index` of the document (before deletion if deleted) and `path` of its base layer file, in the Gradio cache.

| Event | Triggered when | Data |
|---|---|---|
| `change` | documents or displayed document change, by user or by a listener | |
| `input` | user changes them: drop, thumbnail click, keyboard | |
| `select` | another document is displayed | `DocEvent` |
| `doc_added` | a document is added, by user or by a listener | `DocEvent` |
| `doc_deleted` | a document is deleted | `DocEvent` |
| `doc_dropped` | user dropped an image onto the canvas, before `doc_added` | `DocEvent` |
| `thumb_click` | user clicks a thumbnail | `DocEvent` |
| `tool_selected` | user selects a tool, or unselects the active one | `ToolEvent`: `tool`, or None |
| `empty` | the last document is deleted | |
| `filled` | a document is added to an empty canvas | |

## User interface

- The displayed document fits the canvas. A drag of it, or of a thumbnail, drops its image onto another element that accepts drops, as its URL (`text/uri-list`).
- Thumbnails (`thumbs=True`) follow the displayed document. A click displays a document, and so do <kbd>←</kbd>, <kbd>→</kbd>, <kbd>Home</kbd> and <kbd>End</kbd> while a thumbnail has focus.
- Images dropped from outside (e.g. files) are added, the last one displayed, unless `interactive` is False.
- `buttons` are at the top left, and tool buttons in a column below: `"fullscreen"` toggles fullscreen, as does the F key.
- `placeholder` is shown in the canvas while it has no document.

## Tools

A tool is a component which renders nothing in place: canvas passes `tools` its ID (`canvas_id` attribute), by which they find its tool host in the frontend, as `host.ts` defines it. The host gives the element holding the displayed document, for overlays, its base layer image, and a toolbar, where each tool adds its button. User selects one tool at a time, the first one at start.

## Development

Requires Node.js 24.

- `build.ps1 -Target grc` (at project root) builds the wheel ZPix installs from `wheels` directory. Rebuild after any component change.
- `dev.ps1` runs the hot reload demo.

On Gradio update, pin `svelte` in `frontend/package.json` to the version Gradio's frontend uses, then rebuild the wheel.
