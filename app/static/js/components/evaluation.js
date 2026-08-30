/**
 * Evaluation Benchmark — IR metrics, confusion matrices, expandable rows.
 * All DOM mutations use textContent / createElement, zero innerHTML.
 */

import { runEvaluation } from "../modules/api.js";

export function initEvaluation() {
    const btnRunEval = document.getElementById("btn-run-eval");
    const summaryGrid = document.getElementById("eval-summary-grid");
    const matricesRow = document.getElementById("eval-matrices-row");
    const tableBody = document.getElementById("eval-table-body");
    const catFilter = document.getElementById("eval-category-filter");

    if (!btnRunEval || !tableBody) return;

    // Tooltip toggles
    document.querySelectorAll(".info-btn[data-tip]").forEach(btn => {
        btn.addEventListener("click", e => {
            e.stopPropagation();
            const tip = document.getElementById(btn.dataset.tip);
            if (tip) tip.hidden = !tip.hidden;
        });
    });

    // Category filter
    catFilter.addEventListener("change", () => {
        const val = catFilter.value;
        tableBody.querySelectorAll(".eval-row-main").forEach(row => {
            const cat = row.dataset.category || "";
            const show = val === "all" || cat === val;
            row.style.display = show ? "" : "none";
            const drawer = document.getElementById(`drawer-${row.dataset.rowId}`);
            if (drawer && !show) drawer.classList.remove("open");
        });
    });


    // Run benchmark

    btnRunEval.addEventListener("click", async () => {
        btnRunEval.disabled = true;
        btnRunEval.textContent = "Running…";
        tableBody.replaceChildren();
        _showLoadingRow(tableBody);

        try {
            const data = await runEvaluation();
            if (!data.report) throw new Error("No report returned from server.");
            const rep = data.report;

            // Show summary cards
            _updateStat("eval-stat-pass-rate", `${rep.pass_rate_pct}%`);
            _updateStat("eval-stat-precision", _pct(rep.mean_precision_at_k));
            _updateStat("eval-stat-recall", _pct(rep.mean_recall_at_k));
            _updateStat("eval-stat-mrr", rep.mean_reciprocal_rank.toFixed(3));
            _updateStat("eval-stat-hit-rate", _pct(rep.overall_hit_rate_at_k));
            _updateStat("eval-stat-latency", `${rep.avg_latency_ms} ms`);
            summaryGrid.style.display = "grid";

            // Render confusion matrices
            _renderConfusionMatrix(
                rep.retrieval_confusion_matrix,
                document.getElementById("eval-retrieval-matrix"),
                document.getElementById("eval-retrieval-stats"),
                {
                    rowLabels: ["Retrieved", "Omitted"],
                    colLabels: ["Relevant", "Irrelevant"],
                    statsBuilder: cm => [
                        `Precision: ${_pct(cm.precision)}`,
                        `Recall: ${_pct(cm.recall)}`,
                        `F1: ${_pct(cm.f1_score)}`,
                    ],
                }
            );
            _renderConfusionMatrix(
                rep.guardrail_confusion_matrix,
                document.getElementById("eval-guardrail-matrix"),
                document.getElementById("eval-guardrail-stats"),
                {
                    rowLabels: ["Refused", "Answered"],
                    colLabels: ["Unsupported", "Supported"],
                    statsBuilder: cm => {
                        const hallRate = cm.fn + cm.tp > 0
                            ? ((cm.fn / (cm.fn + cm.tp)) * 100).toFixed(1) + "%"
                            : "0%";
                        const frr = cm.fp + cm.tn > 0
                            ? ((cm.fp / (cm.fp + cm.tn)) * 100).toFixed(1) + "%"
                            : "0%";
                        return [
                            `Precision: ${_pct(cm.precision)}`,
                            `Hallucination rate: ${hallRate}`,
                            `False rejection: ${frr}`,
                        ];
                    },
                }
            );
            matricesRow.style.display = "grid";

            // Populate category filter
            const cats = [...new Set(rep.results.map(r => r.category))].sort();
            catFilter.replaceChildren();
            _appendOption(catFilter, "all", "All categories");
            cats.forEach(c => _appendOption(catFilter, c, c.replaceAll("_", " ")));
            catFilter.style.display = "";

            // Render results table
            tableBody.replaceChildren();
            rep.results.forEach((r, idx) => {
                const rowId = `row-${idx}`;
                tableBody.appendChild(_buildMainRow(r, rowId));
                tableBody.appendChild(_buildDrawerRow(r, rowId));
            });
        } catch (err) {
            console.error("Evaluation failed:", err);
            tableBody.replaceChildren();
            const errRow = document.createElement("tr");
            const errCell = document.createElement("td");
            errCell.colSpan = 8;
            errCell.className = "text-center";
            errCell.textContent = `Evaluation failed: ${err.message}`;
            errRow.appendChild(errCell);
            tableBody.appendChild(errRow);
        } finally {
            btnRunEval.disabled = false;
            btnRunEval.textContent = "Run Full Benchmark";
        }
    });

    // Confusion matrix renderer
    function _renderConfusionMatrix(cm, gridEl, statsEl, opts) {
        if (!gridEl) return;
        gridEl.replaceChildren();

        const { rowLabels, colLabels, statsBuilder } = opts;

        // Row 0: corner + col headers
        _appendCell(gridEl, "", "cm-header-cell");
        colLabels.forEach(lbl => _appendCell(gridEl, lbl, "cm-header-cell"));

        // Row 1: rowLabel[0] + TP + FP
        _appendCell(gridEl, rowLabels[0], "cm-row-label");
        _appendCmCell(gridEl, "TP", cm.tp, "cm-tp");
        _appendCmCell(gridEl, "FP", cm.fp, "cm-fp");

        // Row 2: rowLabel[1] + FN + TN
        _appendCell(gridEl, rowLabels[1], "cm-row-label");
        _appendCmCell(gridEl, "FN", cm.fn, "cm-fn");
        _appendCmCell(gridEl, "TN", cm.tn, "cm-tn");

        // Stats line
        if (statsEl) {
            statsEl.replaceChildren();
            statsBuilder(cm).forEach(text => {
                const span = document.createElement("span");
                span.className = "cm-stat-item";
                span.textContent = text;
                statsEl.appendChild(span);
            });
        }
    }

    // Table row builders
    function _buildMainRow(r, rowId) {
        const tr = document.createElement("tr");
        tr.className = "eval-row-main";
        tr.dataset.rowId = rowId;
        tr.dataset.category = r.category || "";

        const isRefusal = r.is_refusal;
        const na = "—";

        _td(tr, r.test_id, "600");
        _td(tr, (r.category || "").replaceAll("_", " "));
        _td(tr, r.question.length > 55 ? r.question.slice(0, 52) + "…" : r.question);
        _td(tr, isRefusal ? na : _pct(r.context_precision_at_k));
        _td(tr, isRefusal ? na : _pct(r.context_recall_at_k));
        _td(tr, isRefusal ? na : r.reciprocal_rank.toFixed(3));

        // Status badge
        const statusTd = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = r.passed ? "badge badge-success" : "badge badge-fail";
        badge.textContent = r.passed ? "PASS" : "FAIL";
        statusTd.appendChild(badge);
        tr.appendChild(statusTd);

        _td(tr, `${Math.round(r.latency_ms)} ms`);

        tr.addEventListener("click", () => {
            const drawer = document.getElementById(`drawer-${rowId}`);
            if (drawer) drawer.classList.toggle("open");
        });

        return tr;
    }

    function _buildDrawerRow(r, rowId) {
        const tr = document.createElement("tr");
        tr.className = "eval-row-drawer";
        tr.id = `drawer-${rowId}`;

        const td = document.createElement("td");
        td.className = "eval-drawer-cell";
        td.colSpan = 8;

        // Chunk detail list
        if (r.retrieved_chunks_detail && r.retrieved_chunks_detail.length > 0) {
            const listLabel = document.createElement("div");
            listLabel.style.cssText = "font-weight:600;font-size:11px;color:var(--text-muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:.3px;";
            listLabel.textContent = "Retrieved chunks";
            td.appendChild(listLabel);

            const ul = document.createElement("ul");
            ul.className = "eval-chunk-list";
            r.retrieved_chunks_detail.forEach(c => {
                const li = document.createElement("li");
                li.className = "eval-chunk-item " + (c.is_relevant ? "eval-chunk-relevant" : "eval-chunk-noise");

                const rank = _span(`#${c.rank}`, "eval-chunk-rank");
                const src = _span(c.source || "—", "eval-chunk-source");
                const score = _span(`score: ${c.score}`, "eval-chunk-score");
                const snip = _span(c.snippet || "", "eval-chunk-snippet");

                li.appendChild(rank); li.appendChild(src); li.appendChild(score); li.appendChild(snip);
                ul.appendChild(li);
            });
            td.appendChild(ul);
        }

        // Failure reasons
        if (r.failure_reasons && r.failure_reasons.length > 0) {
            const fDiv = document.createElement("div");
            fDiv.className = "eval-failure-reasons";
            r.failure_reasons.forEach(reason => {
                const p = document.createElement("p");
                p.style.margin = "2px 0";
                p.textContent = reason;
                fDiv.appendChild(p);
            });
            td.appendChild(fDiv);
        }

        tr.appendChild(td);
        return tr;
    }

    // DOM helpers

    function _showLoadingRow(tbody) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 8;
        td.className = "text-center text-muted";
        td.textContent = "Running benchmark evaluation suite…";
        tr.appendChild(td);
        tbody.appendChild(tr);
    }

    function _updateStat(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function _appendCell(parent, text, className) {
        const el = document.createElement("div");
        el.className = className;
        el.textContent = text;
        parent.appendChild(el);
    }

    function _appendCmCell(parent, label, val, className) {
        const cell = document.createElement("div");
        cell.className = `cm-cell ${className}`;

        const lbl = document.createElement("span");
        lbl.className = "cm-cell-label";
        lbl.textContent = label;

        const v = document.createElement("span");
        v.className = "cm-cell-val";
        v.textContent = val;

        cell.appendChild(lbl);
        cell.appendChild(v);
        parent.appendChild(cell);
    }

    function _appendOption(select, value, text) {
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = text;
        select.appendChild(opt);
    }

    function _td(tr, text, fontWeight) {
        const td = document.createElement("td");
        td.textContent = text;
        if (fontWeight) td.style.fontWeight = fontWeight;
        tr.appendChild(td);
    }

    function _span(text, className) {
        const s = document.createElement("span");
        s.className = className;
        s.textContent = text;
        return s;
    }

    function _pct(val) {
        if (val === null || val === undefined) return "—";
        return (val * 100).toFixed(1) + "%";
    }
}
