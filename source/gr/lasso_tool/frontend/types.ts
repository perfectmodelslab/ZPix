import type { ILoadingStatus as LoadingStatus } from "@gradio/statustracker";
import type { Point } from "./lasso";

export interface LassoToolProps {
	value: Point[] | null;
	canvas_id: number | null;
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
