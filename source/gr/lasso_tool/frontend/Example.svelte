<script lang="ts">
	import type { Point } from "./lasso";

	export let value: Point[] | null;
	export let type: "gallery" | "table";
	export let selected = false;
</script>

<div
	class:table={type === "table"}
	class:gallery={type === "gallery"}
	class:selected
>
	{#if value}
		{value.length} points
	{:else}
		—
	{/if}
</div>

<style>
	.gallery {
		padding: var(--size-1) var(--size-2);
	}

	div {
		overflow: hidden;
		white-space: nowrap;
	}
</style>
