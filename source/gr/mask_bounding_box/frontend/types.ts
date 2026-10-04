import type { ILoadingStatus as LoadingStatus } from "@gradio/statustracker";
import type { BoundingBox } from "./overlay";

export interface MaskBoundingBoxProps {
	value: BoundingBox | null;
	gallery_elem_id: string | null;
	draw_tooltip: string | null;
	clear_tooltip: string | null;
}

export interface MaskBoundingBoxEvents {
	change: never;
	input: never;
	drawn: never;
	cleared: never;
	clear_status: LoadingStatus;
}
