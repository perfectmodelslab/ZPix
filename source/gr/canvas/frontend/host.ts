/**
 * Tool host: what a canvas gives its tools, e.g. LassoTool, in the frontend.
 *
 * Canvas and tools mount in any order, so they meet on window: canvas
 * announces its host as it mounts (`HOST_EVENT`), and answers tools asking
 * for it once mounted (`REQUEST_EVENT`). Both carry the canvas ID.
 */

export const HOST_EVENT = "canvas-host";
export const REQUEST_EVENT = "canvas-host-request";

/** Detail of `REQUEST_EVENT`. */
export interface HostRequest {
	canvas_id: number;
	resolve: (host: CanvasHost) => void;
}

/** Emits "tool-change" as user selects a tool. */
export class CanvasHost extends EventTarget {
	#tool: number | null;

	constructor(
		/** Canvas ID. */
		readonly id: number,
		/** Positioned element holding the displayed document: overlays go in it. */
		readonly stage: HTMLElement,
		/** Base layer of the displayed document, without `src` if none. */
		readonly image: HTMLImageElement,
		/** Canvas area: a drag leaving it goes to another element. */
		readonly area: HTMLElement,
		/** Group of tool buttons. */
		readonly toolbar: HTMLElement,
		/** Tool IDs, in the order tools were given to canvas. */
		readonly tool_ids: readonly number[]
	) {
		super();
		this.#tool = tool_ids[0] ?? null;
	}

	/** ID of the active tool, if any. */
	get tool(): number | null {
		return this.#tool;
	}

	set tool(id: number | null) {
		if (id === this.#tool) return;

		this.#tool = id;
		this.#mark_tools();
		this.dispatchEvent(new Event("tool-change"));
	}

	/** Press the button of the active tool, release the others. */
	#mark_tools(): void {
		for (const el of this.toolbar.children as HTMLCollectionOf<HTMLElement>) {
			el.querySelector("button")?.setAttribute(
				"aria-pressed",
				String(Number(el.dataset.tool) === this.#tool)
			);
		}
	}

	/** Add the button of a tool to the toolbar, in tools order. */
	add_tool(id: number, button: HTMLElement): void {
		const rank = (el: Element): number =>
			this.tool_ids.indexOf(Number((el as HTMLElement).dataset.tool));

		button.dataset.tool = String(id);
		const next = [...this.toolbar.children].find((el) => rank(el) > rank(button));
		this.toolbar.insertBefore(button, next ?? null);
		this.#mark_tools();
	}
}
