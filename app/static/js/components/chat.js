/**
 * Chat Feed & Query Submission Component
 */

import { streamQuery } from "../modules/api.js";
import { resetQAStepper, updateQAStep, updateDiagnosticMetrics } from "./inspector.js";
import { showModal } from "./modal.js";

export function initChat() {
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatSubmitBtn = document.getElementById("chat-submit-btn");
    const chatMessagesArea = document.getElementById("chat-messages");
    const chatTopK = document.getElementById("chat-top-k");
    const chatModelSelect = document.getElementById("chat-model-select");
    const suggestionChips = document.querySelectorAll(".chip");

    if (!chatForm || !chatInput || !chatMessagesArea) return;

    // Handle suggestion chips
    suggestionChips.forEach(chip => {
        chip.addEventListener("click", () => {
            const query = chip.getAttribute("data-query");
            if (query) {
                chatInput.value = query;
                chatForm.dispatchEvent(new Event("submit"));
            }
        });
    });

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

        // 2. Add Bot Placeholder
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
