/**
 * Doc-QA Assistant - Frontend Logic with Real-Time Backend Event Synchronization
 * Strict XSS Prevention: All dynamic text is rendered via textContent and DOM APIs.
 */

document.addEventListener("DOMContentLoaded", () => {
    // State
    let activeFile = null;

    // Elements
    const tabButtons = document.querySelectorAll(".nav-tab");
    const tabPanes = document.querySelectorAll(".tab-pane");
    const dbStatusText = document.getElementById("db-status-text");
    const tabDocCount = document.getElementById("tab-doc-count");

    const btnLoadSamples = document.getElementById("btn-load-samples");
    const btnResetDb = document.getElementById("btn-reset-db");

    // Chat Elements
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatSubmitBtn = document.getElementById("chat-submit-btn");
    const chatMessagesArea = document.getElementById("chat-messages");
    const chatTopK = document.getElementById("chat-top-k");
    const chatModelSelect = document.getElementById("chat-model-select");
    const suggestionChips = document.querySelectorAll(".chip");

    // Ingestion Elements
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const selectedFileInfo = document.getElementById("selected-file-info");
    const selectedFileName = document.getElementById("selected-file-name");
    const btnClearFile = document.getElementById("btn-clear-file");
    const chunkSizeInput = document.getElementById("chunk-size-input");
    const chunkOverlapInput = document.getElementById("chunk-overlap-input");
    const btnUploadSubmit = document.getElementById("btn-upload-submit");
    const uploadForm = document.getElementById("upload-form");
    const documentsListContainer = document.getElementById("documents-list-container");
    const btnRefreshDocs = document.getElementById("btn-refresh-docs");

    // Evaluation Elements
    const btnRunEval = document.getElementById("btn-run-eval");
    const evalSummaryGrid = document.getElementById("eval-summary-grid");
    const evalTableBody = document.getElementById("eval-table-body");
    const evalStatPassRate = document.getElementById("eval-stat-pass-rate");
    const evalStatRetrieval = document.getElementById("eval-stat-retrieval");
    const evalStatGrounding = document.getElementById("eval-stat-grounding");
    const evalStatRefusal = document.getElementById("eval-stat-refusal");
    const evalStatLatency = document.getElementById("eval-stat-latency");

    // Modal Elements
    const inspectorModal = document.getElementById("inspector-modal");
    const modalTitle = document.getElementById("modal-title");
    const modalBody = document.getElementById("modal-body");
    const btnCloseModal = document.getElementById("btn-close-modal");

    // ==========================================
    // Tab Navigation
    // ==========================================
    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-tab");
            tabButtons.forEach(b => b.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));
            btn.classList.add("active");
            document.getElementById(targetId).classList.add("active");
        });
    });

    // ==========================================
    // Modal Helpers
    // ==========================================
    function showModal(title, contentElement) {
        modalTitle.textContent = title;
        modalBody.replaceChildren();
        modalBody.appendChild(contentElement);
        inspectorModal.style.display = "flex";
    }

    btnCloseModal.addEventListener("click", () => {
        inspectorModal.style.display = "none";
    });

    inspectorModal.addEventListener("click", (e) => {
        if (e.target === inspectorModal) {
            inspectorModal.style.display = "none";
        }
    });

    // ==========================================
    // Status & Document Fetching
    // ==========================================
    async function updateStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();
            if (data.version) {
                const versionBadge = document.getElementById("app-version-badge");
                if (versionBadge) versionBadge.textContent = `v${data.version}`;
            }
            if (data.vector_store) {
                const totalChunks = data.vector_store.total_chunks || 0;
                const totalDocs = data.vector_store.total_documents || 0;
                dbStatusText.textContent = `ChromaDB Ready (${totalChunks} chunks in ${totalDocs} docs)`;
                tabDocCount.textContent = totalDocs;
            }
        } catch (err) {
            dbStatusText.textContent = "ChromaDB Connecting...";
        }
    }

    async function loadDocuments() {
        try {
            const res = await fetch("/api/documents");
            const data = await res.json();
            documentsListContainer.replaceChildren();

            if (!data.documents || data.documents.length === 0) {
                const empty = document.createElement("div");
                empty.className = "empty-state";
                empty.textContent = "No documents indexed yet. Ingest a document or click 'Load Samples' above.";
                documentsListContainer.appendChild(empty);
                tabDocCount.textContent = "0";
                return;
            }

            tabDocCount.textContent = data.documents.length;

            data.documents.forEach(doc => {
                const card = document.createElement("div");
                card.className = "doc-card";

                const info = document.createElement("div");
                info.className = "doc-info";

                const icon = document.createElement("div");
                icon.className = "doc-icon-badge";
                icon.textContent = doc.file_type.toUpperCase();

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
                        await fetch(`/api/documents/${doc.doc_id}`, { method: "DELETE" });
                        loadDocuments();
                        updateStatus();
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

    btnRefreshDocs.addEventListener("click", loadDocuments);

    // ==========================================
    // Sample Ingestion & Reset
    // ==========================================
    btnLoadSamples.addEventListener("click", async () => {
        btnLoadSamples.disabled = true;
        btnLoadSamples.textContent = "Ingesting Samples...";
        try {
            const res = await fetch("/api/samples", { method: "POST" });
            const data = await res.json();
            await loadDocuments();
            await updateStatus();
            alert("Sample documents ingested and persisted successfully!");
        } catch (err) {
            alert("Failed to load samples: " + err);
        } finally {
            btnLoadSamples.disabled = false;
            btnLoadSamples.textContent = "Load Samples";
        }
    });

    btnResetDb.addEventListener("click", async () => {
        if (confirm("Are you sure you want to clear the entire vector database? All embeddings will be removed.")) {
            try {
                await fetch("/api/reset", { method: "POST" });
                await loadDocuments();
                await updateStatus();
                alert("Vector database collection reset successfully.");
            } catch (err) {
                alert("Failed to reset database: " + err);
            }
        }
    });

    // ==========================================
    // File Upload & Drag/Drop Ingestion
    // ==========================================
    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files && fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });

    function handleFileSelect(file) {
        activeFile = file;
        selectedFileName.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        selectedFileInfo.style.display = "flex";
        btnUploadSubmit.disabled = false;
    }

    btnClearFile.addEventListener("click", () => {
        activeFile = null;
        fileInput.value = "";
        selectedFileInfo.style.display = "none";
        btnUploadSubmit.disabled = true;
    });

    // Reset Ingestion Stepper Visuals
    function resetIngestStepper() {
        const steps = ["doc-received", "text-extracted", "chunks-created", "embeddings-generated", "vectors-stored"];
        steps.forEach(s => {
            const el = document.getElementById(`istep-${s}`);
            if (el) {
                el.className = "step-item";
                const details = el.querySelector(".step-details");
                if (details) details.textContent = "Waiting...";
            }
        });
    }

    function updateIngestStep(stage, status, message) {
        const stageMap = {
            "DOC_RECEIVED": "istep-doc-received",
            "TEXT_EXTRACTED": "istep-text-extracted",
            "CHUNKS_CREATED": "istep-chunks-created",
            "EMBEDDINGS_GENERATED": "istep-embeddings-generated",
            "VECTORS_STORED": "istep-vectors-stored",
            "INDEXING_COMPLETE": "istep-vectors-stored",
        };

        const elementId = stageMap[stage];
        if (!elementId) return;

        const el = document.getElementById(elementId);
        if (el) {
            el.className = `step-item ${status.toLowerCase()}`;
            const details = el.querySelector(".step-details");
            if (details) details.textContent = message;
        }
    }

    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!activeFile) return;

        btnUploadSubmit.disabled = true;
        btnUploadSubmit.textContent = "Indexing Document...";
        resetIngestStepper();

        const formData = new FormData();
        formData.append("file", activeFile);
        formData.append("chunk_size", chunkSizeInput.value || "500");
        formData.append("chunk_overlap", chunkOverlapInput.value || "50");

        try {
            const response = await fetch("/api/ingest/stream", {
                method: "POST",
                body: formData,
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                buffer = lines.pop(); // keep remainder

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const payload = JSON.parse(line.substring(6));
                            if (payload.event) {
                                updateIngestStep(payload.event.stage, payload.event.status, payload.event.message);
                            }
                            if (payload.__FINAL_RESULT__) {
                                await loadDocuments();
                                await updateStatus();
                                alert(`Document '${payload.__FINAL_RESULT__.filename}' indexed successfully into ${payload.__FINAL_RESULT__.chunk_count} chunks!`);
                            }
                            if (payload.__ERROR__) {
                                alert("Ingestion error: " + payload.__ERROR__);
                            }
                        } catch (pErr) {
                            console.error("Parse SSE error:", pErr);
                        }
                    }
                }
            }
        } catch (err) {
            alert("Upload failed: " + err);
        } finally {
            btnUploadSubmit.disabled = false;
            btnUploadSubmit.textContent = "Start Ingestion Pipeline";
        }
    });

    // ==========================================
    // Suggestion Chips
    // ==========================================
    suggestionChips.forEach(chip => {
        chip.addEventListener("click", () => {
            const query = chip.getAttribute("data-query");
            chatInput.value = query;
            chatForm.dispatchEvent(new Event("submit"));
        });
    });

    // ==========================================
    // QA Pipeline & Chat
    // ==========================================
    function resetQAStepper() {
        const steps = [
            "step-query-received",
            "step-query-embedded",
            "step-retrieving-chunks",
            "step-context-selected",
            "step-prompt-prepared",
            "step-generating-answer",
        ];
        steps.forEach(s => {
            const el = document.getElementById(s);
            if (el) {
                el.className = "step-item";
                const details = el.querySelector(".step-details");
                if (details) details.textContent = "Waiting...";
            }
        });
    }

    function updateQAStep(stage, status, message) {
        const stageMap = {
            "QUERY_RECEIVED": "step-query-received",
            "QUERY_EMBEDDED": "step-query-embedded",
            "RETRIEVING_CHUNKS": "step-retrieving-chunks",
            "CONTEXT_SELECTED": "step-context-selected",
            "PROMPT_PREPARED": "step-prompt-prepared",
            "GENERATING_ANSWER": "step-generating-answer",
            "ANSWER_COMPLETE": "step-generating-answer",
        };

        const elementId = stageMap[stage];
        if (!elementId) return;

        const el = document.getElementById(elementId);
        if (el) {
            el.className = `step-item ${status.toLowerCase()}`;
            const details = el.querySelector(".step-details");
            if (details) details.textContent = message;
        }
    }

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = chatInput.value.trim();
        if (!query) return;

        chatInput.value = "";
        chatSubmitBtn.disabled = true;
        resetQAStepper();

        // 1. Add User Message to Chat
        const userMsg = document.createElement("div");
        userMsg.className = "chat-message user-message";
        const userHeader = document.createElement("div");
        userHeader.className = "message-header";
        const userSender = document.createElement("span");
        userSender.className = "message-sender";
        userSender.textContent = "You";
        userHeader.appendChild(userSender);

        const userBody = document.createElement("div");
        userBody.className = "message-body";
        userBody.textContent = query;

        userMsg.appendChild(userHeader);
        userMsg.appendChild(userBody);
        chatMessagesArea.appendChild(userMsg);
        chatMessagesArea.scrollTop = chatMessagesArea.scrollHeight;

        // 2. Add Thinking Bot Message Placeholder
        const botMsg = document.createElement("div");
        botMsg.className = "chat-message bot-message";
        const botHeader = document.createElement("div");
        botHeader.className = "message-header";
        const botSender = document.createElement("span");
        botSender.className = "message-sender";
        botSender.textContent = "Doc-QA Assistant";
        const botTime = document.createElement("span");
        botTime.className = "message-time";
        botTime.textContent = "Processing...";
        botHeader.appendChild(botSender);
        botHeader.appendChild(botTime);

        const botBody = document.createElement("div");
        botBody.className = "message-body";
        botBody.textContent = "Executing RAG pipeline...";

        botMsg.appendChild(botHeader);
        botMsg.appendChild(botBody);
        chatMessagesArea.appendChild(botMsg);
        chatMessagesArea.scrollTop = chatMessagesArea.scrollHeight;

        // 3. Call Streaming SSE Endpoint
        try {
            const topK = parseInt(chatTopK.value, 10) || 3;
            const model = chatModelSelect.value;

            const response = await fetch("/api/query/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, top_k: topK, model }),
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const payload = JSON.parse(line.substring(6));

                            // Update Real Stepper
                            if (payload.event) {
                                updateQAStep(payload.event.stage, payload.event.status, payload.event.message);
                            }

                            // Final Result Rendering
                            if (payload.__FINAL_RESULT__) {
                                const res = payload.__FINAL_RESULT__;
                                botTime.textContent = `${res.duration_ms} ms`;
                                botBody.textContent = res.answer;

                                // Update Diagnostic Metrics
                                document.getElementById("inspector-metrics").style.display = "block";
                                document.getElementById("metric-latency").textContent = `${res.duration_ms} ms`;
                                document.getElementById("metric-chunks").textContent = res.retrieved_chunks.length;
                                document.getElementById("metric-sim").textContent = res.retrieved_chunks.length > 0 ? res.retrieved_chunks[0].similarity.toFixed(3) : "0.000";
                                document.getElementById("metric-tokens").textContent = res.generation.total_tokens;

                                // Render Citations
                                if (res.citations && res.citations.length > 0 && !res.is_refusal) {
                                    const citationsList = document.createElement("div");
                                    citationsList.className = "citations-list";

                                    const citLabel = document.createElement("span");
                                    citLabel.className = "citations-label";
                                    citLabel.textContent = "Sources:";
                                    citationsList.appendChild(citLabel);

                                    res.citations.forEach(cit => {
                                        const pill = document.createElement("button");
                                        pill.className = "citation-pill";
                                        pill.textContent = `[Source ${cit.source_index}: ${cit.filename}]`;
                                        pill.addEventListener("click", () => {
                                            const modalContent = document.createElement("div");
                                            const srcTitle = document.createElement("h4");
                                            srcTitle.textContent = `${cit.filename} (Page ${cit.page_number}) - Similarity: ${cit.similarity}`;
                                            const srcSnippet = document.createElement("pre");
                                            srcSnippet.textContent = cit.snippet;
                                            modalContent.appendChild(srcTitle);
                                            modalContent.appendChild(srcSnippet);
                                            showModal(`Source Citation [${cit.source_index}]`, modalContent);
                                        });
                                        citationsList.appendChild(pill);
                                    });
                                    botMsg.appendChild(citationsList);
                                }

                                // Message Action Buttons (Inspect Prompt & Chunks)
                                const actionsBar = document.createElement("div");
                                actionsBar.className = "message-actions-bar";

                                // 1. Inspect Context Chunks Button
                                const btnInspectChunks = document.createElement("button");
                                btnInspectChunks.className = "btn-drawer-toggle";
                                btnInspectChunks.textContent = `Inspect Chunks (${res.retrieved_chunks.length})`;
                                btnInspectChunks.addEventListener("click", () => {
                                    const container = document.createElement("div");
                                    res.retrieved_chunks.forEach(c => {
                                        const card = document.createElement("div");
                                        card.style.border = "1px solid var(--border-color)";
                                        card.style.borderRadius = "var(--radius-sm)";
                                        card.style.padding = "10px";
                                        card.style.marginBottom = "10px";
                                        card.style.background = "var(--bg-surface-soft)";

                                        const meta = document.createElement("div");
                                        meta.style.fontWeight = "600";
                                        meta.style.marginBottom = "6px";
                                        meta.textContent = `Rank ${c.rank} • ${c.source_filename} (Page ${c.page_number}) • Cosine Dist: ${c.distance} • Sim: ${c.similarity}`;

                                        const text = document.createElement("pre");
                                        text.textContent = c.content;

                                        card.appendChild(meta);
                                        card.appendChild(text);
                                        container.appendChild(card);
                                    });
                                    showModal("Retrieved Context Chunks (ChromaDB)", container);
                                });
                                actionsBar.appendChild(btnInspectChunks);

                                // 2. Inspect Augmented Prompt Button
                                const btnInspectPrompt = document.createElement("button");
                                btnInspectPrompt.className = "btn-drawer-toggle";
                                btnInspectPrompt.textContent = "Inspect Prompt";
                                btnInspectPrompt.addEventListener("click", () => {
                                    const promptPre = document.createElement("pre");
                                    promptPre.textContent = res.prompt.full_prompt_text;
                                    showModal("Inspected Augmented Prompt", promptPre);
                                });
                                actionsBar.appendChild(btnInspectPrompt);

                                botMsg.appendChild(actionsBar);
                                chatMessagesArea.scrollTop = chatMessagesArea.scrollHeight;
                            }

                            if (payload.__ERROR__) {
                                botBody.textContent = "Error: " + payload.__ERROR__;
                            }
                        } catch (err) {
                            console.error("SSE parse error:", err);
                        }
                    }
                }
            }
        } catch (err) {
            botBody.textContent = "Failed to query RAG pipeline: " + err;
        } finally {
            chatSubmitBtn.disabled = false;
        }
    });

    // ==========================================
    // Evaluation Benchmark Runner
    // ==========================================
    btnRunEval.addEventListener("click", async () => {
        btnRunEval.disabled = true;
        btnRunEval.textContent = "Running Benchmark (10 Questions)...";
        evalTableBody.replaceChildren();

        const loadingRow = document.createElement("tr");
        const loadingCell = document.createElement("td");
        loadingCell.colSpan = 8;
        loadingCell.className = "text-center";
        loadingCell.textContent = "Running benchmark evaluation suite against active ChromaDB store...";
        loadingRow.appendChild(loadingCell);
        evalTableBody.appendChild(loadingRow);

        try {
            const res = await fetch("/api/evaluate", { method: "POST" });
            const data = await res.json();
            if (data.report) {
                const rep = data.report;
                evalSummaryGrid.style.display = "grid";
                evalStatPassRate.textContent = `${rep.pass_rate_pct}%`;
                evalStatRetrieval.textContent = `${rep.retrieval_accuracy_pct}%`;
                evalStatGrounding.textContent = `${rep.grounding_accuracy_pct}%`;
                evalStatRefusal.textContent = `${rep.refusal_accuracy_pct}%`;
                evalStatLatency.textContent = `${rep.avg_latency_ms} ms`;

                evalTableBody.replaceChildren();

                rep.results.forEach(r => {
                    const row = document.createElement("tr");

                    const idCell = document.createElement("td");
                    idCell.style.fontWeight = "600";
                    idCell.textContent = r.test_id;

                    const catCell = document.createElement("td");
                    catCell.textContent = r.category;

                    const qCell = document.createElement("td");
                    qCell.textContent = r.question;

                    const retCell = document.createElement("td");
                    retCell.textContent = r.retrieval_passed ? "Yes" : "No";

                    const grdCell = document.createElement("td");
                    grdCell.textContent = r.grounding_passed ? "Yes" : "No";

                    const refCell = document.createElement("td");
                    refCell.textContent = r.refusal_passed ? "Yes" : "No";

                    const statusCell = document.createElement("td");
                    const badge = document.createElement("span");
                    badge.className = r.passed ? "badge badge-success" : "badge badge-fail";
                    badge.textContent = r.passed ? "PASS" : "FAIL";
                    statusCell.appendChild(badge);

                    const latCell = document.createElement("td");
                    latCell.textContent = `${r.latency_ms} ms`;

                    row.appendChild(idCell);
                    row.appendChild(catCell);
                    row.appendChild(qCell);
                    row.appendChild(retCell);
                    row.appendChild(grdCell);
                    row.appendChild(refCell);
                    row.appendChild(statusCell);
                    row.appendChild(latCell);

                    evalTableBody.appendChild(row);
                });
            }
        } catch (err) {
            alert("Evaluation failed: " + err);
        } finally {
            btnRunEval.disabled = false;
            btnRunEval.textContent = "Run Full Benchmark";
        }
    });

    // Initial Data Fetch
    updateStatus();
    loadDocuments();
});
