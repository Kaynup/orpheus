/**
 * Chat Feed & Query Submission Component
 */

import { streamQuery } from "../modules/api.js";
import { resetQAStepper, updateQAStep, updateDiagnosticMetrics } from "./inspector.js";
import { showModal } from "./modal.js";

export function renderChatDocsRibbon(documents) {
    const listContainer = document.getElementById("chat-docs-list");
    if (!listContainer) return;
    listContainer.replaceChildren();

    if (!documents || documents.length === 0) {
        const empty = document.createElement("span");
        empty.className = "chat-docs-empty";
        empty.textContent = "None indexed yet (click to upload)";
        empty.addEventListener("click", () => {
            document.getElementById("tab-btn-ingest")?.click();
        });
        listContainer.appendChild(empty);
        return;
    }

    documents.forEach(doc => {
        const badge = document.createElement("div");
        badge.className = "chat-doc-badge";
        badge.title = `${doc.filename} (${doc.chunk_count || 0} chunks) - Click to view in Documents tab`;

        const extSpan = document.createElement("span");
        extSpan.className = "chat-doc-ext";
        const parts = doc.filename ? doc.filename.split(".") : [];
        const ext = parts.length > 1 ? parts.pop() : (doc.file_type || "TXT");
        extSpan.textContent = (ext || "TXT").toUpperCase().slice(0, 4);

        badge.appendChild(extSpan);
        badge.addEventListener("click", () => {
            document.getElementById("tab-btn-ingest")?.click();
        });
        listContainer.appendChild(badge);
    });
}

export function renderModelDropdown(availableModels, defaultModel) {
    const menu = document.getElementById("model-dropdown-menu");
    const trigger = document.getElementById("model-dropdown-trigger");
    const nameLabel = document.getElementById("model-selected-name");
    const badgeLabel = document.getElementById("model-selected-badge");
    const hiddenSelect = document.getElementById("chat-model-select");

    if (!menu || !trigger) return;
    menu.replaceChildren();

    const models = Array.isArray(availableModels) && availableModels.length > 0
        ? availableModels
        : [{ id: "offline", name: "Offline Grounded Extractor", provider: "Local Extractor", badge: "No Key Required" }];

    let selectedModel = models.find(m => m.id === defaultModel) || models[0];

    function applySelection(model) {
        selectedModel = model;
        if (nameLabel) nameLabel.textContent = model.name;
        if (badgeLabel) badgeLabel.textContent = model.badge;
        if (hiddenSelect) {
            hiddenSelect.value = model.id;
            hiddenSelect.dispatchEvent(new Event("change"));
        }
        menu.querySelectorAll(".model-opt-item").forEach(item => {
            const isMatch = item.getAttribute("data-model-id") === model.id;
            item.classList.toggle("active", isMatch);
        });
    }

    models.forEach(model => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "model-opt-item";
        item.setAttribute("data-model-id", model.id);
        if (model.id === selectedModel.id) item.classList.add("active");

        const mainDiv = document.createElement("div");
        mainDiv.className = "model-opt-main";

        const nameSpan = document.createElement("span");
        nameSpan.className = "model-opt-name";
        nameSpan.textContent = model.name;

        const providerSpan = document.createElement("span");
        providerSpan.className = "model-opt-provider";
        providerSpan.textContent = model.provider;

        mainDiv.appendChild(nameSpan);
        mainDiv.appendChild(providerSpan);

        const badgeSpan = document.createElement("span");
        badgeSpan.className = "model-opt-badge";
        badgeSpan.textContent = model.badge;

        item.appendChild(mainDiv);
        item.appendChild(badgeSpan);

        item.addEventListener("click", (e) => {
            e.stopPropagation();
            applySelection(model);
            menu.classList.remove("open");
            trigger.classList.remove("active");
            trigger.setAttribute("aria-expanded", "false");
        });

        menu.appendChild(item);
    });

    if (hiddenSelect) {
        hiddenSelect.replaceChildren();
        models.forEach(m => {
            const opt = document.createElement("option");
            opt.value = m.id;
            opt.textContent = m.name;
            if (m.id === selectedModel.id) opt.selected = true;
            hiddenSelect.appendChild(opt);
        });
    }

    applySelection(selectedModel);

    trigger.onclick = (e) => {
        e.stopPropagation();
        const isOpen = menu.classList.toggle("open");
        trigger.classList.toggle("active", isOpen);
        trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
    };

    document.addEventListener("click", (e) => {
        if (!menu.contains(e.target) && !trigger.contains(e.target)) {
            menu.classList.remove("open");
            trigger.classList.remove("active");
            trigger.setAttribute("aria-expanded", "false");
        }
    });
}

export function initChat() {
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatSubmitBtn = document.getElementById("chat-submit-btn");
    const chatMessagesArea = document.getElementById("chat-messages");
    const chatTopK = document.getElementById("chat-top-k");
    const chatModelSelect = document.getElementById("chat-model-select");
    const docsLabel = document.getElementById("chat-docs-label");

    if (!chatForm || !chatInput || !chatMessagesArea) return;

    if (docsLabel) {
        docsLabel.addEventListener("click", () => {
            document.getElementById("tab-btn-ingest")?.click();
        });
    }

    // Top-K Split Button Dropdown Handlers
    const topKDropdownTrigger = document.getElementById("top-k-dropdown-trigger");
    const topKDropdownMenu = document.getElementById("top-k-dropdown-menu");
    const topKDisplayBadge = document.getElementById("top-k-display-badge");
    const topKOptions = document.querySelectorAll(".top-k-opt");

    if (topKDropdownTrigger && topKDropdownMenu) {
        topKDropdownTrigger.addEventListener("click", (e) => {
            e.stopPropagation();
            const isOpen = topKDropdownMenu.classList.toggle("open");
            topKDropdownTrigger.classList.toggle("active", isOpen);
            topKDropdownTrigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
        });

        topKOptions.forEach(opt => {
            opt.addEventListener("click", (e) => {
                e.stopPropagation();
                const val = opt.getAttribute("data-val");
                if (val && chatTopK) {
                    chatTopK.value = val;
                    if (topKDisplayBadge) topKDisplayBadge.textContent = `k=${val}`;
                    topKOptions.forEach(o => o.classList.remove("active"));
                    opt.classList.add("active");
                }
                topKDropdownMenu.classList.remove("open");
                topKDropdownTrigger.classList.remove("active");
                topKDropdownTrigger.setAttribute("aria-expanded", "false");
            });
        });

        document.addEventListener("click", (e) => {
            if (!topKDropdownMenu.contains(e.target) && !topKDropdownTrigger.contains(e.target)) {
                topKDropdownMenu.classList.remove("open");
                topKDropdownTrigger.classList.remove("active");
                topKDropdownTrigger.setAttribute("aria-expanded", "false");
            }
        });
    }

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = chatInput.value.trim();
        if (!query) return;

        chatInput.value = "";
        chatSubmitBtn.disabled = true;
        resetQAStepper();

        // 1. Add User Message
        const userMsg = document.createElement("div");
        userMsg.className = "chat-message user-message";

        const userHeader = document.createElement("div");
        userHeader.className = "message-header";
        const userTime = document.createElement("span");
        userTime.className = "message-time";
        userTime.textContent = "Just now";
        userHeader.appendChild(userTime);

        const userBody = document.createElement("div");
        userBody.className = "message-body";
        userBody.textContent = query;

        userMsg.appendChild(userHeader);
        userMsg.appendChild(userBody);
        chatMessagesArea.appendChild(userMsg);
        chatMessagesArea.scrollTop = chatMessagesArea.scrollHeight;

        // 2. Add Bot Placeholder
        const botMsg = document.createElement("div");
        botMsg.className = "chat-message bot-message";

        const botHeader = document.createElement("div");
        botHeader.className = "message-header";
        const botTime = document.createElement("span");
        botTime.className = "message-time";
        botTime.textContent = "Processing...";
        botHeader.appendChild(botTime);

        const botBody = document.createElement("div");
        botBody.className = "message-body";
        botBody.textContent = "Executing RAG pipeline...";

        botMsg.appendChild(botHeader);
        botMsg.appendChild(botBody);
        chatMessagesArea.appendChild(botMsg);
        chatMessagesArea.scrollTop = chatMessagesArea.scrollHeight;

        const topK = parseInt(chatTopK ? chatTopK.value : "3", 10) || 3;
        const model = chatModelSelect ? chatModelSelect.value : "gemini/gemini-1.5-flash";

        try {
            await streamQuery(
                { query, top_k: topK, model },
                {
                    onEvent: (event) => {
                        updateQAStep(event.stage, event.status, event.message);
                    },
                    onFinal: (res) => {
                        botTime.textContent = `${res.duration_ms} ms`;
                        botBody.textContent = res.answer;

                        updateDiagnosticMetrics(res);

                        if (res.generation && (res.generation.model === "offline-grounded-fallback" || res.generation.is_offline_mode)) {
                            const offlineBtn = document.querySelector('.model-opt-item[data-model-id="offline"]');
                            if (offlineBtn && !offlineBtn.classList.contains("active")) {
                                offlineBtn.click();
                            }
                        }

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

                        // Action buttons
                        const actionsBar = document.createElement("div");
                        actionsBar.className = "message-actions-bar";

                        if (res.retrieved_chunks && res.retrieved_chunks.length > 0) {
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
                                    meta.textContent = `Rank ${c.rank} • ${c.source_filename} (Page ${c.page_number}) • Dist: ${c.distance.toFixed(3)} • Sim: ${c.similarity.toFixed(3)}`;

                                    const text = document.createElement("pre");
                                    text.textContent = c.content;

                                    card.appendChild(meta);
                                    card.appendChild(text);
                                    container.appendChild(card);
                                });
                                showModal("Retrieved Context Chunks (ChromaDB)", container);
                            });
                            actionsBar.appendChild(btnInspectChunks);
                        }

                        if (res.prompt && res.prompt.full_prompt_text) {
                            const btnInspectPrompt = document.createElement("button");
                            btnInspectPrompt.className = "btn-drawer-toggle";
                            btnInspectPrompt.textContent = "Inspect Prompt";
                            btnInspectPrompt.addEventListener("click", () => {
                                const promptPre = document.createElement("pre");
                                promptPre.textContent = res.prompt.full_prompt_text;
                                showModal("Inspected Augmented Prompt", promptPre);
                            });
                            actionsBar.appendChild(btnInspectPrompt);
                        }

                        if (actionsBar.children.length > 0) {
                            botMsg.appendChild(actionsBar);
                        }

                        chatMessagesArea.scrollTop = chatMessagesArea.scrollHeight;
                    },
                    onError: (err) => {
                        botBody.textContent = `Error: ${err}`;
                    },
                }
            );
        } catch (err) {
            botBody.textContent = `Failed to query RAG pipeline: ${err}`;
        } finally {
            chatSubmitBtn.disabled = false;
        }
    });
}
