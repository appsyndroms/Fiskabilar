"""
Rendering av ML-statistik.
"""

from __future__ import annotations

from typing import Any

from data_loader import (
    fmt_number,
    fmt_price,
    safe,
)


MODEL_NAMES = {

    "random_forest":
        "Random Forest",

    "linear_regression":
        "Linear Regression",

}


def render_ml(
    ml: dict[str, Any],
) -> str:

    metadata = ml.get(
        "metadata",
        {},
    )

    if not metadata:

        return """
        <div class="empty">
            Ingen tränad ML-modell hittades ännu.
        </div>
        """


    model_key = str(
        metadata.get(
            "modell",
            "",
        )
    )


    model_name = (
        MODEL_NAMES.get(
            model_key,
            model_key
            or "Okänd",
        )
    )


    observations = metadata.get(
        "antal_observationer",
        0,
    )


    training = metadata.get(
        "antal_traning",
        0,
    )


    test = metadata.get(
        "antal_test",
        0,
    )


    created = metadata.get(
        "skapad",
        "—",
    )


    features = metadata.get(
        "features",
        [],
    )


    metrics = metadata.get(
        "metrics",
        {},
    )


    active_metrics = {}


    if isinstance(
        metrics,
        dict,
    ):

        model_metrics = (
            metrics.get(
                model_key,
                {},
            )
        )

        if isinstance(
            model_metrics,
            dict,
        ):

            active_metrics = (
                model_metrics.get(
                    "totalt",
                    {},
                )
            )


    r2 = active_metrics.get(
        "r2"
    )

    mae = active_metrics.get(
        "mae"
    )

    rmse = active_metrics.get(
        "rmse"
    )

    mape = active_metrics.get(
        "mape_procent"
    )


    total = (
        float(training or 0)
        + float(test or 0)
    )


    progress = (

        float(training or 0)
        / total
        * 100

        if total
        else 0

    )


    features_text = (

        ", ".join(
            str(feature)
            for feature
            in features
        )

        if isinstance(
            features,
            list,
        )

        else str(features)

    )


    comparison = []


    for key in (
        "linear_regression",
        "random_forest",
    ):

        data = {}


        if isinstance(
            metrics,
            dict,
        ):

            model_data = (
                metrics.get(
                    key,
                    {},
                )
            )

            if isinstance(
                model_data,
                dict,
            ):

                data = (
                    model_data.get(
                        "totalt",
                        {},
                    )
                )


        comparison.append(
            f"""
            <tr>

                <td>
                    <strong>

                        {safe(
                            MODEL_NAMES.get(
                                key,
                                key,
                            )
                        )}

                        {
                            " ⭐"
                            if key == model_key
                            else ""
                        }

                    </strong>
                </td>

                <td>
                    {fmt_number(
                        data.get("r2"),
                        3,
                    )}
                </td>

                <td>
                    {fmt_price(
                        data.get("mae")
                    )}
                </td>

                <td>
                    {fmt_price(
                        data.get("rmse")
                    )}
                </td>

                <td>
                    {fmt_number(
                        data.get(
                            "mape_procent"
                        ),
                        2,
                    )} %
                </td>

            </tr>
            """
        )


    return f"""

    <div
        data-ml-section
    >

        <div
            class="ml-filter-status"
            data-ml-filter-status
        ></div>


        <div class="ml-grid">

            <div class="ml-card">

                <span>
                    Aktiv modell
                </span>

                <strong>
                    {safe(model_name)}
                </strong>

            </div>


            <div class="ml-card">

                <span>
                    Observationer
                </span>

                <strong>
                    {fmt_number(
                        observations
                    )}
                </strong>

            </div>


            <div class="ml-card">

                <span>
                    R²
                </span>

                <strong>
                    {fmt_number(
                        r2,
                        3,
                    )}
                </strong>

            </div>


            <div class="ml-card">

                <span>
                    MAE
                </span>

                <strong>
                    {fmt_price(mae)}
                </strong>

            </div>


            <div class="ml-card">

                <span>
                    RMSE
                </span>

                <strong>
                    {fmt_price(rmse)}
                </strong>

            </div>


            <div class="ml-card">

                <span>
                    MAPE
                </span>

                <strong>
                    {fmt_number(
                        mape,
                        2,
                    )} %
                </strong>

            </div>

        </div>


        <div class="progress-card">

            <div class="progress-header">

                <strong>
                    ML-progress
                </strong>

                <span>
                    {fmt_number(training)}
                    träningsrader /
                    {fmt_number(total)} totalt
                </span>

            </div>


            <div class="progress">

                <div
                    style="width:{progress:.1f}%"
                ></div>

            </div>


            <div class="progress-meta">

                <span>
                    Träning:
                    {fmt_number(training)}
                </span>

                <span>
                    Test:
                    {fmt_number(test)}
                </span>

            </div>

        </div>


        <div class="ml-info">

            <p>

                <strong>
                    Senast tränad:
                </strong>

                {safe(created)}

            </p>


            <p>

                <strong>
                    Features:
                </strong>

                {safe(features_text)}

            </p>

        </div>


        <h3>
            Modelljämförelse
        </h3>


        <div class="table-wrap">

            <table>

                <thead>

                    <tr>
                        <th>Modell</th>
                        <th>R²</th>
                        <th>MAE</th>
                        <th>RMSE</th>
                        <th>MAPE</th>
                    </tr>

                </thead>

                <tbody>

                    {"".join(comparison)}

                </tbody>

            </table>

        </div>

    </div>

    """
