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


def _get_metric(
    metrics: dict[str, Any],
    name: str,
) -> Any:
    """
    Hämtar ett metric-värde.

    Stödjer både stora och små nycklar för
    bakåtkompatibilitet.
    """

    for key in (
        name,
        name.upper(),
        name.lower(),
    ):

        if key in metrics:
            return metrics[key]

    return None


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
            "model_type",
            metadata.get(
                "modell",
                "",
            ),
        )
    )


    model_name = (
        MODEL_NAMES.get(
            model_key,
            model_key
            or "Okänd",
        )
    )


    features = metadata.get(
        "features",
        [],
    )


    metrics = metadata.get(
        "metrics",
        {},
    )

    if not isinstance(
        metrics,
        dict,
    ):

        metrics = {}


    r2 = _get_metric(
        metrics,
        "R2",
    )

    mae = _get_metric(
        metrics,
        "MAE",
    )

    rmse = _get_metric(
        metrics,
        "RMSE",
    )

    bias = _get_metric(
        metrics,
        "Bias",
    )

    mape = _get_metric(
        metrics,
        "MAPE",
    )


    predictions = ml.get(
        "predictions",
        [],
    )

    observations = (
        len(predictions)
        if isinstance(
            predictions,
            list,
        )
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
                    Bias
                </span>

                <strong>
                    {fmt_price(bias)}
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


        <div class="ml-info">

            <p>

                <strong>
                    Modell:
                </strong>

                {safe(model_name)}

            </p>


            <p>

                <strong>
                    Features:
                </strong>

                {safe(features_text)}

            </p>


            <p>

                <strong>
                    Värderingsobservationer:
                </strong>

                {fmt_number(
                    observations
                )}

            </p>

        </div>


        <div class="table-wrap">

            <table>

                <thead>

                    <tr>
                        <th>Metric</th>
                        <th>Resultat</th>
                    </tr>

                </thead>

                <tbody>

                    <tr>
                        <td>R²</td>
                        <td>
                            {fmt_number(
                                r2,
                                3,
                            )}
                        </td>
                    </tr>

                    <tr>
                        <td>MAE</td>
                        <td>
                            {fmt_price(mae)}
                        </td>
                    </tr>

                    <tr>
                        <td>RMSE</td>
                        <td>
                            {fmt_price(rmse)}
                        </td>
                    </tr>

                    <tr>
                        <td>Bias</td>
                        <td>
                            {fmt_price(bias)}
                        </td>
                    </tr>

                    <tr>
                        <td>MAPE</td>
                        <td>
                            {fmt_number(
                                mape,
                                2,
                            )} %
                        </td>
                    </tr>

                </tbody>

            </table>

        </div>

    </div>

    """
