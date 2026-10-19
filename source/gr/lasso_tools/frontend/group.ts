/**
 * Lasso tools of a canvas, e.g. a FreehandLassoTool and a PolygonalLassoTool,
 * share one selection, drawn on one overlay, and shortcuts: they differ only
 * in how user draws.
 *
 * Each tool class loads this module apart, so the group lives on the canvas
 * host, under a global symbol, for the tools of a canvas to find it.
 */

import type { CanvasHost } from "./canvas_host";
import {
	IS_MAC,
	LassoOverlay,
	OVERLAY_TAG,
	primary_key,
	type Lasso,
	type Mode
} from "./lasso";

const GROUP_KEY = Symbol.for("gradio_lasso_tools.group");

export interface LassoToolState {
	mode: Mode;
	visible: boolean;
	interactive: boolean;
	marching_ants: boolean;
	smoothing: number;
	tooltips: [string, string];
}

export interface LassoTool {
	readonly id: number;
	state: LassoToolState;
	/** Selection changed: by user if `input`, else by another tool's value. */
	on_change(value: Lasso | null, input: boolean): void;
}

function is_text_field(target: EventTarget | null): boolean {
	return (
		target instanceof HTMLElement &&
		(target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
	);
}

export class LassoGroup {
	readonly overlay: LassoOverlay;
	#tools = new Map<number, LassoTool>();
	/** Lasso tool user selected last, which L selects back. */
	#current: number | null = null;

	#on_tool_change = (): void => this.refresh();

	/**
	 * L selects the lasso tool user selected last, or the next one if a lasso
	 * tool is selected, unless user types text with pointer away from the
	 * canvas area.
	 * While a lasso tool is selected, Ctrl+D (Cmd+D on macOS) clears the
	 * selection, Ctrl+Shift+D selects it back, and Ctrl+Shift+I inverts it.
	 */
	#on_keydown = (event: KeyboardEvent): void => {
		if (
			event.defaultPrevented ||
			event.repeat ||
			event.altKey ||
			(is_text_field(event.target) && !this.host.area.matches(":hover"))
		) {
			return;
		}

		const key = event.key.toLowerCase();
		const primary = primary_key(event);
		// The other one of Ctrl and Cmd: Ctrl+click is a right click on macOS.
		if (IS_MAC ? event.ctrlKey : event.metaKey) return;

		if (!primary && key === "l") this.#select_tool(event);
		else if (primary && (key === "d" || (key === "i" && event.shiftKey))) {
			this.#edit_selection(key, event);
		}
	};

	/** Group of the lasso tools of a canvas. */
	static of(host: CanvasHost): LassoGroup {
		const slot = host as unknown as Record<symbol, LassoGroup | undefined>;
		return (slot[GROUP_KEY] ??= new LassoGroup(host));
	}

	private constructor(readonly host: CanvasHost) {
		this.overlay = document.createElement(OVERLAY_TAG) as LassoOverlay;
		host.doc_el.append(this.overlay);
		this.overlay.area = host.area;
		this.overlay.bands = host.frame;
		this.overlay.target = host.image;

		this.overlay.addEventListener("lasso-change", (event) => {
			const value = (event as CustomEvent<Lasso | null>).detail;
			for (const tool of this.#tools.values()) tool.on_change(value, true);
		});
		host.addEventListener("tool-change", this.#on_tool_change);
		window.addEventListener("keydown", this.#on_keydown);
	}

	/** Add a tool, with its value, which is the selection unless null. */
	join(tool: LassoTool, value: Lasso | null): void {
		this.#tools.set(tool.id, tool);

		if (value) this.set_value(tool.id, value);
		else if (this.overlay.value) tool.on_change(this.overlay.value, false);

		this.refresh();
	}

	leave(id: number): void {
		this.#tools.delete(id);
		if (this.#tools.size) {
			this.refresh();
			return;
		}

		this.host.removeEventListener("tool-change", this.#on_tool_change);
		window.removeEventListener("keydown", this.#on_keydown);
		this.overlay.target = null;
		this.overlay.remove();
		delete (this.host as unknown as Record<symbol, unknown>)[GROUP_KEY];
	}

	/** Selection set by an event to a tool's value: the other tools follow. */
	set_value(id: number, value: Lasso | null): void {
		this.overlay.value = value;
		for (const tool of this.#tools.values()) {
			if (tool.id !== id) tool.on_change(value, false);
		}
	}

	/** Apply tool states, e.g. after one changed. */
	refresh(): void {
		const active = this.#active();
		if (active) this.#current = active.id;

		// Selection shows as the active tool sets, else as the first one.
		const shown = active ?? this.#ordered()[0];
		const overlay = this.overlay;

		overlay.mode = active?.state.mode ?? overlay.mode;
		overlay.disabled = !active || !this.#selectable(active);
		overlay.hidden = ![...this.#tools.values()].some((tool) => tool.state.visible);
		overlay.toggleAttribute("static", shown?.state.marching_ants === false);
		overlay.smoothing = shown?.state.smoothing ?? 1;
		overlay.tooltips = shown?.state.tooltips ?? ["", ""];
	}

	#active(): LassoTool | undefined {
		return this.host.tool === null ? undefined : this.#tools.get(this.host.tool);
	}

	/** Tools in the order they were given to canvas. */
	#ordered(): LassoTool[] {
		return this.host.tool_groups
			.flat()
			.flatMap((id) => this.#tools.get(id) ?? []);
	}

	#selectable(tool: LassoTool): boolean {
		return tool.state.visible && tool.state.interactive;
	}

	#select_tool(event: KeyboardEvent): void {
		const tools = this.#ordered().filter((tool) => this.#selectable(tool));
		if (!tools.length) return;

		const active = this.#active();
		const tool = active
			? tools[(tools.indexOf(active) + 1) % tools.length]
			: (tools.find((tool) => tool.id === this.#current) ?? tools[0]);

		event.preventDefault();
		this.host.tool = tool.id;
	}

	#edit_selection(key: string, event: KeyboardEvent): void {
		const active = this.#active();
		if (!active || !this.#selectable(active)) return;

		event.preventDefault();
		if (key === "i") this.overlay.invert();
		else if (event.shiftKey) this.overlay.reselect();
		else this.overlay.clear();
	}
}
