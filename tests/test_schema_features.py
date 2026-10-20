import copy
import numpy as np
import pytest
from pydantic import ValidationError
from tracelens.schema import Incident, Service
from tracelens.ml.features import extract,FEATURE_NAMES


def test_public_schema_round_trip(case):assert Incident.model_validate_json(case.model_dump_json())==case
@pytest.mark.parametrize("field",["root_service","fault_family","split","experiment_id"])
def test_label_fields_not_accepted(case,field):
    data=case.model_dump();data[field]="leaked"
    with pytest.raises(ValidationError):Incident.model_validate(data)
@pytest.mark.parametrize("value",[float("nan"),float("inf"),-1.])
def test_bad_metric_values_rejected(case,value):
    data=case.model_dump();data["services"][0]["metrics"]["latency_ms"][0]=value
    with pytest.raises(ValidationError):Incident.model_validate(data)
def test_error_rate_bound(case):
    data=case.model_dump();data["services"][0]["metrics"]["error_rate"][0]=1.1
    with pytest.raises(ValidationError):Incident.model_validate(data)
def test_missing_metric(case):
    data=case.model_dump();del data["services"][0]["metrics"]["cpu_pct"]
    with pytest.raises(ValidationError):Incident.model_validate(data)
def test_unaligned_samples(case):
    data=case.model_dump();data["services"][0]["metrics"]["latency_ms"].pop()
    with pytest.raises(ValidationError):Incident.model_validate(data)
def test_duplicate_service(case):
    data=case.model_dump();data["services"].append(data["services"][0])
    with pytest.raises(ValidationError):Incident.model_validate(data)
def test_unknown_log_service(case):
    data=case.model_dump();data["logs"][0]["service"]="not-a-service"
    with pytest.raises(ValidationError):Incident.model_validate(data)
def test_duplicate_evidence(case):
    data=case.model_dump();data["logs"].append(data["logs"][0])
    with pytest.raises(ValidationError):Incident.model_validate(data)
def test_unknown_dependency(case):
    data=case.model_dump();data["spans"][0]["target"]="absent"
    with pytest.raises(ValidationError):Incident.model_validate(data)
def test_feature_shapes(case):
    f=extract(case)
    assert f.temporal.shape==(6,24,6)
    assert f.logs.shape==(6,64)
    assert f.stats.shape==(6,len(FEATURE_NAMES))
    assert np.isfinite(f.temporal).all() and np.isfinite(f.stats).all()
def test_identifiers_and_title_do_not_change_features(case):
    f=extract(case);other=case.model_copy(update={"id":"different-id","title":"root-service-leak-attempt","source":"imported","started_at":"other"})
    changed=extract(other)
    for name in ["temporal","logs","stats"]:np.testing.assert_array_equal(getattr(f,name),getattr(changed,name))
def test_candidate_permutation_equivariance(case):
    a=extract(case);b=extract(case.model_copy(update={"services":list(reversed(case.services))}))
    for name in ["temporal","logs","stats"]:np.testing.assert_allclose(getattr(a,name)[::-1],getattr(b,name))
def test_resampling(case):
    raw=case.model_dump()
    for svc in raw["services"]:
        svc["metrics"]={k:v+v for k,v in svc["metrics"].items()}
    assert extract(Incident.model_validate(raw)).temporal.shape==(6,24,6)
