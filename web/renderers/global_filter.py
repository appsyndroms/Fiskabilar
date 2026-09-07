"""
Globalt filter för Fiskabilar Analytics.

Filtret körs helt i webbläsaren eftersom GitHub Pages är statiskt.

Data hämtas från data.json som build_static.py redan genererar.
"""

from __future__ import annotations


def render_global_filter() -> str:
    return r"""
<section id="global-filter">

    <div class="global-filter-card">

        <div class="global-filter-header">

            <div>

                <h2>
                    🔎 Filtrera hela sidan
                </h2>

                <p class="muted">
                    Filtret påverkar all statistik på sidan.
                </p>

            </div>

            <button
                id="global-filter-reset"
                type="button"
            >
                Rensa filter
            </button>

        </div>

        <div class="global-filter-grid">

            <label>

                <span>
                    Tillverkare
                </span>

                <select id="filter-make">

                    <option value="">
                        Alla tillverkare
                    </option>

                </select>

            </label>

            <label>

                <span>
                    Modell
                </span>

                <select id="filter-model">

                    <option value="">
                        Alla modeller
                    </option>

                </select>

            </label>

            <label>

                <span>
                    Årsmodell
                </span>

                <select id="filter-year">

                    <option value="">
                        Alla årsmodeller
                    </option>

                </select>

            </label>

        </div>

        <div
            id="global-filter-status"
            class="global-filter-status"
        ></div>

    </div>

</section>


<script>

(() => {

    const state = {

        data: null,

        make: "",

        model: "",

        year: "",

    };


    const $ = (
        id
    ) => document.getElementById(id);


    function text(
        value
    ) {

        return String(
            value ?? ""
        ).trim();

    }


    function first(
        row,
        keys
    ) {

        for (
            const key
            of keys
        ) {

            if (
                row
                && row[key] !== undefined
                && row[key] !== null
                && text(row[key])
            ) {

                return text(
                    row[key]
                );

            }

        }

        return "";

    }


    function modelName(
        row
    ) {

        /*
         * Modellfiltret ska ligga på modellnivå.
         *
         * Variant ska INTE ingå här.
         *
         * Exempel:
         *
         *   modell = V60
         *   variant = T6 AWD
         *
         * ska ge:
         *
         *   V60
         *
         * och inte:
         *
         *   V60 T6 AWD
         *
         * På så sätt blir flera drivlinevarianter
         * av samma modell ett enda modellalternativ.
         */

        const model = first(
            row,
            [
                "modell",
                "model",
            ]
        );

        return model
            .replace(
                /\s+/g,
                " "
            )
            .trim();

    }


    function yearName(
        row
    ) {

        return first(
            row,
            [
                "arsmodell",
                "modell_ar",
                "model_year",
                "year",
            ]
        );

    }


    function makeName(
        row
    ) {

        const explicit = first(
            row,
            [
                "tillverkare",
                "manufacturer",
                "make",
            ]
        );

        if (
            explicit
        ) {

            return explicit;

        }


        const model = modelName(
            row
        ).toLowerCase();


        /*
         * Fallback för den nuvarande datamodellen.
         *
         * Om tillverkare senare finns som explicit
         * fält används det automatiskt.
         */

        if (
            model.startsWith(
                "v60"
            )
            || model.startsWith(
                "v90"
            )
            || model.startsWith(
                "xc"
            )
        ) {

            return "Volvo";

        }


        if (
            model.startsWith(
                "330e"
            )
            || model.startsWith(
                "530e"
            )
            || model.startsWith(
                "i4"
            )
            || model.startsWith(
                "i5"
            )
        ) {

            return "BMW";

        }


        if (
            model.startsWith(
                "audi"
            )
        ) {

            return "Audi";

        }


        if (
            model.startsWith(
                "mercedes"
            )
        ) {

            return "Mercedes-Benz";

        }


        if (
            model.startsWith(
                "tesla"
            )
        ) {

            return "Tesla";

        }


        return (
            model
            .split(/\s+/)[0]
            || "Okänd"
        );

    }


    function matches(
        row
    ) {

        const make = makeName(
            row
        );

        const model = modelName(
            row
        );

        const year = yearName(
            row
        );


        return (

            (
                !state.make
                || make === state.make
            )

            &&

            (
                !state.model
                || model === state.model
            )

            &&

            (
                !state.year
                || year === state.year
            )

        );

    }


    function allRows() {

        const data =
            state.data || {};


        return [

            ...(data.current_findings || []),

            ...(data.price_reductions || []),

            ...(data.find_outcomes || []),

            ...(data.market_history || []),

        ];

    }


    function unique(
        rows,
        mapper
    ) {

        return [

            ...new Set(

                rows
                .map(mapper)
                .filter(Boolean)

            )

        ].sort(
            (
                a,
                b
            ) => String(a).localeCompare(
                String(b),
                "sv",
                {
                    numeric: true,
                }
            )
        );

    }


    function populateFilters() {

        const rows =
            allRows();


        const makeSelect =
            $("filter-make");

        const modelSelect =
            $("filter-model");

        const yearSelect =
            $("filter-year");


        const makes =
            unique(
                rows,
                makeName
            );


        const modelRows =
            rows.filter(
                row =>
                    !state.make
                    || makeName(row)
                    === state.make
            );


        /*
         * Modellalternativen bygger enbart på
         * grundmodellen och dedupliceras via Set.
         *
         * Variant används alltså inte här.
         */

        const models =
            unique(
                modelRows,
                modelName
            );


        const yearRows =
            rows.filter(
                row =>
                    (
                        !state.make
                        || makeName(row)
                        === state.make
                    )
                    &&
                    (
                        !state.model
                        || modelName(row)
                        === state.model
                    )
            );


        const years =
            unique(
                yearRows,
                yearName
            );


        makeSelect.innerHTML =
            '<option value="">Alla tillverkare</option>';


        makes.forEach(
            value =>
                makeSelect.add(
                    new Option(
                        value,
                        value
                    )
                )
        );


        makeSelect.value =
            state.make;


        modelSelect.innerHTML =
            '<option value="">Alla modeller</option>';


        models.forEach(
            value =>
                modelSelect.add(
                    new Option(
                        value,
                        value
                    )
                )
        );


        if (
            models.includes(
                state.model
            )
        ) {

            modelSelect.value =
                state.model;

        } else {

            state.model = "";

        }


        yearSelect.innerHTML =
            '<option value="">Alla årsmodeller</option>';


        years.forEach(
            value =>
                yearSelect.add(
                    new Option(
                        value,
                        value
                    )
                )
        );


        if (
            years.includes(
                state.year
            )
        ) {

            yearSelect.value =
                state.year;

        } else {

            state.year = "";

        }

    }


    function filterIndexedRows(
        selector,
        rows
    ) {

        document
            .querySelectorAll(
                selector
            )
            .forEach(
                (
                    element,
                    index
                ) => {

                    const row =
                        rows[index];


                    if (
                        !row
                    ) {

                        element.hidden =
                            true;

                        return;

                    }


                    element.hidden =
                        !matches(
                            row
                        );

                }
            );

    }


    function scoreBucket(
        score
    ) {

        const value =
            Number(score);


        if (
            !Number.isFinite(
                value
            )
        ) {

            return null;

        }


        if (
            value < 40
        ) {

            return "0–39";

        }


        if (
            value < 60
        ) {

            return "40–59";

        }


        if (
            value < 70
        ) {

            return "60–69";

        }


        if (
            value < 80
        ) {

            return "70–79";

        }


        if (
            value < 90
        ) {

            return "80–89";

        }


        return "90–100";

    }


    function renderScore() {

        const container =
            document.querySelector(
                "[data-score-container]"
            );


        if (
            !container
        ) {

            return;

        }


        const buckets = {

            "0–39": [],

            "40–59": [],

            "60–69": [],

            "70–79": [],

            "80–89": [],

            "90–100": [],

        };


        const outcomes =
            state.data
            .find_outcomes || [];


        outcomes
            .filter(matches)
            .forEach(
                row => {

                    const bucket =
                        scoreBucket(
                            row.score
                        );


                    if (
                        bucket
                    ) {

                        buckets[
                            bucket
                        ].push(
                            row
                        );

                    }

                }
            );


        container.innerHTML =
            Object.entries(
                buckets
            )
            .map(
                (
                    [
                        bucket,
                        rows,
                    ]
                ) => {

                    const counts = {};


                    rows.forEach(
                        row => {

                            const outcome =
                                first(
                                    row,
                                    [
                                        "utfall",
                                        "livscykelstatus",
                                    ]
                                )
                                || "OKÄNT";


                            counts[
                                outcome
                            ] =
                                (
                                    counts[
                                        outcome
                                    ]
                                    || 0
                                )
                                + 1;

                        }
                    );


                    const parts =
                        Object.entries(
                            counts
                        )
                        .map(
                            (
                                [
                                    name,
                                    count,
                                ]
                            ) =>
                                `${name}: ${count}`
                        )
                        .join(
                            " · "
                        );


                    return `
                    <div class="score-row">

                        <div>

                            <strong>
                                ${bucket}
                            </strong>

                            <span>
                                ${rows.length} event
                            </span>

                        </div>

                        <div>
                            ${parts || "—"}
                        </div>

                    </div>
                    `;

                }
            )
            .join("");

    }


    function renderOutcomes() {

        const container =
            document.querySelector(
                "[data-outcomes-container]"
            );


        if (
            !container
        ) {

            return;

        }


        const counts = {};


        const outcomes =
            state.data
            .find_outcomes || [];


        outcomes
            .filter(matches)
            .forEach(
                row => {

                    const outcome =
                        first(
                            row,
                            [
                                "utfall",
                                "livscykelstatus",
                            ]
                        )
                        || "OKÄNT";


                    counts[
                        outcome
                    ] =
                        (
                            counts[
                                outcome
                            ]
                            || 0
                        )
                        + 1;

                }
            );


        const total =
            Object.values(
                counts
            )
            .reduce(
                (
                    sum,
                    value
                ) =>
                    sum + value,
                0
            );


        if (
            !total
        ) {

            container.innerHTML =
                `
                <div class="empty">
                    Ingen fyndutfallsdata för valt filter.
                </div>
                `;

            return;

        }


        container.innerHTML =
            Object.entries(
                counts
            )
            .sort(
                (
                    a,
                    b
                ) =>
                    b[1] - a[1]
            )
            .map(
                (
                    [
                        name,
                        count,
                    ]
                ) => {

                    const share =
                        count
                        / total
                        * 100;


                    return `
                    <div class="bar-row">

                        <div class="bar-label">

                            <span>
                                ${name}
                            </span>

                            <strong>
                                ${count}
                            </strong>

                        </div>

                        <div class="bar">

                            <div
                                style="width:${share.toFixed(1)}%"
                            ></div>

                        </div>

                    </div>
                    `;

                }
            )
            .join("");

    }


    function updateKpis() {

        const data =
            state.data || {};


        const findings =
            (
                data.current_findings
                || []
            )
            .filter(matches);


        const reductions =
            (
                data.price_reductions
                || []
            )
            .filter(matches);


        const outcomes =
            (
                data.find_outcomes
                || []
            )
            .filter(matches);


        const history =
            (
                data.market_history
                || []
            )
            .filter(matches);


        const groups =
            new Set(
                history.map(
                    row =>
                        `${modelName(row)}|${yearName(row)}`
                )
            );


        const values = [

            findings.length,

            outcomes.length,

            reductions.length,

            history.length,

            groups.size,

        ];


        document
            .querySelectorAll(
                ".kpi strong"
            )
            .forEach(
                (
                    element,
                    index
                ) => {

                    if (
                        values[index]
                        !== undefined
                    ) {

                        element.textContent =
                            values[index]
                            .toLocaleString(
                                "sv-SE"
                            );

                    }

                }
            );

    }


    function updateHistory() {

        document
            .querySelectorAll(
                "[data-history-row]"
            )
            .forEach(
                element => {

                    const row = {

                        modell:
                            element.dataset.filterModel,

                        variant:
                            element.dataset.filterVariant,

                        arssmodell:
                            element.dataset.filterYear,

                    };


                    element.hidden =
                        !matches(
                            row
                        );

                }
            );


        document
            .querySelectorAll(
                "[data-chart-model]"
            )
            .forEach(
                chart => {

                    const model =
                        chart.dataset.chartModel
                        || "";


                    const years =
                        (
                            chart.dataset.chartYears
                            || ""
                        )
                        .split(",")
                        .filter(Boolean);


                    const modelOk =
                        !state.model
                        || model
                        === state.model;


                    const makeOk =
                        !state.make
                        || makeName({
                            modell: model,
                        })
                        === state.make;


                    const yearOk =
                        !state.year
                        || years.includes(
                            state.year
                        );


                    chart.hidden =
                        !(
                            modelOk
                            && makeOk
                            && yearOk
                        );


                    chart
                        .querySelectorAll(
                            "[data-chart-year]"
                        )
                        .forEach(
                            node => {

                                node.style.display =
                                    (
                                        !state.year
                                        || node.dataset.chartYear
                                        === state.year
                                    )
                                    ? ""
                                    : "none";

                            }
                        );

                }
            );

    }


    function updateMlStatus() {

        const section =
            document.querySelector(
                "[data-ml-section]"
            );


        if (
            !section
        ) {

            return;

        }


        /*
         * ML-modellen är tränad på hela historiken.
         *
         * Vi döljer inte modellen vid filter eftersom
         * dess R²/MAE/RMSE beskriver träningsmodellens
         * totala kvalitet.
         *
         * I stället visar vi tydligt detta i sektionen.
         */

        const message =
            section.querySelector(
                "[data-ml-filter-status]"
            );


        if (
            !message
        ) {

            return;

        }


        const active =
            [
                state.make,
                state.model,
                state.year,
            ]
            .filter(Boolean)
            .length;


        message.textContent =
            active
            ? "ML-måtten visar modellens totala träningskvalitet. Övriga sektioner är filtrerade."
            : "";

    }


    function updateUrl() {

        const params =
            new URLSearchParams();


        if (
            state.make
        ) {

            params.set(
                "tillverkare",
                state.make
            );

        }


        if (
            state.model
        ) {

            params.set(
                "modell",
                state.model
            );

        }


        if (
            state.year
        ) {

            params.set(
                "år",
                state.year
            );

        }


        const query =
            params.toString();


        history.replaceState(
            null,
            "",
            query
            ? `${location.pathname}?${query}`
            : location.pathname
        );

    }


    function update() {

        const data =
            state.data || {};


        filterIndexedRows(
            "[data-current-finding]",
            data.current_findings || []
        );


        filterIndexedRows(
            "[data-price-reduction]",
            data.price_reductions || []
        );


        renderScore();

        renderOutcomes();

        updateKpis();

        updateHistory();

        updateMlStatus();

        updateUrl();


        const visible =
            [
                ...(data.current_findings || []),
                ...(data.price_reductions || []),
                ...(data.find_outcomes || []),
                ...(data.market_history || []),
            ]
            .filter(matches)
            .length;


        const active =
            [
                state.make,
                state.model,
                state.year,
            ]
            .filter(Boolean)
            .length;


        $("global-filter-status")
            .textContent =
                active
                ? `${visible.toLocaleString("sv-SE")} relevanta observationer · filter aktivt`
                : "Visar hela datasetet";

    }


    function restoreUrl() {

        const params =
            new URLSearchParams(
                location.search
            );


        state.make =
            params.get(
                "tillverkare"
            )
            || "";


        state.model =
            params.get(
                "modell"
            )
            || "";


        state.year =
            params.get(
                "år"
            )
            || "";

    }


    async function init() {

        try {

            const response =
                await fetch(
                    "data.json",
                    {
                        cache:
                            "no-store",
                    }
                );


            if (
                !response.ok
            ) {

                throw new Error(
                    "data.json kunde inte läsas"
                );

            }


            state.data =
                await response.json();


            restoreUrl();

            populateFilters();

            update();

        } catch (
            error
        ) {

            console.error(
                error
            );


            $("global-filter-status")
                .textContent =
                    "Filtret kunde inte läsa data.json.";

        }

    }


    $("filter-make")
        .addEventListener(
            "change",
            event => {

                state.make =
                    event.target.value;

                state.model = "";

                state.year = "";

                populateFilters();

                update();

            }
        );


    $("filter-model")
        .addEventListener(
            "change",
            event => {

                state.model =
                    event.target.value;

                state.year = "";

                populateFilters();

                update();

            }
        );


    $("filter-year")
        .addEventListener(
            "change",
            event => {

                state.year =
                    event.target.value;

                update();

            }
        );


    $("global-filter-reset")
        .addEventListener(
            "click",
            () => {

                state.make = "";

                state.model = "";

                state.year = "";

                populateFilters();

                update();

            }
        );


    init();

})();

</script>
"""
