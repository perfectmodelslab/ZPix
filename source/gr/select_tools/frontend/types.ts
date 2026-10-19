import type { ILoadingStatus as LoadingStatus } from "@gradio/statustracker";
import type { Mode, Selection } from "./selection";

export interface SelectToolProps {
	value: Selection | null;
	canvas_id: number | null;
	/** How user draws. */
	mode: Mode;
	enable_tooltip: string | null;
	disable_tooltip: string | null;
	draw_tooltip: string | null;
	clear_tooltip: string | null;
	marching_ants: boolean;
	smoothing: number;
}

export interface SelectToolEvents {
	change: never;
	input: never;
	drawn: never;
	cleared: never;
	clear_status: LoadingStatus;
}
