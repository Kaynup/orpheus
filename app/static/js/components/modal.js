/**
 * Modal Component for Inspecting Prompts, Chunks, and Sources
 */

let inspectorModal = null;
let modalTitle = null;
let modalBody = null;
let btnCloseModal = null;

export function initModal() {
    inspectorModal = document.getElementById("inspector-modal");
    modalTitle = document.getElementById("modal-title");
    modalBody = document.getElementById("modal-body");
    btnCloseModal = document.getElementById("btn-close-modal");

    if (!inspectorModal) return;

    if (btnCloseModal) {
        btnCloseModal.addEventListener("click", hideModal);
    }

    inspectorModal.addEventListener("click", (e) => {
        if (e.target === inspectorModal) {
            hideModal();
        }
    });
}

export function showModal(title, contentElement) {
    if (!inspectorModal || !modalTitle || !modalBody) return;
    modalTitle.textContent = title;
    modalBody.replaceChildren();
    if (contentElement) {
        modalBody.appendChild(contentElement);
    }
    inspectorModal.style.display = "flex";
}

export function hideModal() {
    if (inspectorModal) {
        inspectorModal.style.display = "none";
    }
}
