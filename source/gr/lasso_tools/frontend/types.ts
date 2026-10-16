import type { ILoadingStatus as LoadingStatus } from "@gradio/statustracker";
import type { Lasso } from "./lasso";

export interface LassoToolProps {
	value: Lasso | null;
	canvas_id: number | null;
	/** Whether user clicks vertices joined by straight segments, else drags freehand. */
	polygonal: boolean;
	enable_tooltip: string | null;
	disable_tooltip: string | null;
	draw_tooltip: string | null;
	clear_tooltip: string | null;
	marching_ants: boolean;
	smoothing: number;
}

export interface LassoToolEvents {
	change: never;
	input: never;
	drawn: never;
	cleared: never;
	clear_status: LoadingStatus;
}
