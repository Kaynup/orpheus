/**
 * Centralized REST & SSE Transport Client for Doc-QA Assistant
 */

export async function fetchStatus() {
    const res = await fetch("/api/status");
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
}

export async function fetchDocuments() {
    const res = await fetch("/api/documents");
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
}

export async function deleteDocument(docId) {
    const res = await fetch(`/api/documents/${docId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`Failed to delete document: ${res.status}`);
    return await res.json();
}

export async function loadSamples() {
    const res = await fetch("/api/samples", { method: "POST" });
    if (!res.ok) throw new Error(`Failed to load samples: ${res.status}`);
    return await res.json();
}

export async function resetDatabase() {
    const res = await fetch("/api/reset", { method: "POST" });
    if (!res.ok) throw new Error(`Failed to reset database: ${res.status}`);
    return await res.json();
}

export async function runEvaluation() {
    const res = await fetch("/api/evaluate", { method: "POST" });
    if (!res.ok) throw new Error(`Evaluation failed with status ${res.status}`);
    return await res.json();
}

/**
 * Generic SSE stream reader for endpoints producing text/event-stream chunks.
 */
async function consumeSSEStream(response, { onEvent, onFinal, onError }) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop(); // keep partial remainder

        for (const line of lines) {
            if (line.startsWith("data: ")) {
                try {
                    const payload = JSON.parse(line.substring(6));
                    if (payload.event && onEvent) {
                        onEvent(payload.event);
                    }
                    if (payload.__FINAL_RESULT__ && onFinal) {
                        onFinal(payload.__FINAL_RESULT__);
                    }
                    if (payload.__ERROR__ && onError) {
                        onError(payload.__ERROR__);
                    }
                } catch (pErr) {
                    console.error("SSE JSON parse error:", pErr);
                }
            }
        }
    }
}

export async function streamQuery({ query, top_k, model }, callbacks) {
    const response = await fetch("/api/query/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k, model }),
    });
    if (!response.ok) throw new Error(`Query stream failed: ${response.status}`);
    await consumeSSEStream(response, callbacks);
}

export async function streamIngest(formData, callbacks) {
    const response = await fetch("/api/ingest/stream", {
        method: "POST",
        body: formData,
    });
    if (!response.ok) throw new Error(`Ingest stream failed: ${response.status}`);
    await consumeSSEStream(response, callbacks);
}
