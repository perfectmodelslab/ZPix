<script lang="ts">
	import { IconButton } from "@gradio/atoms";
	import { Maximize, Minimize } from "@gradio/icons";

	let {
		fullscreen,
		onclick,
		label,
		exit_label,
		hovered
	}: {
		fullscreen: boolean;
		onclick: (fullscreen: boolean) => void;
		label: string;
		exit_label: string;
		/** Whether pointer is over the area of the shortcut. */
		hovered: () => boolean;
	} = $props();

	function is_text_field(target: EventTarget | null): boolean {
		return (
			target instanceof HTMLElement &&
			(target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
		);
	}

	/**
	 * F toggles fullscreen, unless user types text with pointer away from the
	 * area.
	 */
	function on_keydown(event: KeyboardEvent): void {
		if (
			event.key.toLowerCase() !== "f" ||
			event.repeat ||
			event.defaultPrevented ||
			event.altKey ||
			event.ctrlKey ||
			event.metaKey ||
			(is_text_field(event.target) && !hovered())
		) {
			return;
		}

		event.preventDefault();
		onclick(!fullscreen);
	}
</script>

<svelte:window onkeydown={on_keydown} />

{#if fullscreen}
	<IconButton Icon={Minimize} label={exit_label} onclick={() => onclick(false)} />
{:else}
	<IconButton Icon={Maximize} {label} onclick={() => onclick(true)} />
{/if}
