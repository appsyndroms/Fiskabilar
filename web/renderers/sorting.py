"""Tillgänglig kolumnsortering för de statiska tabellerna."""


def render_table_sorting() -> str:
    return r"""
<script>
(() => {
    const collator = new Intl.Collator("sv", {numeric: true, sensitivity: "base"});

    function value(cell, numeric) {
        const text = (cell?.textContent || "").trim();
        if (!text || text === "—" || text === "–" || text === "-") return null;
        if (!numeric) return text;
        const normalized = text.replace(/\s/g, "").replace(/−/g, "-")
            .replace(/(?:kr|%|mil)$/i, "").replace(",", ".");
        const number = Number(normalized);
        return Number.isFinite(number) ? number : null;
    }

    document.querySelectorAll("table").forEach(table => {
        const body = table.tBodies[0];
        if (!body || !table.tHead) return;
        const headers = Array.from(table.tHead.rows[0].cells);
        const original = new Map(Array.from(body.rows, (row, index) => [row, index]));
        let active = -1;
        let direction = "ascending";

        function sort(column, nextDirection) {
            active = column;
            direction = nextDirection;
            const numeric = headers[column].dataset.sortType === "number";
            const sign = direction === "ascending" ? 1 : -1;
            const rows = Array.from(body.rows);
            rows.sort((left, right) => {
                const a = value(left.cells[column], numeric);
                const b = value(right.cells[column], numeric);
                // Saknade värden ska ligga sist i båda riktningarna.
                if (a === null || b === null) {
                    if (a !== b) return a === null ? 1 : -1;
                } else {
                    const result = numeric ? a - b : collator.compare(a, b);
                    if (result) return sign * result;
                }
                return original.get(left) - original.get(right);
            });
            body.append(...rows);
            headers.forEach((header, index) => {
                const selected = index === active;
                header.setAttribute("aria-sort", selected ? direction : "none");
                const button = header.querySelector("button");
                const next = selected && direction === "ascending" ? "fallande" : "stigande";
                button.setAttribute("aria-label", `${button.dataset.label}: sortera ${next}`);
                button.querySelector(".sort-indicator").textContent = selected
                    ? (direction === "ascending" ? "↑" : "↓") : "↕";
            });
        }

        headers.forEach((header, index) => {
            const label = header.textContent.trim();
            const button = document.createElement("button");
            button.type = "button";
            button.className = "table-sort";
            button.dataset.label = label;
            button.textContent = label + " ";
            button.setAttribute("aria-label", `${label}: sortera stigande`);
            const indicator = document.createElement("span");
            indicator.className = "sort-indicator";
            indicator.setAttribute("aria-hidden", "true");
            indicator.textContent = "↕";
            button.append(indicator);
            button.addEventListener("click", () => sort(index,
                active === index && direction === "ascending" ? "descending" : "ascending"));
            header.replaceChildren(button);
            header.setAttribute("scope", "col");
            header.setAttribute("aria-sort", "none");
        });

        const initial = headers.findIndex(header => header.dataset.sortDefault);
        if (initial >= 0) sort(initial, headers[initial].dataset.sortDefault);
    });
})();
</script>
"""
