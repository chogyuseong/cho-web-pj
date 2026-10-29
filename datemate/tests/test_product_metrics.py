import time
import uuid
from types import SimpleNamespace
from app.experience import event
from app.telemetry import invoke_model
from scripts.operations_report import report


def test_product_report_deduplicates_actions_and_separates_self_report():
    since=time.time();owner=uuid.uuid4().hex
    event(owner,'p','selection',{})
    event(owner,'p','selection',{})
    event(owner,'p','visit',{'visited':'yes','reuse':'yes'})
    event(owner,'','recommendation',{'status':'complete','plans':1,'evidence_fields':2,'total_evidence_fields':8})
    result=report(since)
    assert result['product_actions']['selection']==1
    assert result['self_reported_visits']==1
    assert result['operating_evidence_coverage']==.25
    assert result['billing_cost']=='not_measured'


def test_model_usage_records_tokens_without_content(monkeypatch):
    since=time.time()
    model=SimpleNamespace(invoke=lambda _:SimpleNamespace(content='private content',usage_metadata={'input_tokens':100,'output_tokens':50,'total_tokens':150}))
    monkeypatch.setenv('DATEMATE_INPUT_USD_PER_MILLION','1')
    monkeypatch.setenv('DATEMATE_OUTPUT_USD_PER_MILLION','2')
    invoke_model(model,['private prompt'])
    result=report(since)
    assert result['model_usage']['total_tokens']==150
    assert result['model_usage']['estimated_usd']==.0002
    assert 'private' not in str(result)
