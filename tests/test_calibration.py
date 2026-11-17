import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor

from ml import calibration
from ml.features import build_features
from ml.current_findings import build_current_findings
from valuation import market_value
from reporting import daily_market_report as report


def rows(count=40):
    return pd.DataFrame({"Identity": [str(i) for i in range(count)], "Price": [400000]*count,
                         "Model": ["v60"]*count, "Variant": ["T6 AWD"]*count,
                         "ModelYear": [2024]*count, "Mil": [5000]*count,
                         "Tid": pd.date_range("2026-11-01", periods=count, freq="h", tz="UTC")})


class CalibrationTests(unittest.TestCase):
    def test_positive_bias_is_subtracted_and_negative_bias_never_inflates_prices(self):
        data=rows()
        profile=calibration.build_calibration(data, np.full(len(data), 430000))
        estimator=DummyRegressor(strategy="constant", constant=430000).fit(build_features(data), data["Price"])
        model=calibration.CalibratedModel(estimator, profile)
        np.testing.assert_allclose(model.predict(build_features(data)), 400000)
        low=calibration.build_calibration(data, np.full(len(data), 380000))
        self.assertEqual(low["global"]["overvaluation_kr"], 0)

    def test_repeated_snapshots_do_not_multiply_calibration_weight(self):
        data=rows(2)
        extra=data.iloc[[0]].copy()
        extra["Tid"] += pd.Timedelta(days=2)
        data=pd.concat([data,extra],ignore_index=True)
        profile=calibration.build_calibration(data, [410000,430000,450000])
        self.assertEqual(profile["global"]["cars"],2)
        self.assertEqual(profile["global"]["overvaluation_kr"],40000)

    def test_small_groups_use_global_error_and_categories_are_normalized(self):
        data=rows(40)
        profile=calibration.build_calibration(data, np.arange(40)*1000+400000)
        self.assertEqual(calibration.stats_for(profile,"VOLVO V60","t6-awd"), profile["groups"]["v60 | t6 awd"])
        self.assertEqual(calibration.stats_for(profile,"BMW 330e xDrive Touring","330e xDrive Touring"),profile["global"])
        self.assertEqual(calibration.build_calibration(rows(2),[420000,430000])["groups"],{})

    def test_empirical_error_floor_and_percentage_all_control_eligibility(self):
        profile=calibration.build_calibration(rows(),np.full(40,400000))
        self.assertEqual(calibration.required_margin("v60","t6 awd",300000,profile),20000)
        self.assertEqual(calibration.required_margin("v60","t6 awd",600000,profile),30000)
        profile["global"]["error_margin_kr"]=60000
        self.assertEqual(calibration.required_margin("unknown","unknown",300000,profile),60000)

    def test_nonfinite_errors_fail_instead_of_claiming_calibration(self):
        with self.assertRaises(ValueError):
            calibration.build_calibration(rows(2),[np.nan,420000])

    def test_serialized_production_model_keeps_correction(self):
        data=rows()
        estimator=DummyRegressor(strategy="constant",constant=450000).fit(build_features(data),data["Price"])
        model=calibration.CalibratedModel(estimator,calibration.build_calibration(data,np.full(40,450000)))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"model.joblib"
            joblib.dump(model,path,compress=3)
            restored=joblib.load(path)
            np.testing.assert_allclose(restored.predict(build_features(data)),400000)

    def test_valuation_rejects_discount_smaller_than_uncertainty(self):
        car={"modell":"v60","variant":"T6 AWD","arsmodell":2024,"miltal":5000,"annonspris":400000}
        with patch.object(market_value,"_hamta_ml_borpris",return_value=440000), patch.object(market_value,"berakna_marknadsvarde",return_value=440000), patch.object(market_value,"required_margin",return_value=60000):
            result=market_value.berakna_fynd(car)
            self.assertIsNone(result["niva"])
            self.assertEqual(result["fyndmarginal_kr"],60000)

    def test_live_findings_reject_high_score_when_error_margin_exceeds_gap(self):
        data=rows(8)
        data.loc[0,"Price"]=350000
        profile=calibration.build_calibration(data,np.full(8,400000))
        profile["global"].update(overvaluation_kr=0,error_margin_kr=70000)
        estimator=DummyRegressor(strategy="constant",constant=400000).fit(build_features(data),data["Price"])
        model=calibration.CalibratedModel(estimator,profile)
        found=build_current_findings(data,model,as_of="2026-11-01T12:00:00Z")
        self.assertTrue(found.empty)

    def test_report_revalues_with_current_model_instead_of_old_high_score(self):
        ad={"vehicle_id":"car","tid":"2026-11-17T12:00:00+01:00","modell":"v60","variant":"T6 AWD","pris":400000,"miltal":5000,"arsmodell":2024}
        old={"vehicle_id":"car","tid":ad["tid"],"annonspris":400000,"miltal":5000,"fyndscore":95,"diff":80000,"marknadsvarde":480000}
        with patch.object(report,"_annonsobservationer",return_value=[ad]), patch.object(report,"_varderingar",return_value=[old]), patch.object(report,"_fyndfeedback",return_value=[]), patch.object(report,"canonical_vehicle_id",side_effect=lambda x:x), patch.object(report,"model_metadata",return_value={"calibration":{"version":1}}), patch.object(report,"_hamta_ml_borpris",return_value=420000), patch.object(report,"berakna_fynd",return_value={"niva":None}):
            self.assertEqual(report._fynd("2026-11-17"),[])

    def test_calibrated_valuation_uses_exact_mileage_not_legacy_grid(self):
        car={"modell":"v60","variant":"T6 AWD","arsmodell":2024,"miltal":4321}
        with patch.object(market_value,"model_metadata",return_value={"calibration":{"version":1}}), patch.object(market_value,"prediktera_borpris",return_value=412345) as predict, patch.object(market_value,"ML_PRISER",[{}]):
            self.assertEqual(market_value._hamta_ml_borpris(car),412345)
            self.assertEqual(predict.call_args.args[1],4321)

    def test_current_predictions_use_valuation_time_not_old_observation_time(self):
        data=rows(2)
        from unittest.mock import MagicMock
        model=MagicMock()
        model.predict.return_value=np.array([400000,400000])
        with patch("ml.current_findings.detektera_fynd",return_value=pd.DataFrame()):
            build_current_findings(data,model,as_of="2026-11-02T00:00:00Z")
        from ml.features import EPOCH
        expected=(pd.Timestamp("2026-11-02T00:00:00Z")-EPOCH).total_seconds()/86400
        self.assertTrue((model.predict.call_args.args[0]["ObservationDays"]==expected).all())

    def test_report_can_find_new_candidate_without_old_saved_valuation(self):
        ad={"vehicle_id":"new","tid":"2026-11-17T12:00:00+01:00","modell":"v60","variant":"T6 AWD","pris":400000,"miltal":5000,"arsmodell":2024}
        value={"niva":"FYND","marknadsvarde":460000,"diff":60000,"fyndmarginal_kr":50000}
        with patch.object(report,"_annonsobservationer",return_value=[ad]), patch.object(report,"_varderingar",return_value=[]), patch.object(report,"_fyndfeedback",return_value=[]), patch.object(report,"canonical_vehicle_id",side_effect=lambda x:x), patch.object(report,"model_metadata",return_value={"calibration":{"version":1}}), patch.object(report,"_hamta_ml_borpris",return_value=460000), patch.object(report,"berakna_fynd",return_value=value), patch.object(report,"berakna_fyndscore",return_value=80):
            self.assertEqual(len(report._fynd("2026-11-17")),1)

    def test_extreme_model_prediction_is_capped_by_independent_comparables(self):
        car={"modell":"v60","variant":"T6 AWD","arsmodell":2024,"miltal":5000,"annonspris":400000}
        with patch.object(market_value,"_hamta_ml_borpris",return_value=660000), patch.object(market_value,"berakna_marknadsvarde",return_value=660000), patch.object(market_value,"_hamta_jamforelsebilar",return_value=[{}, {}, {}]), patch.object(market_value,"_bygg_marknadsdiagnostik",return_value={"median_justerat":420000}), patch.object(market_value,"required_margin",return_value=50000):
            value=market_value.berakna_fynd(car)
            self.assertEqual(value["marknadsvarde"],420000)
            self.assertIsNone(value["niva"])

    def test_supported_gap_above_uncertainty_is_still_a_finding(self):
        car={"modell":"v60","variant":"T6 AWD","arsmodell":2024,"miltal":5000,"annonspris":400000}
        with patch.object(market_value,"_hamta_ml_borpris",return_value=480000), patch.object(market_value,"berakna_marknadsvarde",return_value=480000), patch.object(market_value,"_hamta_jamforelsebilar",return_value=[{}, {}, {}]), patch.object(market_value,"_bygg_marknadsdiagnostik",return_value={"median_justerat":490000}), patch.object(market_value,"required_margin",return_value=50000):
            value=market_value.berakna_fynd(car)
            self.assertIsNotNone(value["niva"])

    def test_report_and_web_use_the_same_calibrated_finding_engine(self):
        from ml.current_findings import _shared_calibrated_findings
        data=rows(8)
        data.loc[0,"Price"]=350000
        data["url"]=[f"https://example.test/{i}" for i in range(8)]
        profile=calibration.build_calibration(data,np.full(8,400000))
        profile["global"].update(overvaluation_kr=0,error_margin_kr=20000)
        ads=[{"vehicle_id":r["Identity"],"tid":r["Tid"].isoformat(),"modell":r["Model"],"variant":r["Variant"],"pris":r["Price"],"miltal":r["Mil"],"arsmodell":r["ModelYear"],"url":r["url"]} for r in data.to_dict("records")]
        with patch.object(calibration,"metadata",return_value={"calibration":profile}), patch.object(report,"model_metadata",return_value={"calibration":profile}), patch.object(report,"_hamta_ml_borpris",return_value=400000), patch.object(market_value,"_hamta_ml_borpris",return_value=400000), patch.object(market_value,"berakna_marknadsvarde",return_value=400000), patch.object(report,"_annonsobservationer",return_value=ads), patch.object(report,"_varderingar",return_value=[]), patch.object(report,"_fyndfeedback",return_value=[]), patch.object(report,"canonical_vehicle_id",side_effect=lambda x:x):
            web=_shared_calibrated_findings(data,np.full(8,400000),profile)
            daily=report._fynd("2026-11-01")
        self.assertEqual(len(daily),1)
        self.assertEqual(len(web),1)
        self.assertEqual(daily[0]["url"],web.iloc[0]["url"])
        self.assertEqual(daily[0]["marknadsvarde"],web.iloc[0]["Prediction"])
        self.assertEqual(daily[0]["fyndmarginal_kr"],web.iloc[0]["RequiredMargin"])
        # The static publication must retain the finding after matching its
        # vehicle identity and current price/mileage to the actual ad.
        from ml.fynd_export import exportera_fynd
        from web import build_static
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"fynd.jsonl"
            exportera_fynd(web,path)
            active={ad["vehicle_id"]:dict(ad,annonspris=ad["pris"]) for ad in ads}
            with patch.object(build_static,"ML_FINDINGS_FILE",path), patch.object(build_static,"_load_active_market_observations",return_value=active):
                published=build_static.get_ml_findings(ads)
        self.assertEqual(len(published),len(daily))
        self.assertEqual(published[0]["Identity"],daily[0]["vehicle_id"])

    def test_ad_metadata_carries_forward_but_never_from_future(self):
        from ml.train_market_model import _deduplicera_dataset
        data=rows(3)
        data["Identity"]="car"
        data["Price"]=[380000,390000,400000]
        data["utrustningsniva"]=[None,"Plus Dark",None]
        result=_deduplicera_dataset(data)
        self.assertTrue(pd.isna(result.iloc[0]["utrustningsniva"]))
        self.assertEqual(result.iloc[-1]["utrustningsniva"],"Plus Dark")

    def test_missing_url_is_only_carried_to_valuation_rows(self):
        from ml.train_market_model import _deduplicera_dataset
        data=rows(3)
        data["Identity"]="car"
        data["Price"]=[380000,390000,400000]
        data["utrustningsniva"]=[None,None,None]
        data["ObservationType"]=["annons","marknadsvarde","annons"]
        data["url"]=["https://example.test/car",None,None]
        result=_deduplicera_dataset(data)
        self.assertEqual(result.iloc[1]["url"],"https://example.test/car")
        self.assertTrue(pd.isna(result.iloc[2]["url"]))
