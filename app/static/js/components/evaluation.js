/**
 * Evaluation Benchmark Execution & Results Table Component
 */

import { runEvaluation } from "../modules/api.js";

export function initEvaluation() {
    const btnRunEval = document.getElementById("btn-run-eval");
    const evalSummaryGrid = document.getElementById("eval-summary-grid");
    const evalTableBody = document.getElementById("eval-table-body");
    const evalStatPassRate = document.getElementById("eval-stat-pass-rate");
    const evalStatRetrieval = document.getElementById("eval-stat-retrieval");
    const evalStatGrounding = document.getElementById("eval-stat-grounding");
    const evalStatRefusal = document.getElementById("eval-stat-refusal");
    const evalStatLatency = document.getElementById("eval-stat-latency");

    if (!btnRunEval || !evalTableBody) return;

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
            const data = await runEvaluation();
            if (data.report) {
                const rep = data.report;
                if (evalSummaryGrid) evalSummaryGrid.style.display = "grid";
                if (evalStatPassRate) evalStatPassRate.textContent = `${rep.pass_rate_pct}%`;
                if (evalStatRetrieval) evalStatRetrieval.textContent = `${rep.retrieval_accuracy_pct}%`;
                if (evalStatGrounding) evalStatGrounding.textContent = `${rep.grounding_accuracy_pct}%`;
                if (evalStatRefusal) evalStatRefusal.textContent = `${rep.refusal_accuracy_pct}%`;
                if (evalStatLatency) evalStatLatency.textContent = `${rep.avg_latency_ms} ms`;

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
            alert(`Evaluation failed: ${err}`);
        } finally {
            btnRunEval.disabled = false;
            btnRunEval.textContent = "Run Full Benchmark";
        }
    });
}
