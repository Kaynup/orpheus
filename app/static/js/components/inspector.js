/**
 * Pipeline Inspector & Real-Time Stepper Component
 */

const QA_STEPS = [
    "step-query-received",
    "step-query-embedded",
    "step-retrieving-chunks",
    "step-context-selected",
    "step-prompt-prepared",
    "step-generating-answer",
];

const QA_STAGE_MAP = {
    "QUERY_RECEIVED": "step-query-received",
    "QUERY_EMBEDDED": "step-query-embedded",
    "RETRIEVING_CHUNKS": "step-retrieving-chunks",
    "CONTEXT_SELECTED": "step-context-selected",
    "PROMPT_PREPARED": "step-prompt-prepared",
    "GENERATING_ANSWER": "step-generating-answer",
    "ANSWER_COMPLETE": "step-generating-answer",
};

const INGEST_STEPS = [
    "doc-received",
    "text-extracted",
    "chunks-created",
    "embeddings-generated",
    "vectors-stored",
];

const INGEST_STAGE_MAP = {
    "DOC_RECEIVED": "istep-doc-received",
    "TEXT_EXTRACTED": "istep-text-extracted",
    "CHUNKS_CREATED": "istep-chunks-created",
    "EMBEDDINGS_GENERATED": "istep-embeddings-generated",
    "VECTORS_STORED": "istep-vectors-stored",
    "INDEXING_COMPLETE": "istep-vectors-stored",
};

export function resetQAStepper() {
    QA_STEPS.forEach(s => {
        const el = document.getElementById(s);
        if (el) {
            el.className = "step-item";
            const details = el.querySelector(".step-details");
            if (details) details.textContent = "Waiting...";
        }
    });
}

export function updateQAStep(stage, status, message) {
    const elementId = QA_STAGE_MAP[stage];
    if (!elementId) return;

    const el = document.getElementById(elementId);
    if (el) {
        el.className = `step-item ${status.toLowerCase()}`;
        const details = el.querySelector(".step-details");
        if (details) details.textContent = message;
    }
}

export function resetIngestStepper() {
    INGEST_STEPS.forEach(s => {
        const el = document.getElementById(`istep-${s}`);
        if (el) {
            el.className = "step-item";
            const details = el.querySelector(".step-details");
            if (details) details.textContent = "Waiting...";
        }
    });
}

export function updateIngestStep(stage, status, message) {
    const elementId = INGEST_STAGE_MAP[stage];
    if (!elementId) return;

    const el = document.getElementById(elementId);
    if (el) {
        el.className = `step-item ${status.toLowerCase()}`;
        const details = el.querySelector(".step-details");
        if (details) details.textContent = message;
    }
}

export function updateDiagnosticMetrics(res) {
    const metricsPanel = document.getElementById("inspector-metrics");
    if (metricsPanel) metricsPanel.style.display = "block";

    const elLatency = document.getElementById("metric-latency");
    const elChunks = document.getElementById("metric-chunks");
    const elSim = document.getElementById("metric-sim");
    const elTokens = document.getElementById("metric-tokens");

    if (elLatency) elLatency.textContent = `${res.duration_ms} ms`;
    if (elChunks) elChunks.textContent = res.retrieved_chunks ? res.retrieved_chunks.length : 0;
    if (elSim) {
        const topSim = (res.retrieved_chunks && res.retrieved_chunks.length > 0)
            ? res.retrieved_chunks[0].similarity.toFixed(3)
            : "0.000";
        elSim.textContent = topSim;
    }
    if (elTokens) {
        const totalTokens = (res.generation && res.generation.total_tokens !== undefined)
            ? res.generation.total_tokens
            : 0;
        elTokens.textContent = totalTokens;
    }
}
