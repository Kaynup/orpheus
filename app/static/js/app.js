/**
 * Doc-QA Assistant - Main Application Bootstrap & Tab Navigation Router
 * Strict XSS Prevention: All dynamic text is rendered via textContent and DOM APIs.
 */

import { initModal } from "./components/modal.js";
import { initChat } from "./components/chat.js";
import { initIngestion, updateStatus, loadDocumentsList } from "./components/ingestion.js";
import { initEvaluation } from "./components/evaluation.js";

function initTabNavigation() {
    const tabButtons = document.querySelectorAll(".nav-tab");
    const tabPanes = document.querySelectorAll(".tab-pane");

    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-tab");
            if (!targetId) return;

            tabButtons.forEach(b => b.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));

            btn.classList.add("active");
            const targetPane = document.getElementById(targetId);
            if (targetPane) {
                targetPane.classList.add("active");
            }
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    // 1. Initialize Navigation & Modal
    initTabNavigation();
    initModal();

    // 2. Initialize Feature Components
    initChat();
    initIngestion();
    initEvaluation();

    // 3. Perform Initial Data Synchronization
    updateStatus();
    loadDocumentsList();
});
