/**
 * Document Ingestion & Storage Management Component
 */

import { fetchDocuments, deleteDocument, loadSamples, resetDatabase, streamIngest, fetchStatus } from "../modules/api.js";
import { resetIngestStepper, updateIngestStep } from "./inspector.js";
import { renderChatDocsRibbon, renderModelDropdown } from "./chat.js";

let activeFile = null;

export function initIngestion() {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const selectedFileInfo = document.getElementById("selected-file-info");
    const selectedFileName = document.getElementById("selected-file-name");
    const btnClearFile = document.getElementById("btn-clear-file");
    const chunkSizeInput = document.getElementById("chunk-size-input");
    const chunkOverlapInput = document.getElementById("chunk-overlap-input");
    const btnUploadSubmit = document.getElementById("btn-upload-submit");
    const uploadForm = document.getElementById("upload-form");
    const btnRefreshDocs = document.getElementById("btn-refresh-docs");
    const btnLoadSamples = document.getElementById("btn-load-samples");
    const btnResetDb = document.getElementById("btn-reset-db");

    if (!dropZone || !fileInput) return;

    function handleFile(file) {
        if (!file) return;
        const validExts = [".txt", ".pdf"];
        const ext = "." + file.name.split(".").pop().toLowerCase();
        if (!validExts.includes(ext)) {
            alert("Only .txt and .pdf files are supported.");
            return;
        }

        activeFile = file;
        selectedFileName.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        selectedFileInfo.style.display = "flex";
        btnUploadSubmit.disabled = false;
    }

    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        if (e.dataTransfer.files.length > 0) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0]);
        }
    });

    btnClearFile.addEventListener("click", () => {
        activeFile = null;
        fileInput.value = "";
        selectedFileInfo.style.display = "none";
        btnUploadSubmit.disabled = true;
    });

    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!activeFile) return;

        btnUploadSubmit.disabled = true;
        btnUploadSubmit.textContent = "Ingesting...";
        resetIngestStepper();

        const chunkSize = parseInt(chunkSizeInput.value, 10) || 500;
        const chunkOverlap = parseInt(chunkOverlapInput.value, 10) || 50;

        try {
            await streamIngest(
                activeFile,
                { chunk_size: chunkSize, chunk_overlap: chunkOverlap },
                {
                    onEvent: (event) => {
                        updateIngestStep(event.stage, event.status, event.message);
                    },
                    onFinal: async (res) => {
                        await loadDocumentsList();
                        await updateStatus();
                        alert(`Document '${res.filename}' indexed successfully into ${res.chunk_count} chunks!`);
                    },
                    onError: (err) => {
                        alert(`Ingestion error: ${err}`);
                    },
                });
            } catch (err) {
                alert(`Upload failed: ${err}`);
            } finally {
                if (btnUploadSubmit) {
                    btnUploadSubmit.disabled = false;
                    btnUploadSubmit.textContent = "Start Ingestion Pipeline";
                }
            }
        });

    if (btnRefreshDocs) {
        btnRefreshDocs.addEventListener("click", loadDocumentsList);
    }

    if (btnLoadSamples) {
        btnLoadSamples.addEventListener("click", async () => {
            btnLoadSamples.disabled = true;
            btnLoadSamples.textContent = "Ingesting Samples...";
            try {
                await loadSamples();
                await loadDocumentsList();
                await updateStatus();
                alert("Sample documents ingested and persisted successfully!");
            } catch (err) {
                alert("Failed to load samples: " + err);
            } finally {
                btnLoadSamples.disabled = false;
                btnLoadSamples.textContent = "Load Samples";
            }
        });
    }

    if (btnResetDb) {
        btnResetDb.addEventListener("click", async () => {
            if (confirm("Are you sure you want to clear the entire vector database? All embeddings will be removed.")) {
                try {
                    await resetDatabase();
                    await loadDocumentsList();
                    await updateStatus();
                    alert("Vector database collection reset successfully.");
                } catch (err) {
                    alert("Failed to reset database: " + err);
                }
            }
        });
    }
}

export async function updateStatus() {
    const dbStatusText = document.getElementById("db-status-text");
    const tabDocCount = document.getElementById("tab-doc-count");
    const versionBadge = document.getElementById("app-version-badge");

    try {
        const data = await fetchStatus();
        if (data.version && versionBadge) {
            versionBadge.textContent = `v${data.version}`;
        }
        if (data.available_models) {
            renderModelDropdown(data.available_models, data.config?.default_model);
        }
        if (data.vector_store && dbStatusText) {
            const totalChunks = data.vector_store.total_chunks || 0;
            const totalDocs = data.vector_store.total_documents || 0;
            dbStatusText.textContent = `${totalChunks} chunks`;
            if (tabDocCount) tabDocCount.textContent = totalDocs;
        }
    } catch (err) {
        if (dbStatusText) dbStatusText.textContent = "connecting...";
    }
}

export async function loadDocumentsList() {
    const documentsListContainer = document.getElementById("documents-list-container");
    const tabDocCount = document.getElementById("tab-doc-count");
    if (!documentsListContainer) return;

    try {
        const data = await fetchDocuments();
        documentsListContainer.replaceChildren();

        if (!data.documents || data.documents.length === 0) {
            const empty = document.createElement("div");
            empty.className = "empty-state";
            empty.textContent = "No documents indexed yet. Ingest a document or click 'Load Samples' above.";
            documentsListContainer.appendChild(empty);
            if (tabDocCount) tabDocCount.textContent = "0";
            renderChatDocsRibbon([]);
            return;
        }

        if (tabDocCount) tabDocCount.textContent = data.documents.length;
        renderChatDocsRibbon(data.documents);

        data.documents.forEach(doc => {
            const card = document.createElement("div");
            card.className = "doc-card";

            const info = document.createElement("div");
            info.className = "doc-info";

            const icon = document.createElement("div");
            icon.className = "doc-icon-badge";
            icon.textContent = doc.file_type ? doc.file_type.toUpperCase() : "TXT";

            const details = document.createElement("div");
            const name = document.createElement("div");
            name.className = "doc-name";
            name.textContent = doc.filename;

            const meta = document.createElement("div");
            meta.className = "doc-meta";
            meta.textContent = `${doc.chunk_count} chunks • ${doc.page_count} page(s) • ~${doc.total_tokens_estimate} tokens`;

            details.appendChild(name);
            details.appendChild(meta);
            info.appendChild(icon);
            info.appendChild(details);

            const delBtn = document.createElement("button");
            delBtn.className = "btn btn-outline-danger btn-sm";
            delBtn.textContent = "Delete";
            delBtn.addEventListener("click", async () => {
                if (confirm(`Remove '${doc.filename}' from vector database?`)) {
                    await deleteDocument(doc.doc_id);
                    await loadDocumentsList();
                    await updateStatus();
                }
            });

            card.appendChild(info);
            card.appendChild(delBtn);
            documentsListContainer.appendChild(card);
        });
    } catch (err) {
        console.error("Failed to load documents:", err);
    }
}
