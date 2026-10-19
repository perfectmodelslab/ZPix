/*
 * ZPix Gradio app custom JavaScript.
 */

// Delegate events to work with Gradio rendering.

document.addEventListener("mouseover", (event) => {
    if (event.target.closest("#prompt textarea")) {
        const prompt = document.getElementById("prompt")
        if (prompt?.title) hidePromptTooltip(prompt)
    }
})

document.addEventListener("mouseleave", (event) => {
    if (event.target.closest?.("#prompt textarea")) {
        const prompt = document.getElementById("prompt")
        if (prompt?.dataset.title) restorePromptTooltip(prompt)
    }
}, true) // Required because mouseleave doesn't bubble.

// Capture phase to decide before Gradio handles the drop.
document.addEventListener("drop", uploadDroppedImage, true)

// On Windows, a file drop leaves focus to the file explorer:
// ZPix launcher takes it back. Capture as the above can stop it.
document.addEventListener("drop", () => {
    window.chrome?.webview?.postMessage("getWindowFocus")
}, true)

// A refresh can close the server (see app.unload)
// or disturb the app state.
if (performance.getEntriesByType("navigation")[0]?.type === "reload") {
    const notice = document.createElement("div")
    notice.className = "refresh-notice"
    notice.textContent = "Page reload broke app."
    notice.textContent += " Close this tab or window and run ZPix again."
    document.body.replaceChildren(notice)
}

/**
 * Hide the prompt tooltip on its textarea mouseover
 * so tooltip doesn't cause inconvenience to the user.
 * @param {HTMLElement} prompt
 */
function hidePromptTooltip(prompt) {
    prompt.dataset.title = prompt.title
    prompt.title = ""
}

/**
 * Restore the prompt tooltip on its textarea mouseleave.
 * @param {HTMLElement} prompt
 */
function restorePromptTooltip(prompt) {
    prompt.title = prompt.dataset.title
    delete prompt.dataset.title
}

/**
 * Upload an image dropped from the canvas, to recover its prompt
 * or to add it as a reference, since Gradio only reads dropped files.
 * @param {DragEvent} event
 */
async function uploadDroppedImage(event) {
    const zone = event.target.closest?.("#prompt, #reference-images")
    if (!zone) return

    // Gradio uploads from this file input, which it removes from a single
    // reference image zone once one was added, then crashes on the next drop.
    const input = zone.querySelector("input[type=file]")
    if (!input) {
        event.preventDefault()
        event.stopPropagation()
        // Let Gradio clear the drag highlight of the drop we just stopped.
        event.target.dispatchEvent(new DragEvent("dragleave", { bubbles: true }))
        return
    }

    const imageUrl = event.dataTransfer.getData("text/uri-list")
    // Chrome drops a canvas image as a file, Firefox and select tools
    // as its URL.
    if (!imageUrl || event.dataTransfer.files.length) return

    event.preventDefault() // Firefox would write the URL in the prompt.

    const response = await fetch(imageUrl)
    if (!response.ok) return // Image file was deleted meanwhile.

    const blob = await response.blob()
    const transfer = new DataTransfer()
    transfer.items.add(new File([blob], "image.png", { type: blob.type }))

    input.files = transfer.files
    input.dispatchEvent(new Event("change"))
}
