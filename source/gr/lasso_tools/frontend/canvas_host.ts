/**
 * Tool host a canvas gives its tools, as gradio_canvas defines it (see its
 * `host.ts`): this tool asks for it on window, or waits for it to mount.
 */

export const HOST_EVENT = "canvas-host";
export const REQUEST_EVENT = "canvas-host-request";

/** Emits "tool-change" as user selects a tool. */
export interface CanvasHost extends EventTarget {
	readonly id: number;
	readonly stage: HTMLElement;
	readonly image: HTMLImageElement;
	readonly area: HTMLElement;
	/** Tool IDs by group, in the order tools were given to canvas. */
	readonly tool_groups: readonly (readonly number[])[];
	tool: number | null;
	add_tool(id: number, button: HTMLElement): void;
}

/** Call `attach` with the host of a canvas, once it's mounted. */
export function find_host(
	canvas_id: number,
	attach: (host: CanvasHost) => void
): () => void {
	const on_host = (event: Event): void => {
		const host = (event as CustomEvent<CanvasHost>).detail;
		if (host.id === canvas_id) attach(host);
	};

	window.addEventListener(HOST_EVENT, on_host);
	window.dispatchEvent(
		new CustomEvent(REQUEST_EVENT, { detail: { canvas_id, resolve: attach } })
	);

	return () => window.removeEventListener(HOST_EVENT, on_host);
}
