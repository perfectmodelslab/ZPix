import type { FileData } from "@gradio/client";
import type { ILoadingStatus as LoadingStatus } from "@gradio/statustracker";

export interface LayerData {
	object: FileData;
}

export interface DocData {
	layers: LayerData[];
	caption: string | null;
}

export interface CanvasData {
	docs: DocData[];
	/** Index of the displayed document, null only if there is none. */
	index: number | null;
}

export interface CanvasProps {
	value: CanvasData | null;
	tools: number[];
	buttons: "fullscreen"[];
	fullscreen_tooltip: string;
	exit_fullscreen_tooltip: string;
	thumbs: boolean;
	placeholder: string | null;
	height: number | string | null;
}

export interface DocEventData {
	index: number;
	/** Path of the base layer file. */
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
