import type { FileData } from "@gradio/client";
import type { ILoadingStatus as LoadingStatus } from "@gradio/statustracker";

export interface LayerData {
	object: FileData;
	imported: boolean;
	source_file: string | null;
}

export interface DocData {
	layers: LayerData[];
	caption: string | null;
}

export interface CanvasData {
	docs: DocData[];
	index: number | null;
}

export interface CanvasProps {
	value: CanvasData | null;
	tools: number[][];
	buttons: "fullscreen"[];
	fullscreen_tooltip: string;
	exit_fullscreen_tooltip: string;
	placeholder: string | null;
	max_zoom_levels: number;
	pan_tooltip: string;
	height: number | string | null;
}

export interface DocEventData {
	index: number;
	path: string;
}

export interface CanvasEvents {
	change: never;
	input: never;
	select: DocEventData;
	doc_added: DocEventData;
	doc_deleted: DocEventData;
	doc_dropped: DocEventData;
	thumb_click: DocEventData;
	tool_selected: { tool: number | null };
	empty: never;
	filled: never;
	error: string;
	clear_status: LoadingStatus;
}
